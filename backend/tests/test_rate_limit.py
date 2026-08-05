"""
Limiti di frequenza sulle rotte che chiunque può chiamare.

Erano quattro endpoint senza tetto: registrazione, login, verifica del codice
e rinvio del codice. Chiamandoli in ciclo si riempiva l'anagrafica di clienti
falsi, si bruciava la quota Brevo — 300 email al giorno, e quando finisce non
partono più **neanche** le conferme delle prenotazioni vere — e si provavano
password a raffica.

Il resto della suite gira coi limiti spenti (vedi `no_rate_limit` in
conftest): qui si riaccendono, perché sono la cosa da verificare.
"""
import pytest
import pytest_asyncio

from tests.conftest import ADMIN_PASSWORD, auth

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def limiti_accesi():
    """Riaccende i limiti e azzera i contatori prima di ogni test.

    L'azzeramento non è cosmetico: lo storage è condiviso nel processo, quindi
    senza, il secondo test partirebbe con il budget già consumato dal primo e
    fallirebbe per un motivo che non è quello che sta verificando.
    """
    from app.rate_limit import limiter

    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


def _registrazione(n: int) -> dict:
    return {
        "first_name": "Prova", "last_name": f"Numero{n}",
        "phone": f"+39333000{n:04d}", "email": f"prova{n}@example.it",
        "password": "password-lunga-abbastanza", "birth_date": "1990-01-01",
    }


class TestRegistrazione:
    async def test_la_sesta_in_un_ora_viene_fermata(self, client):
        """Cinque all'ora: un salone non registra di più, un ciclo automatico sì."""
        for n in range(5):
            resp = await client.post("/api/public/auth/register", json=_registrazione(n))
            assert resp.status_code in (201, 400), resp.text

        bloccata = await client.post("/api/public/auth/register", json=_registrazione(99))
        assert bloccata.status_code == 429
        assert "Troppi tentativi" in bloccata.json()["detail"]

    async def test_la_risposta_dice_quando_riprovare(self, client):
        for n in range(5):
            await client.post("/api/public/auth/register", json=_registrazione(n))
        bloccata = await client.post("/api/public/auth/register", json=_registrazione(99))
        assert bloccata.headers.get("Retry-After") is not None

    async def test_non_rivela_il_limite(self, client):
        """A chi lavora non serve sapere quale tetto ha toccato; a chi prova
        password servirebbe per tarare i tempi."""
        for n in range(5):
            await client.post("/api/public/auth/register", json=_registrazione(n))
        corpo = (await client.post(
            "/api/public/auth/register", json=_registrazione(99)
        )).json()
        assert "5" not in corpo["detail"] and "hour" not in corpo["detail"]


class TestLogin:
    async def test_undici_tentativi_al_minuto_vengono_fermati(self, client, admin_user):
        """Il tetto vale sui tentativi, non sui successi: è il caso della forza
        bruta, dove ogni richiesta è sbagliata fino all'ultima."""
        for _ in range(10):
            resp = await client.post(
                "/api/admin/auth/login",
                json={"email": admin_user.email, "password": "sbagliata"},
            )
            assert resp.status_code == 401

        bloccato = await client.post(
            "/api/admin/auth/login",
            json={"email": admin_user.email, "password": ADMIN_PASSWORD},
        )
        assert bloccato.status_code == 429, "la password giusta non deve aggirare il tetto"

    async def test_anche_il_login_unificato_e_coperto(self, client, admin_user):
        """Due schermate, la stessa porta: lasciarne una senza tetto renderebbe
        inutile il tetto sull'altra."""
        for _ in range(10):
            await client.post(
                "/api/auth/login",
                json={"email": admin_user.email, "password": "sbagliata"},
            )
        bloccato = await client.post(
            "/api/auth/login",
            json={"email": admin_user.email, "password": "sbagliata"},
        )
        assert bloccato.status_code == 429


class TestChiConta:
    async def test_due_indirizzi_diversi_hanno_budget_separati(self, client, admin_user):
        """Il conteggio è per chiamante. Se fosse globale, chi insiste
        bloccherebbe il salone — cioè l'attacco riuscirebbe lo stesso, solo per
        una strada diversa."""
        for _ in range(10):
            await client.post(
                "/api/admin/auth/login",
                headers={"X-Forwarded-For": "203.0.113.10"},
                json={"email": admin_user.email, "password": "sbagliata"},
            )
        suo = await client.post(
            "/api/admin/auth/login",
            headers={"X-Forwarded-For": "203.0.113.10"},
            json={"email": admin_user.email, "password": "sbagliata"},
        )
        assert suo.status_code == 429

        altro = await client.post(
            "/api/admin/auth/login",
            headers={"X-Forwarded-For": "203.0.113.99"},
            json={"email": admin_user.email, "password": ADMIN_PASSWORD},
        )
        assert altro.status_code == 200, "un altro IP non deve pagare per il primo"

    async def test_un_forwarded_for_inventato_non_azzera_il_budget(
        self, client, admin_user
    ):
        """Dietro il proxy di Railway la catena è `<quello che manda il client>,
        <quello vero>`. Prendendo l'ultima voce, cambiare la prima a ogni
        richiesta non serve a niente; prendendo la prima, il limite sarebbe
        aggirabile con un header."""
        for _ in range(10):
            await client.post(
                "/api/admin/auth/login",
                headers={"X-Forwarded-For": "1.2.3.4, 198.51.100.7"},
                json={"email": admin_user.email, "password": "sbagliata"},
            )

        travestito = await client.post(
            "/api/admin/auth/login",
            headers={"X-Forwarded-For": "9.9.9.9, 198.51.100.7"},
            json={"email": admin_user.email, "password": ADMIN_PASSWORD},
        )
        assert travestito.status_code == 429


class TestCosaRestaLibero:
    async def test_l_agenda_non_ha_tetto(self, client, admin_tokens):
        """Nessun limite di default: dal salone il calendario viene interrogato
        di continuo, e un tetto lì bloccherebbe chi sta lavorando."""
        for _ in range(30):
            resp = await client.get("/api/admin/appointments", headers=auth(admin_tokens))
            assert resp.status_code == 200


class TestPasswordCliente:
    """Il minimo lato server. Prima il campo accettava `1`, e un limite
    scritto solo nel form del browser non è un limite: basta chiamare l'API."""

    async def test_troppo_corta_rifiutata(self, client):
        corta = _registrazione(1)
        corta["password"] = "corta1"
        resp = await client.post("/api/public/auth/register", json=corta)
        assert resp.status_code == 422

    async def test_dieci_caratteri_bastano(self, client):
        giusta = _registrazione(2)
        giusta["password"] = "dieci12345"
        resp = await client.post("/api/public/auth/register", json=giusta)
        assert resp.status_code == 201, resp.text

    async def test_il_reset_non_e_la_scappatoia(self, client):
        """Senza il minimo anche qui, ci si registrerebbe con una password
        lunga per accorciarla subito dopo."""
        resp = await client.post(
            "/api/public/auth/reset-password",
            json={"token": "qualsiasi", "new_password": "corta"},
        )
        assert resp.status_code == 422


class TestBcryptFuoriDallEventLoop:
    async def test_le_funzioni_degli_handler_sono_asincrone(self):
        """Bcrypt occupa la CPU per un paio di decimi di secondo. Chiamato
        dentro un handler async non è «una richiesta lenta»: è l'intero event
        loop fermo, cioè tutta l'API che non risponde a nessuno."""
        import inspect

        from app.utils import auth

        assert inspect.iscoroutinefunction(auth.hash_password)
        assert inspect.iscoroutinefunction(auth.verify_password)

    async def test_restano_le_versioni_sincrone_per_gli_script(self):
        """Seed, bootstrap e la rotazione password girano fuori da un event
        loop: lì il threadpool non serve e non ci sarebbe modo di attenderlo."""
        import inspect

        from app.utils import auth

        assert not inspect.iscoroutinefunction(auth.hash_password_sync)
        assert auth.verify_password_sync(
            "prova-di-hash", auth.hash_password_sync("prova-di-hash")
        )

    async def test_l_event_loop_resta_libero_durante_un_hash(self):
        """La prova che il threadpool serve davvero: mentre bcrypt lavora, un
        altro task deve poter avanzare. Con la versione sincrona non girerebbe
        finché l'hash non ha finito."""
        import asyncio

        from app.utils.auth import hash_password

        battiti = 0

        async def cuore():
            nonlocal battiti
            while True:
                battiti += 1
                await asyncio.sleep(0.005)

        polso = asyncio.create_task(cuore())
        await hash_password("una-password-qualunque")
        polso.cancel()

        assert battiti > 1, "l'event loop è rimasto bloccato durante l'hash"


class TestSeRedisNonRisponde:
    """La domanda che conta: un limitatore rotto chiude fuori il salone?"""

    async def test_il_login_passa_lo_stesso(self, client, admin_user, monkeypatch):
        """Provato dal vivo prima di scriverlo: senza il ripiego in memoria,
        con Redis spento **ogni** login rispondeva 500. Sarebbe stato il
        salone chiuso fuori dal proprio gestionale perché è caduta una cache —
        e fino a ieri Redis giù voleva dire soltanto notifiche non spedite.
        """
        from app.rate_limit import limiter

        def esplode(*args, **kwargs):
            raise ConnectionError("Redis irraggiungibile")

        # Rompe lo storage sotto al limitatore, non l'endpoint.
        monkeypatch.setattr(limiter._limiter, "hit", esplode)

        resp = await client.post(
            "/api/admin/auth/login",
            json={"email": admin_user.email, "password": ADMIN_PASSWORD},
        )
        assert resp.status_code == 200, resp.text

    async def test_la_configurazione_dichiara_il_ripiego(self):
        """Le due opzioni che reggono il comportamento sopra. Un limite di
        frequenza è una protezione, non una dipendenza da cui far dipendere
        l'accesso."""
        from app.rate_limit import limiter

        assert limiter._in_memory_fallback_enabled is True
        assert limiter._swallow_errors is True
