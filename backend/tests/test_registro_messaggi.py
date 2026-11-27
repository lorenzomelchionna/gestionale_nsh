"""Registro dei messaggi: ogni invio lascia una riga, e la riga dice la verità.

Quello che i test tengono fermo:
  - ogni messaggio che parte — WhatsApp template, testo libero, risposta in
    chat, email — scrive una riga col tipo giusto, la cliente, l'appuntamento,
    il SID del fornitore; anche quando l'invio fallisce, con l'errore;
  - codici di verifica, link di reset e codici dei buoni **non** finiscono nel
    registro: sono chiavi d'accesso;
  - lo stato di consegna arriva da Twilio solo con la firma giusta, va solo
    avanti (un «letto» arrivato prima di «consegnato» non torna indietro) e
    traduce i codici d'errore che si sono visti davvero;
  - la pagina filtra per cliente, numero scritto come capita, giorno del
    salone, canale, tipo; e la vede solo l'admin;
  - dopo sei mesi le righe se ne vanno;
  - un registro rotto non ferma un promemoria.
"""
import json
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.appointment import Appointment, AppointmentStatus
from app.models.client import Client
from app.models.registro_messaggi import RegistroMessaggio
from app.services import registro
from app.utils import email as email_util
from app.utils import whatsapp
from app.utils.tempo import istante
from app.utils.twilio_webhook import expected_signature
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

STATO = "/api/public/whatsapp/stato"
ELENCO = "/api/admin/registro-messaggi"
TOKEN = "test-twilio-auth-token"


class FintoTwilio:
    """Al posto di `httpx.AsyncClient` dentro `utils.whatsapp`."""

    def __init__(self, stato=201, sid="SM123"):
        self.stato, self.sid, self.dati = stato, sid, []

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        self.dati.append(kw["data"])
        finto = self

        class Risposta:
            status_code = finto.stato
            text = '{"message": "rifiutato"}'

            def json(self):
                return {"sid": finto.sid}

        return Risposta()


@pytest.fixture
def twilio(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC-test")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "whatsapp:+390825000000")
    monkeypatch.setattr(settings, "TWILIO_TEMPLATE_CONFERMA", "HX-conferma")
    monkeypatch.setattr(settings, "TWILIO_STATUS_CALLBACK_URL", "https://backend.test/api/public/whatsapp/stato")
    finto = FintoTwilio()
    monkeypatch.setattr(whatsapp.httpx, "AsyncClient", finto)
    return finto


@pytest.fixture
def brevo(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "chiave-di-prova")

    async def finto(to, subject, html_body, allegati=None):
        return "<id-brevo@test>"

    monkeypatch.setattr(email_util, "_send_via_brevo", finto)


async def _righe(db) -> list[RegistroMessaggio]:
    db.expire_all()
    return list((await db.execute(select(RegistroMessaggio).order_by(RegistroMessaggio.id))).scalars())


async def _appuntamento(db, client_account, collaborator, fra=timedelta(days=2)) -> Appointment:
    cliente = (await db.execute(
        select(Client).where(Client.account_id == client_account.id)
    )).scalar_one()
    quando = datetime.now(timezone.utc) + fra
    a = Appointment(
        client_id=cliente.id, collaborator_id=collaborator.id,
        start_time=quando, end_time=quando + timedelta(minutes=30),
        status=AppointmentStatus.confirmed,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a, ["client", "collaborator"])
    return a


async def _riga(db, **campi) -> RegistroMessaggio:
    r = RegistroMessaggio(**{"canale": "whatsapp", "tipo": "conferma", "destinatario": "+393330000002",
                             "stato": "inviato", **campi})
    db.add(r)
    await db.commit()
    return r


# ── Si scrive a ogni invio ──────────────────────────────────────────

class TestCosaFiniscePelRegistro:
    async def test_conferma_su_whatsapp_ed_email(
        self, db, twilio, brevo, booking_config, client_account, collaborator, monkeypatch
    ):
        from app.utils import notifications

        monkeypatch.setattr(notifications, "_wa_enabled", lambda cfg: True)
        appt = await _appuntamento(db, client_account, collaborator)
        id_cliente, id_appuntamento = appt.client_id, appt.id
        await notifications.notify_booking_confirmation(db, appt)

        righe = await _righe(db)
        per_canale = {r.canale: r for r in righe}
        assert set(per_canale) == {"email", "whatsapp"}
        for r in righe:
            assert r.tipo == "conferma"
            assert r.client_id == id_cliente
            assert r.appointment_id == id_appuntamento
            assert r.stato == "inviato"
        wa = per_canale["whatsapp"]
        assert wa.formato == "template"
        assert wa.id_fornitore == "SM123"
        assert wa.testo.startswith("Ciao Giulia! La tua prenotazione da New Style Hair")
        assert wa.destinatario == "+393330000002"
        em = per_canale["email"]
        assert em.id_fornitore == "<id-brevo@test>"
        assert em.oggetto and em.testo and "<" not in em.testo, "il testo è leggibile, non HTML"

    async def test_twilio_riceve_il_callback_dello_stato(self, twilio):
        with registro.invio("promemoria"):
            await whatsapp.send_whatsapp("+393330000002", "ciao")
        assert twilio.dati[-1]["StatusCallback"] == "https://backend.test/api/public/whatsapp/stato"

    async def test_senza_callback_configurato_non_lo_manda(self, twilio, monkeypatch):
        monkeypatch.setattr(settings, "TWILIO_STATUS_CALLBACK_URL", "")
        with registro.invio("promemoria"):
            await whatsapp.send_whatsapp("+393330000002", "ciao")
        assert "StatusCallback" not in twilio.dati[-1]

    async def test_invio_rifiutato_da_twilio_resta_con_l_errore(self, db, twilio):
        twilio.stato = 400
        with registro.invio("promemoria", client_id=None):
            with pytest.raises(RuntimeError):
                await whatsapp.send_whatsapp("+393330000002", "ciao")
        (r,) = await _righe(db)
        assert r.stato == "errore"
        assert "400" in r.errore

    async def test_email_senza_canale_configurato_resta_come_errore(self, db, monkeypatch):
        monkeypatch.setattr(settings, "BREVO_API_KEY", "")
        monkeypatch.setattr(settings, "SMTP_USER", "")
        with registro.invio("compleanno"):
            await email_util.send_email("cliente@example.com", "Auguri", "<p>Auguri!</p>")
        (r,) = await _righe(db)
        assert (r.canale, r.stato, r.tipo) == ("email", "errore", "compleanno")
        assert r.testo == "Auguri!"

    async def test_risposta_in_chat(self, db, twilio, monkeypatch):
        from app.services import chat as chat_service
        from app.models.chat import Conversation

        monkeypatch.setattr(chat_service.httpx, "AsyncClient", twilio)
        conv = Conversation(phone="+393330000002")
        db.add(conv)
        await db.commit()
        await chat_service.send_reply(db, conv, "Sì, c'è posto alle 15")
        (r,) = await _righe(db)
        assert (r.tipo, r.formato, r.testo, r.id_fornitore) == (
            "risposta_chat", "testo_libero", "Sì, c'è posto alle 15", "SM123",
        )


class TestChiaviDAccesso:
    """I segreti partono, ma nel registro resta solo che sono partiti."""

    async def test_il_codice_di_verifica_non_si_salva(self, db, twilio, monkeypatch):
        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_VERIFICA", "HX-verifica")
        with registro.invio("codice_verifica"):
            await whatsapp.send_verification_code_whatsapp("+393330000002", "482913")
        (r,) = await _righe(db)
        assert r.tipo == "codice_verifica"
        assert r.testo is None
        assert "482913" not in json.dumps({k: str(v) for k, v in vars(r).items()})

    async def test_il_link_di_reset_non_si_salva(self, db, brevo):
        with registro.invio("reset_password"):
            await email_util.send_password_reset_email(
                "cliente@example.com", "Giulia", "https://x.test/booking/reset-password#token=SEGRETO",
            )
        (r,) = await _righe(db)
        assert r.testo is None
        assert "SEGRETO" not in (r.oggetto or "")

    async def test_un_invio_senza_tipo_non_salva_il_testo(self, db, twilio):
        """Un tipo di messaggio aggiunto domani senza dichiararsi: parte, ma
        il testo resta fuori finché qualcuno non decide che è sicuro."""
        await whatsapp.send_whatsapp("+393330000002", "qualcosa di nuovo")
        (r,) = await _righe(db)
        assert (r.tipo, r.testo) == ("altro", None)

    async def test_un_tipo_inventato_e_rifiutato(self):
        with pytest.raises(ValueError):
            with registro.invio("tipo_che_non_esiste"):
                pass


class TestRegistroRotto:
    async def test_un_promemoria_parte_anche_se_il_registro_non_si_scrive(self, twilio, monkeypatch):
        class Rotta:
            def __call__(self):
                raise RuntimeError("database giù")

        monkeypatch.setattr(registro, "_fabbrica", Rotta())
        with registro.invio("promemoria"):
            await whatsapp.send_whatsapp("+393330000002", "ciao")
        assert twilio.dati, "il messaggio è partito comunque"


# ── Stato di consegna ───────────────────────────────────────────────

def _firmata(params: dict[str, str]) -> dict[str, str]:
    return {"X-Twilio-Signature": expected_signature(f"http://test{STATO}", params, TOKEN)}


class TestStatoDiConsegna:
    @pytest.fixture(autouse=True)
    def token(self, monkeypatch):
        monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TOKEN)

    async def _manda(self, client, sid, stato, codice=None):
        params = {"MessageSid": sid, "MessageStatus": stato}
        if codice:
            params["ErrorCode"] = codice
        return await client.post(STATO, data=params, headers=_firmata(params))

    async def test_consegnato_poi_letto(self, client, db):
        r = await _riga(db, id_fornitore="SMa")
        assert (await self._manda(client, "SMa", "delivered")).status_code == 204
        await db.refresh(r)
        assert r.stato == "consegnato"
        await self._manda(client, "SMa", "read")
        await db.refresh(r)
        assert r.stato == "letto"
        assert r.stato_aggiornato_il is not None

    async def test_non_torna_indietro(self, client, db):
        r = await _riga(db, id_fornitore="SMb")
        await self._manda(client, "SMb", "read")
        await self._manda(client, "SMb", "delivered")
        await db.refresh(r)
        assert r.stato == "letto"

    async def test_non_consegnato_col_motivo_in_parole(self, client, db):
        r = await _riga(db, id_fornitore="SMc")
        await self._manda(client, "SMc", "undelivered", "63024")
        await db.refresh(r)
        assert r.stato == "non_consegnato"
        assert r.errore == "63024: Destinatario non valido per WhatsApp"

    async def test_senza_firma_rifiutato(self, client, db):
        r = await _riga(db, id_fornitore="SMd")
        resp = await client.post(STATO, data={"MessageSid": "SMd", "MessageStatus": "read"})
        assert resp.status_code == 403
        await db.refresh(r)
        assert r.stato == "inviato"

    async def test_firma_di_altri_parametri_rifiutata(self, client, db):
        await _riga(db, id_fornitore="SMe")
        firmati = {"MessageSid": "SMe", "MessageStatus": "delivered"}
        mandati = {"MessageSid": "SMe", "MessageStatus": "read"}
        resp = await client.post(STATO, data=mandati, headers=_firmata(firmati))
        assert resp.status_code == 403

    async def test_sid_sconosciuto_non_fa_ritentare_twilio(self, client):
        assert (await self._manda(client, "SMnessuno", "delivered")).status_code == 204


# ── La pagina ───────────────────────────────────────────────────────

class TestPagina:
    async def test_filtri(self, client, db, admin_tokens, client_account, other_client):
        giulia = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()
        ieri = istante(date.today() - timedelta(days=1), time(10, 0))
        await _riga(db, client_id=giulia.id, destinatario="+393330000002", tipo="conferma")
        await _riga(db, client_id=other_client.id, destinatario="+393330000003", tipo="promemoria")
        await _riga(db, canale="email", destinatario="altra@nsh-test.it", client_id=other_client.id,
                    tipo="compleanno", creato_il=ieri)

        async def cerca(**params):
            r = await client.get(ELENCO, headers=auth(admin_tokens), params=params)
            assert r.status_code == 200, r.text
            return r.json()

        tutto = await cerca()
        assert tutto["total"] == 3
        assert tutto["items"][0]["creato_il"] >= tutto["items"][-1]["creato_il"], "i più recenti prima"

        per_nome = await cerca(cerca="giulia")
        assert [i["cliente_nome"] for i in per_nome["items"]] == ["Giulia Test"]
        assert per_nome["items"][0]["tipo_etichetta"] == "Conferma appuntamento"

        per_numero = await cerca(cerca="333 000 0003")
        assert {i["destinatario"] for i in per_numero["items"]} == {"+393330000003"}

        assert (await cerca(canale="email"))["total"] == 1
        assert (await cerca(tipo="promemoria"))["total"] == 1
        giorno = (date.today() - timedelta(days=1)).isoformat()
        solo_ieri = await cerca(dal=giorno, al=giorno)
        assert [i["tipo"] for i in solo_ieri["items"]] == ["compleanno"]
        assert (await cerca(client_id=giulia.id))["total"] == 1

        # Anche un numero salvato con gli spazi si trova per cifre.
        await _riga(db, destinatario="+39 347 555 1234", tipo="promemoria")
        con_spazi = await cerca(cerca="3475551234")
        assert [i["destinatario"] for i in con_spazi["items"]] == ["+39 347 555 1234"]

    async def test_tipi(self, client, admin_tokens):
        r = await client.get(f"{ELENCO}/tipi", headers=auth(admin_tokens))
        assert r.json()["promemoria"] == "Promemoria"

    async def test_solo_admin(self, client, collab_tokens, client_tokens):
        assert (await client.get(ELENCO, headers=auth(collab_tokens))).status_code == 403
        assert (await client.get(ELENCO, headers=auth(client_tokens))).status_code in (401, 403)
        assert (await client.get(ELENCO)).status_code == 401


class TestSeiMesi:
    async def test_le_righe_vecchie_se_ne_vanno(self, db):
        adesso = datetime.now(timezone.utc)
        vecchia = await _riga(db, creato_il=adesso - timedelta(days=registro.CONSERVAZIONE_GIORNI + 1))
        recente = await _riga(db, creato_il=adesso - timedelta(days=registro.CONSERVAZIONE_GIORNI - 1))
        cancellate = await registro.pulisci(db, adesso)
        await db.commit()
        assert cancellate == 1
        rimaste = {r.id for r in await _righe(db)}
        assert rimaste == {recente.id}
        assert vecchia.id not in rimaste
