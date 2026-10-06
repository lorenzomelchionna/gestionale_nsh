"""Limiti per persona: il Wi-Fi del salone non deve bloccare nessuno.

Le rotte della registrazione contavano solo per IP, e il salone ha un IP
solo per tutto il Wi-Fi. Il 3 ottobre una cliente che non riusciva a
confermare l'email ha consumato il budget di tutte: i rinvii del codice
fermati a 3 all'ora, e alle 13:22 un'altra persona, da un iPhone sullo
stesso Wi-Fi, respinta alla registrazione con «Troppi tentativi».

Adesso ogni rotta ha due tetti: uno stretto per indirizzo email (quello che
una persona sola incontra) e uno largo per IP (contro chi prova in ciclo).
Questi test fissano entrambe le metà: le persone diverse dallo stesso Wi-Fi
passano, la stessa persona che insiste no, e un IP che prova in ciclo resta
fermato.
"""
import logging

import pytest
from sqlalchemy import select

from app.models.client import ClientAccount

pytestmark = pytest.mark.asyncio

REGISTER = "/api/public/auth/register"
VERIFY = "/api/public/auth/verify-email"
VERIFY_PHONE = "/api/public/auth/verify-phone"
RESEND = "/api/public/auth/resend-code"
RESEND_PHONE = "/api/public/auth/resend-phone-code"
FORGOT = "/api/public/auth/forgot-password"
CHANGE_PHONE = "/api/public/auth/change-phone"

# Il Wi-Fi del salone: un IP solo, per tutte le clienti che ci passano.
SALONE = {"X-Forwarded-For": "185.178.11.129"}
PASSWORD = "password-lunga-abbastanza"


@pytest.fixture(autouse=True)
def limiti_accesi():
    """Come in `test_rate_limit.py`: limiti accesi e contatori azzerati."""
    from app.rate_limit import limiter

    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


@pytest.fixture(autouse=True)
def niente_invii(monkeypatch):
    """Email e WhatsApp finti: qui si contano le richieste, non i messaggi."""
    import app.api.public.auth as auth_api

    async def finto_email(*args, **kwargs):
        return None

    async def finto_whatsapp(*args, **kwargs):
        return None

    monkeypatch.setattr(auth_api, "send_verification_code_email", finto_email)
    monkeypatch.setattr(auth_api, "send_verification_code_whatsapp", finto_whatsapp)


def _registrazione(n: int, email: str | None = None) -> dict:
    return {
        "first_name": "Prova", "last_name": f"Numero{n}",
        "phone": f"+39333100{n:04d}", "email": email or f"cliente{n}@example.it",
        "password": PASSWORD, "birth_date": "1990-01-01",
    }


async def _in_attesa_del_numero(db, email: str) -> None:
    """Un account con l'email confermata e il numero no: lo stato in cui
    rinvio e correzione del numero hanno senso."""
    account = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == email)
    )).scalar_one()
    account.email_verified = True
    await db.commit()


class TestAlSalone:
    async def test_clienti_diverse_dallo_stesso_wifi_si_registrano(self, client):
        """Il caso del 3 ottobre, rovesciato: prima la sesta veniva respinta."""
        for n in range(8):
            resp = await client.post(REGISTER, headers=SALONE, json=_registrazione(n))
            assert resp.status_code == 201, f"cliente {n}: {resp.text}"

    async def test_chi_insiste_non_blocca_le_altre(self, client):
        """Una persona arriva al tetto dei rinvii; quella dopo, sullo stesso
        Wi-Fi, il codice lo riceve."""
        for n in (0, 1):
            await client.post(REGISTER, headers=SALONE, json=_registrazione(n))

        for _ in range(3):
            resp = await client.post(RESEND, headers=SALONE, json={"email": "cliente0@example.it"})
            assert resp.status_code == 200
        fermata = await client.post(RESEND, headers=SALONE, json={"email": "cliente0@example.it"})
        assert fermata.status_code == 429

        altra = await client.post(RESEND, headers=SALONE, json={"email": "cliente1@example.it"})
        assert altra.status_code == 200, "un'altra cliente sullo stesso Wi-Fi non deve pagare"


class TestPerIndirizzo:
    async def test_la_stessa_email_la_sesta_volta(self, client):
        for _ in range(5):
            resp = await client.post(REGISTER, json=_registrazione(0))
            assert resp.status_code == 201, resp.text
        assert (await client.post(REGISTER, json=_registrazione(0))).status_code == 429

    async def test_cambiare_ip_non_compra_un_budget_nuovo(self, client):
        """Il tetto è sull'indirizzo: scriverlo da cinque reti diverse non
        moltiplica le email che arrivano alla stessa casella."""
        for n in range(5):
            await client.post(
                REGISTER, headers={"X-Forwarded-For": f"203.0.113.{n}"},
                json=_registrazione(0),
            )
        resp = await client.post(
            REGISTER, headers={"X-Forwarded-For": "203.0.113.99"}, json=_registrazione(0),
        )
        assert resp.status_code == 429

    async def test_maiuscole_non_raddoppiano_il_budget(self, client):
        """`Mario@…` e `mario@…` arrivano alla stessa casella: contarli a parte
        raddoppierebbe le email che le si possono mandare."""
        varianti = [
            "maria.caso@example.it", "Maria.Caso@example.it", "MARIA.CASO@example.it",
            "maria.Caso@example.it", "Maria.caso@example.it",
        ]
        for email in varianti:
            resp = await client.post(REGISTER, json=_registrazione(0, email=email))
            assert resp.status_code in (201, 400), resp.text
        resp = await client.post(REGISTER, json=_registrazione(0, email="mARIA.cASO@example.it"))
        assert resp.status_code == 429

    async def test_rinvio_del_codice_email(self, client):
        await client.post(REGISTER, json=_registrazione(0))
        for _ in range(3):
            assert (await client.post(RESEND, json={"email": "cliente0@example.it"})).status_code == 200
        assert (await client.post(RESEND, json={"email": "cliente0@example.it"})).status_code == 429

    async def test_rinvio_del_codice_whatsapp(self, client, db):
        for n in (0, 1):
            await client.post(REGISTER, json=_registrazione(n))
            await _in_attesa_del_numero(db, f"cliente{n}@example.it")

        for _ in range(3):
            assert (await client.post(RESEND_PHONE, json={"email": "cliente0@example.it"})).status_code == 200
        assert (await client.post(RESEND_PHONE, json={"email": "cliente0@example.it"})).status_code == 429
        assert (await client.post(RESEND_PHONE, json={"email": "cliente1@example.it"})).status_code == 200

    async def test_password_dimenticata(self, client, client_account):
        for _ in range(3):
            assert (await client.post(FORGOT, json={"email": client_account.email})).status_code == 200
        assert (await client.post(FORGOT, json={"email": client_account.email})).status_code == 429
        assert (await client.post(FORGOT, json={"email": "altra@example.it"})).status_code == 200

    async def test_verifica_del_codice(self, client):
        """Dieci al minuto per indirizzo: i tentativi su un codice sono già
        contati a parte, questo ferma chi gira su più codici."""
        await client.post(REGISTER, json=_registrazione(0))
        for _ in range(10):
            resp = await client.post(VERIFY, json={"email": "cliente0@example.it", "code": "000000"})
            assert resp.status_code == 400
        resp = await client.post(VERIFY, json={"email": "cliente0@example.it", "code": "000000"})
        assert resp.status_code == 429
        altra = await client.post(VERIFY, json={"email": "altra@example.it", "code": "000000"})
        assert altra.status_code == 400, "un altro indirizzo dallo stesso IP non è fermato"

    async def test_verifica_del_numero(self, client, db):
        await client.post(REGISTER, json=_registrazione(0))
        await _in_attesa_del_numero(db, "cliente0@example.it")
        for _ in range(10):
            await client.post(VERIFY_PHONE, json={"email": "cliente0@example.it", "code": "000000"})
        resp = await client.post(VERIFY_PHONE, json={"email": "cliente0@example.it", "code": "000000"})
        assert resp.status_code == 429

    async def test_correzione_del_numero(self, client, db):
        await client.post(REGISTER, json=_registrazione(0))
        await _in_attesa_del_numero(db, "cliente0@example.it")
        corpo = {"email": "cliente0@example.it", "password": PASSWORD, "phone": "3331234567"}
        for _ in range(3):
            assert (await client.post(CHANGE_PHONE, json=corpo)).status_code == 200
        assert (await client.post(CHANGE_PHONE, json=corpo)).status_code == 429


class TestTettoPerIp:
    """Il tetto largo resta: un IP che registra in ciclo indirizzi sempre
    nuovi consumerebbe la quota Brevo (300 email al giorno), e con lei le
    conferme delle prenotazioni vere."""

    async def test_registrazioni(self, client):
        for n in range(20):
            resp = await client.post(REGISTER, headers=SALONE, json=_registrazione(n))
            assert resp.status_code == 201, f"{n}: {resp.text}"
        resp = await client.post(REGISTER, headers=SALONE, json=_registrazione(20))
        assert resp.status_code == 429

    async def test_rinvii_email(self, client):
        for n in range(20):
            await client.post(RESEND, headers=SALONE, json={"email": f"a{n}@example.it"})
        resp = await client.post(RESEND, headers=SALONE, json={"email": "a99@example.it"})
        assert resp.status_code == 429

    async def test_whatsapp_ha_il_tetto_piu_basso(self, client):
        """Ogni rinvio è un WhatsApp: costa, e mandato a raffica rovina la
        reputazione del numero del salone."""
        for n in range(10):
            await client.post(RESEND_PHONE, headers=SALONE, json={"email": f"a{n}@example.it"})
        resp = await client.post(RESEND_PHONE, headers=SALONE, json={"email": "a99@example.it"})
        assert resp.status_code == 429


class TestNelLog:
    async def _fino_al_tetto_per_email(self, client):
        await client.post(REGISTER, json=_registrazione(0, email="Pinco.Pallina@example.it"))
        for _ in range(3):
            await client.post(RESEND, json={"email": "Pinco.Pallina@example.it"})
        return await client.post(RESEND, json={"email": "Pinco.Pallina@example.it"})

    async def test_si_capisce_quale_tetto_ha_fermato(self, client, caplog):
        with caplog.at_level(logging.DEBUG):
            fermata = await self._fino_al_tetto_per_email(client)
        assert fermata.status_code == 429
        [ev] = [r for r in caplog.records if getattr(r, "evento", None) == "limite_superato"]
        assert ev.chiave == "email"
        assert ev.email == "p***a@example.it"

    async def test_l_indirizzo_non_finisce_nei_log_in_chiaro(self, client, caplog):
        """slowapi scrive la chiave del limite nel suo avviso: con l'indirizzo
        dentro, il log diventerebbe un elenco di email non mascherate."""
        with caplog.at_level(logging.DEBUG):
            await self._fino_al_tetto_per_email(client)
        tutto = " ".join(r.getMessage() + " " + str(r.__dict__) for r in caplog.records).lower()
        assert "pinco.pallina" not in tutto

    async def test_il_tetto_per_ip_lo_dice(self, client, caplog):
        with caplog.at_level(logging.DEBUG):
            for n in range(21):
                await client.post(REGISTER, headers=SALONE, json=_registrazione(n))
        [ev] = [r for r in caplog.records if getattr(r, "evento", None) == "limite_superato"]
        assert ev.chiave == "ip"
