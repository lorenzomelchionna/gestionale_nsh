"""Chat WhatsApp: allegati, e chi c'è dietro un numero.

Fino al 2026-09-25 il webhook salvava un messaggio solo se aveva del testo:
una foto o un vocale senza didascalia sparivano per intero — tre così, uno
di una cliente, nei primi giorni sul fisso. Questi test fissano che arrivino,
che si vedano, e che il file passi dal backend senza che la pagina veda mai
l'URL di Twilio (che con le credenziali dell'account apre il file).

In fondo, il nome: quello del profilo WhatsApp si aggiorna, e la scheda
cliente si collega anche a una conversazione nata prima di lei.
"""
import pytest
from sqlalchemy import select

from app.models.chat import ChatMessage, Conversation
from app.models.client import Client
from app.services import chat as chat_service
from app.utils.twilio_webhook import expected_signature
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

WEBHOOK = "/api/public/whatsapp/webhook"
TEST_AUTH_TOKEN = "test-twilio-auth-token"
TWILIO_MEDIA = "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MM1/Media/ME1"
PHONE = "+393471234567"


@pytest.fixture(autouse=True)
def twilio_configured(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TEST_AUTH_TOKEN)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "")
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "")


async def _arriva(client, sid="MM1", body="", profilo="Giulia", media=None):
    params = {
        "From": f"whatsapp:{PHONE}",
        "Body": body,
        "MessageSid": sid,
        "ProfileName": profilo,
        "NumMedia": str(len(media or [])),
    }
    for i, (url, tipo) in enumerate(media or []):
        params[f"MediaUrl{i}"] = url
        params[f"MediaContentType{i}"] = tipo
    firma = expected_signature(f"http://test{WEBHOOK}", params, TEST_AUTH_TOKEN)
    r = await client.post(WEBHOOK, data=params, headers={"X-Twilio-Signature": firma})
    assert r.status_code == 200, r.text


async def _conversazione(client, admin_tokens) -> dict:
    lista = (await client.get("/api/admin/chat/conversations", headers=auth(admin_tokens))).json()
    assert len(lista) == 1
    return lista[0]


class TestArrivano:
    async def test_foto_senza_testo_viene_salvata(self, client, db, admin_tokens):
        await _arriva(client, media=[(TWILIO_MEDIA, "image/jpeg")])

        msg = (await db.execute(select(ChatMessage))).scalar_one()
        assert msg.body == ""
        assert msg.media == [{"url": TWILIO_MEDIA, "content_type": "image/jpeg"}]

    async def test_la_didascalia_resta_col_suo_allegato(self, client, db):
        await _arriva(client, body="Così va bene?", media=[(TWILIO_MEDIA, "image/png")])
        msg = (await db.execute(select(ChatMessage))).scalar_one()
        assert msg.body == "Così va bene?"
        assert len(msg.media) == 1

    async def test_un_url_che_non_e_di_twilio_non_si_salva(self, client, db):
        """Il backend scaricherà quell'URL con le credenziali dell'account:
        non deve poter puntare altrove."""
        await _arriva(client, media=[("https://altrove.example/x.jpg", "image/jpeg")])
        assert (await db.execute(select(ChatMessage))).scalars().all() == []

    async def test_la_pagina_non_vede_l_url(self, client, admin_tokens):
        await _arriva(client, media=[(TWILIO_MEDIA, "audio/ogg")])
        conv = await _conversazione(client, admin_tokens)
        dettaglio = await client.get(
            f"/api/admin/chat/conversations/{conv['id']}", headers=auth(admin_tokens)
        )
        assert dettaglio.json()["messages"][0]["media"] == [{"index": 0, "content_type": "audio/ogg"}]
        assert "api.twilio.com" not in dettaglio.text

    @pytest.mark.parametrize("tipo, etichetta", [
        ("image/jpeg", "📷 Foto"),
        ("audio/ogg", "🎤 Messaggio vocale"),
        ("video/mp4", "🎬 Video"),
        ("application/pdf", "📎 Allegato"),
    ])
    async def test_anteprima_nell_elenco(self, client, admin_tokens, tipo, etichetta):
        await _arriva(client, media=[(TWILIO_MEDIA, tipo)])
        assert (await _conversazione(client, admin_tokens))["last_message_preview"] == etichetta


class TestSiVedono:
    async def _id_messaggio(self, client, db, tipo):
        await _arriva(client, media=[(TWILIO_MEDIA, tipo)])
        return (await db.execute(select(ChatMessage))).scalar_one().id

    async def test_il_file_passa_dal_backend(self, client, db, admin_tokens, monkeypatch):
        chiesti = []

        async def finto(url):
            chiesti.append(url)
            return b"\xff\xd8JPEG", "image/jpeg"

        monkeypatch.setattr("app.api.admin.chat.scarica_allegato", finto)
        mid = await self._id_messaggio(client, db, "image/jpeg")

        r = await client.get(f"/api/admin/chat/messages/{mid}/media/0", headers=auth(admin_tokens))
        assert r.status_code == 200
        assert r.content == b"\xff\xd8JPEG"
        assert r.headers["content-type"] == "image/jpeg"
        assert r.headers["content-disposition"] == "inline"
        assert chiesti == [TWILIO_MEDIA]

    async def test_un_html_si_scarica_non_si_apre(self, client, db, admin_tokens, monkeypatch):
        async def finto(url):
            return b"<script>alert(1)</script>", "text/html"

        monkeypatch.setattr("app.api.admin.chat.scarica_allegato", finto)
        mid = await self._id_messaggio(client, db, "text/html")

        r = await client.get(f"/api/admin/chat/messages/{mid}/media/0", headers=auth(admin_tokens))
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["content-disposition"] == "attachment"

    async def test_indice_inesistente(self, client, db, admin_tokens):
        mid = await self._id_messaggio(client, db, "image/jpeg")
        r = await client.get(f"/api/admin/chat/messages/{mid}/media/1", headers=auth(admin_tokens))
        assert r.status_code == 404

    async def test_twilio_non_risponde(self, client, db, admin_tokens, monkeypatch):
        async def rotto(url):
            raise chat_service.AllegatoNonDisponibile("giù")

        monkeypatch.setattr("app.api.admin.chat.scarica_allegato", rotto)
        mid = await self._id_messaggio(client, db, "image/jpeg")
        r = await client.get(f"/api/admin/chat/messages/{mid}/media/0", headers=auth(admin_tokens))
        assert r.status_code == 502

    async def test_la_cliente_non_ci_arriva(self, client, db, client_tokens):
        mid = await self._id_messaggio(client, db, "image/jpeg")
        r = await client.get(f"/api/admin/chat/messages/{mid}/media/0", headers=auth(client_tokens))
        assert r.status_code == 401

    async def test_il_download_rifiuta_url_non_twilio(self, monkeypatch):
        """Rifiutato prima di aprire qualunque connessione: le credenziali
        dell'account non devono partire verso un altro indirizzo."""
        from app.config import settings

        class NessunaConnessione:
            def __init__(self, *a, **kw):
                raise AssertionError("il download non doveva nemmeno partire")

        monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACtest")
        monkeypatch.setattr(chat_service.httpx, "AsyncClient", NessunaConnessione)
        with pytest.raises(chat_service.AllegatoNonDisponibile):
            await chat_service.scarica_allegato("https://altrove.example/x.jpg")


class TestIlNome:
    async def test_il_nome_whatsapp_si_aggiorna(self, client, db):
        await _arriva(client, sid="SM1", body="ciao", profilo="Giuli")
        await _arriva(client, sid="SM2", body="ci sono", profilo="Giulia Bianchi")
        conv = (await db.execute(select(Conversation))).scalar_one()
        await db.refresh(conv)
        assert conv.contact_name == "Giulia Bianchi"

    async def test_la_scheda_si_collega_anche_dopo(self, client, db, admin_tokens):
        """Ha scritto prima che il salone avesse una scheda per lei."""
        await _arriva(client, sid="SM1", body="ciao", profilo="Giuli")
        assert (await _conversazione(client, admin_tokens))["display_name"] == "Giuli"

        db.add(Client(first_name="Giulia", last_name="Bianchi", phone=PHONE))
        await db.commit()
        await _arriva(client, sid="SM2", body="sono io")

        assert (await _conversazione(client, admin_tokens))["display_name"] == "Giulia Bianchi"

    async def test_due_schede_collo_stesso_numero_nessuna_scelta(self, client, db, admin_tokens):
        """Madre e figlia col fisso di casa: meglio il nome WhatsApp di chi
        scrive che quello giusto una volta su due."""
        db.add(Client(first_name="Anna", last_name="Bianchi", phone=PHONE))
        db.add(Client(first_name="Giulia", last_name="Bianchi", phone=PHONE))
        await db.commit()
        await _arriva(client, sid="SM1", body="ciao", profilo="Giuli")
        conv = await _conversazione(client, admin_tokens)
        assert conv["client_id"] is None
        assert conv["display_name"] == "Giuli"

    async def test_una_scheda_disattivata_non_da_il_nome(self, client, db, admin_tokens):
        db.add(Client(first_name="Vecchia", last_name="Scheda", phone=PHONE, is_active=False))
        await db.commit()
        await _arriva(client, sid="SM1", body="ciao", profilo="Giuli")
        assert (await _conversazione(client, admin_tokens))["display_name"] == "Giuli"


class TestIlNomeSubito:
    """La scheda nasce dopo che la persona ha scritto: la chat prende il suo
    nome **subito**, non al prossimo messaggio — che può arrivare fra un mese."""

    async def _chat_senza_scheda(self, client, admin_tokens):
        await _arriva(client, sid="SM1", body="ciao, vorrei prenotare", profilo="Giuli")
        assert (await _conversazione(client, admin_tokens))["display_name"] == "Giuli"

    async def test_scheda_creata_dall_admin(self, client, admin_tokens):
        await self._chat_senza_scheda(client, admin_tokens)
        r = await client.post("/api/admin/clients", headers=auth(admin_tokens), json={
            "first_name": "Giulia", "last_name": "Bianchi", "phone": "347 123 4567",
        })
        assert r.status_code == 201, r.text
        assert (await _conversazione(client, admin_tokens))["display_name"] == "Giulia Bianchi"

    async def test_numero_aggiunto_dopo(self, client, db, admin_tokens):
        await self._chat_senza_scheda(client, admin_tokens)
        senza = Client(first_name="Giulia", last_name="Bianchi")
        db.add(senza)
        await db.commit()
        r = await client.put(f"/api/admin/clients/{senza.id}", headers=auth(admin_tokens), json={
            "phone": "+39 347 1234567",
        })
        assert r.status_code == 200, r.text
        assert (await _conversazione(client, admin_tokens))["display_name"] == "Giulia Bianchi"

    async def test_seconda_scheda_con_lo_stesso_numero_non_collega(self, client, db, admin_tokens):
        await self._chat_senza_scheda(client, admin_tokens)
        db.add(Client(first_name="Anna", last_name="Bianchi", phone=PHONE))
        await db.commit()
        # Con due schede sul numero — madre e figlia — non si sceglie.
        r = await client.post("/api/admin/clients", headers=auth(admin_tokens), json={
            "first_name": "Giulia", "last_name": "Bianchi", "phone": PHONE,
        })
        assert r.status_code == 201
        assert (await _conversazione(client, admin_tokens))["client_id"] is None

    async def test_la_chat_segue_il_numero_quando_passa_ad_altri(self, client, db, admin_tokens):
        """La scheda collegata il numero non ce l'ha più: ora è di un'altra."""
        prima = Client(first_name="Giulia", last_name="Bianchi", phone=PHONE)
        db.add(prima)
        await db.commit()
        await _arriva(client, sid="SM1", body="ciao")
        assert (await _conversazione(client, admin_tokens))["client_id"] == prima.id

        await client.put(f"/api/admin/clients/{prima.id}", headers=auth(admin_tokens), json={"phone": "+393330000999"})
        r = await client.post("/api/admin/clients", headers=auth(admin_tokens), json={
            "first_name": "Nuova", "last_name": "Titolare", "phone": PHONE,
        })
        assert (await _conversazione(client, admin_tokens))["client_id"] == r.json()["id"]

    async def test_resta_a_chi_ha_ancora_il_numero(self, client, db, admin_tokens):
        prima = Client(first_name="Giulia", last_name="Bianchi", phone=PHONE)
        db.add(prima)
        await db.commit()
        await _arriva(client, sid="SM1", body="ciao")
        assert (await _conversazione(client, admin_tokens))["client_id"] == prima.id

        altra = Client(first_name="Altra", last_name="Persona")
        db.add(altra)
        await db.commit()
        await client.put(f"/api/admin/clients/{altra.id}", headers=auth(admin_tokens), json={"phone": PHONE})
        assert (await _conversazione(client, admin_tokens))["client_id"] == prima.id

    async def test_prenotazione_senza_account(
        self, client, admin_tokens, booking_config, collaborator, service, monkeypatch
    ):
        from datetime import date, timedelta
        from tests.conftest import giorno_lavorativo
        import app.api.public.guest as guest_api

        codici = []

        async def finto(to_phone, code):
            codici.append(code)

        monkeypatch.setattr(guest_api, "send_verification_code_whatsapp", finto)
        await self._chat_senza_scheda(client, admin_tokens)

        giorno = giorno_lavorativo(date.today() + timedelta(days=2))
        orari = (await client.get("/api/public/availability", params={
            "service_id": service.id, "collaborator_id": collaborator.id,
            "target_date": giorno.isoformat(),
        })).json()
        chi = {"first_name": "Giulia", "last_name": "Bianchi", "phone": "347 123 4567"}
        await client.post("/api/public/guest/code", json=chi)
        r = await client.post("/api/public/guest/appointments", json={
            **chi, "code": codici[-1], "collaborator_id": collaborator.id,
            "start_time": orari[0], "service_ids": [service.id],
        })
        assert r.status_code == 201, r.text
        assert (await _conversazione(client, admin_tokens))["display_name"] == "Giulia Bianchi"
