"""«Numero sbagliato? Correggilo»: il numero sulla schermata del codice WhatsApp.

Il 2 ottobre una cliente ha scritto male il proprio numero: il codice è
arrivato a un estraneo — che l'ha letto — e lei, che non lo vedeva arrivare,
ha potuto solo registrarsi da capo con un'altra email. La schermata diceva
«Abbiamo mandato sei cifre su WhatsApp» senza dire **dove**.

Due metà, e questi test le fissano entrambe:
  - il numero si vede, ma solo a chi ha dimostrato qualcosa (il codice email
    o la password): il rinvio, che chiunque può chiedere con un indirizzo,
    non lo dice;
  - il numero si corregge, ma quello nuovo resta in attesa finché il codice
    non torna — la scheda può essere quella del salone, e non deve prendersi
    un numero mai provato.
"""
import pytest
from sqlalchemy import select

from app.models.client import Client, ClientAccount

pytestmark = pytest.mark.asyncio

REGISTER = "/api/public/auth/register"
VERIFY = "/api/public/auth/verify-email"
VERIFY_PHONE = "/api/public/auth/verify-phone"
RESEND_PHONE = "/api/public/auth/resend-phone-code"
CHANGE_PHONE = "/api/public/auth/change-phone"
LOGIN = "/api/auth/login"
LOGIN_PORTALE = "/api/public/auth/login"

EMAIL = "lucia.numero@nsh-test.it"
PASSWORD = "una-password-lunga-2026"
SBAGLIATO = "+393349990011"   # quello scritto alla registrazione, con l'errore
GIUSTO = "+393351112233"      # quello vero


@pytest.fixture
def email_inviate(monkeypatch):
    import app.api.public.auth as auth_api

    codici: list[tuple[str, str]] = []

    async def finto(to_email, first_name, code, ttl_minutes):
        codici.append((to_email, code))

    monkeypatch.setattr(auth_api, "send_verification_code_email", finto)
    return codici


@pytest.fixture
def whatsapp_inviati(monkeypatch):
    import app.api.public.auth as auth_api

    codici: list[tuple[str, str]] = []

    async def finto(to_phone, code):
        codici.append((to_phone, code))

    monkeypatch.setattr(auth_api, "send_verification_code_whatsapp", finto)
    return codici


async def _registra(client, email_inviate, phone=SBAGLIATO):
    resp = await client.post(REGISTER, json={
        "first_name": "Lucia", "last_name": "Numero", "phone": phone,
        "email": EMAIL, "password": PASSWORD, "birth_date": "1985-04-12",
    })
    assert resp.status_code == 201, resp.text
    return email_inviate[-1][1]


async def _fino_al_codice_whatsapp(client, email_inviate, phone=SBAGLIATO):
    codice = await _registra(client, email_inviate, phone)
    resp = await client.post(VERIFY, json={"email": EMAIL, "code": codice})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _correggi(client, phone=GIUSTO, password=PASSWORD):
    return await client.post(CHANGE_PHONE, json={
        "email": EMAIL, "password": password, "phone": phone,
    })


async def _account(db) -> ClientAccount:
    return (await db.execute(
        select(ClientAccount).where(ClientAccount.email == EMAIL)
    )).scalar_one()


async def _scheda(db) -> Client:
    account = await _account(db)
    return (await db.execute(
        select(Client).where(Client.account_id == account.id)
    )).scalar_one()


class TestIlNumeroSulloSchermo:
    async def test_dopo_l_email_dice_dove_e_partito_il_codice(
        self, client, email_inviate, whatsapp_inviati,
    ):
        esito = await _fino_al_codice_whatsapp(client, email_inviate, phone="334 999 0011")
        assert esito["phone"] == SBAGLIATO, "normalizzato, come lo vede WhatsApp"
        assert whatsapp_inviati[-1][0] == esito["phone"], "quello scritto è quello usato"

    @pytest.mark.parametrize("percorso", [LOGIN, LOGIN_PORTALE])
    async def test_il_login_bloccato_lo_dice(
        self, client, email_inviate, whatsapp_inviati, percorso,
    ):
        await _fino_al_codice_whatsapp(client, email_inviate)
        resp = await client.post(percorso, json={"email": EMAIL, "password": PASSWORD})
        assert resp.status_code == 403
        corpo = resp.json()
        assert "telefono" in corpo["detail"].lower(), "il frontend sceglie la schermata da qui"
        assert corpo["phone"] == SBAGLIATO

    async def test_con_la_password_sbagliata_niente(self, client, email_inviate, whatsapp_inviati):
        await _fino_al_codice_whatsapp(client, email_inviate)
        resp = await client.post(LOGIN, json={"email": EMAIL, "password": "non-è-lei-12345"})
        assert resp.status_code == 401
        assert "phone" not in resp.json()

    async def test_il_rinvio_non_lo_dice(self, client, email_inviate, whatsapp_inviati):
        """Per chiedere un rinvio basta un indirizzo: se la risposta dicesse
        il numero, chiunque conosca un'email avrebbe il cellulare di chi."""
        await _fino_al_codice_whatsapp(client, email_inviate)
        resp = await client.post(RESEND_PHONE, json={"email": EMAIL})
        assert resp.status_code == 200
        assert SBAGLIATO not in resp.text and "phone\"" not in resp.text

    async def test_con_la_scheda_del_salone_dice_il_numero_del_salone(
        self, client, db, email_inviate, whatsapp_inviati,
    ):
        """Dopo l'email l'account prende la scheda che il salone aveva per
        quell'indirizzo, e il codice parte al numero di quella — magari il
        fisso di casa. È proprio il caso in cui vederlo serve."""
        db.add(Client(first_name="Lucia", last_name="Numero", email=EMAIL, phone="+390825123456"))
        await db.commit()

        esito = await _fino_al_codice_whatsapp(client, email_inviate)
        assert esito["phone"] == "+390825123456"
        assert whatsapp_inviati[-1][0] == "+390825123456"


class TestCorreggereIlNumero:
    async def test_il_codice_parte_al_numero_nuovo_e_la_scheda_aspetta(
        self, client, db, email_inviate, whatsapp_inviati,
    ):
        await _fino_al_codice_whatsapp(client, email_inviate)
        resp = await _correggi(client, phone="335 111 2233")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"whatsapp_sent": True, "phone": GIUSTO}
        assert whatsapp_inviati[-1][0] == GIUSTO

        assert (await _scheda(db)).phone == SBAGLIATO, "finché il codice non torna, la scheda non cambia"
        assert (await _account(db)).phone_pending == GIUSTO

    async def test_col_codice_il_numero_passa_sulla_scheda(
        self, client, db, email_inviate, whatsapp_inviati,
    ):
        await _fino_al_codice_whatsapp(client, email_inviate)
        await _correggi(client)
        resp = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": whatsapp_inviati[-1][1]})
        assert resp.status_code == 200, resp.text
        assert "access_token" in resp.json()

        db.expire_all()
        assert (await _scheda(db)).phone == GIUSTO
        account = await _account(db)
        assert account.phone_verified and account.phone_pending is None

    async def test_il_codice_del_numero_sbagliato_non_vale_piu(
        self, client, email_inviate, whatsapp_inviati,
    ):
        """Il primo codice è andato a un estraneo: dopo la correzione non deve
        più aprire niente."""
        await _fino_al_codice_whatsapp(client, email_inviate)
        codice_all_estraneo = whatsapp_inviati[-1][1]
        await _correggi(client)
        resp = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": codice_all_estraneo})
        assert resp.status_code == 400

    async def test_il_rinvio_va_al_numero_nuovo(self, client, email_inviate, whatsapp_inviati):
        await _fino_al_codice_whatsapp(client, email_inviate)
        await _correggi(client)
        await client.post(RESEND_PHONE, json={"email": EMAIL})
        assert whatsapp_inviati[-1][0] == GIUSTO

    async def test_il_login_dopo_la_correzione_dice_il_numero_nuovo(
        self, client, email_inviate, whatsapp_inviati,
    ):
        await _fino_al_codice_whatsapp(client, email_inviate)
        await _correggi(client)
        resp = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
        assert resp.json()["phone"] == GIUSTO

    async def test_la_scheda_del_salone_cambia_solo_col_codice(
        self, client, db, email_inviate, whatsapp_inviati,
    ):
        salone = Client(first_name="Lucia", last_name="Numero", email=EMAIL, phone="+390825123456")
        db.add(salone)
        await db.commit()
        salone_id = salone.id

        await _fino_al_codice_whatsapp(client, email_inviate)
        await _correggi(client)
        db.expire_all()
        assert (await db.get(Client, salone_id)).phone == "+390825123456"

        await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": whatsapp_inviati[-1][1]})
        db.expire_all()
        assert (await db.get(Client, salone_id)).phone == GIUSTO

    async def test_il_collegamento_per_telefono_cerca_il_numero_giusto(
        self, client, db, email_inviate, whatsapp_inviati,
    ):
        """Una scheda senza email, segnata dal salone col numero vero: si
        unisce all'account solo se il collegamento cerca il numero appena
        dimostrato, non quello sbagliato della registrazione."""
        vecchia = Client(first_name="Lucia", last_name="Numero", phone=GIUSTO)
        db.add(vecchia)
        await db.commit()
        vecchia_id = vecchia.id

        await _fino_al_codice_whatsapp(client, email_inviate)
        await _correggi(client)
        await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": whatsapp_inviati[-1][1]})

        db.expire_all()
        account = await _account(db)
        assert (await db.get(Client, vecchia_id)).account_id == account.id


class TestChiPuoCorreggere:
    async def test_serve_la_password(self, client, db, email_inviate, whatsapp_inviati):
        await _fino_al_codice_whatsapp(client, email_inviate)
        inviati_prima = len(whatsapp_inviati)
        resp = await _correggi(client, password="non-è-lei-12345")
        assert resp.status_code == 401
        assert len(whatsapp_inviati) == inviati_prima, "nessun codice al numero di chi prova"
        assert (await _account(db)).phone_pending is None

    async def test_prima_l_email(self, client, email_inviate, whatsapp_inviati):
        await _registra(client, email_inviate)
        resp = await _correggi(client)
        assert resp.status_code == 400
        assert whatsapp_inviati == []

    async def test_non_un_numero_gia_confermato(self, client, email_inviate, whatsapp_inviati):
        """Spostare conferme e promemoria su un altro telefono con la sola
        password è un'altra cosa: la fa il salone, dalla scheda."""
        await _fino_al_codice_whatsapp(client, email_inviate)
        await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": whatsapp_inviati[-1][1]})
        resp = await _correggi(client)
        assert resp.status_code == 409

    async def test_un_numero_che_non_e_un_numero(self, client, email_inviate, whatsapp_inviati):
        await _fino_al_codice_whatsapp(client, email_inviate)
        assert (await _correggi(client, phone="12")).status_code == 422
