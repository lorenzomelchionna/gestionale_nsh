"""
WhatsApp inbox: webhook authenticity, threading, and the reply window.

The webhook is the only unauthenticated write path in the app, so its signature
check gets the same scrutiny as the auth boundaries.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.chat import Conversation, MessageDirection, MessageStatus
from app.services.chat import REPLY_WINDOW_HOURS, normalise_phone
from app.utils.twilio_webhook import expected_signature
from tests.conftest import auth

WEBHOOK = "/api/public/whatsapp/webhook"
# Must match the token the app is configured with during tests.
TEST_AUTH_TOKEN = "test-twilio-auth-token"


@pytest.fixture(autouse=True)
def twilio_configured(monkeypatch):
    """Give the app a known auth token so signatures can be computed here."""
    from app.config import settings

    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TEST_AUTH_TOKEN)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "")  # keep sending stubbed
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "")


def signed(params: dict[str, str], url: str = f"http://test{WEBHOOK}") -> dict[str, str]:
    return {"X-Twilio-Signature": expected_signature(url, params, TEST_AUTH_TOKEN)}


def inbound_params(body="Ciao, avete posto giovedì?", phone="whatsapp:+393331234567", sid="SM1"):
    return {
        "From": phone,
        "Body": body,
        "MessageSid": sid,
        "ProfileName": "Giulia",
    }


class TestIlTettoSulCorpo:
    """Quanto lavoro l'endpoint fa per uno sconosciuto prima di poterlo cacciare.

    La firma si calcola sui parametri, quindi vanno letti prima di poterla
    verificare: un pezzo di lavoro per chiunque bussi è inevitabile qui. La
    domanda non è *se*, è *quanto* — e fino al 2026-08-05 la risposta era
    «tutto quello che manda».

    `request.form()` accetta `max_fields` e `max_part_size` e li ignora in
    silenzio sui corpi urlencoded (PYSEC-2026-249). Misurato prima della
    correzione: 200.000 campi, 1,8 MB, parsati per intero prima del 403, senza
    credenziali e senza limite di tentativi.
    """

    async def test_un_corpo_enorme_viene_rifiutato(self, client, db):
        gonfio = {f"campo{i}": "x" for i in range(200_000)}

        resp = await client.post(WEBHOOK, data=gonfio)

        assert resp.status_code == 413
        assert (await db.execute(select(Conversation))).scalars().all() == []

    async def test_il_corpo_enorme_non_viene_nemmeno_parsato(self, client, monkeypatch):
        """Il punto non è il codice di risposta, è il lavoro risparmiato.

        Rifiutare *dopo* aver parsato darebbe lo stesso 413 e non servirebbe a
        niente: il costo è il parsing, non la risposta. Questo test guarda che
        il parser non venga proprio interpellato.
        """
        import starlette.requests

        chiamate = []
        originale = starlette.requests.Request.form

        def spia(self, *a, **kw):
            chiamate.append("form")
            return originale(self, *a, **kw)

        monkeypatch.setattr(starlette.requests.Request, "form", spia)

        resp = await client.post(
            WEBHOOK, data={f"campo{i}": "x" for i in range(200_000)}
        )

        assert resp.status_code == 413
        assert chiamate == [], (
            "il corpo è stato parsato prima di rifiutarlo: il tetto non serve a niente"
        )

    async def test_un_messaggio_vero_passa_lo_stesso(self, client, db):
        """L'altra metà: un tetto che rifiuta anche i messaggi legittimi è
        peggio del problema che risolve, perché perde le richieste delle
        clienti in silenzio.

        Il caso più grosso plausibile: testo al limite dei 4096 caratteri che
        WhatsApp consente, più una decina di URL di media.
        """
        params = inbound_params(body="a" * 4096)
        params.update({f"MediaUrl{i}": f"https://api.twilio.com/media/{i}" for i in range(10)})
        params.update({f"MediaContentType{i}": "image/jpeg" for i in range(10)})

        resp = await client.post(WEBHOOK, data=params, headers=signed(params))

        assert resp.status_code == 200, resp.text
        assert (await db.execute(select(Conversation))).scalars().all(), (
            "un messaggio legittimo è stato perso"
        )

    async def test_accenti_ed_emoji_arrivano_interi(self, client, db):
        """Il tetto ha cambiato *come* si legge il corpo, non come si
        interpreta: i byte limitati tornano al parser di starlette invece di
        essere decodificati a mano.

        Conta perché la firma si calcola su questi valori: qualunque
        differenza di decodifica si manifesterebbe come messaggi veri
        rifiutati, cioè il guasto peggiore possibile per questo endpoint.
        """
        testo = "Ciao! Sposto l'appuntamento di lunedì 💇 (taglio & piega) — ok?"
        params = inbound_params(body=testo)

        resp = await client.post(WEBHOOK, data=params, headers=signed(params))

        assert resp.status_code == 200, resp.text
        from app.models.chat import ChatMessage

        salvato = (await db.execute(select(ChatMessage))).scalars().all()
        assert [m.body for m in salvato] == [testo]

    async def test_il_tetto_lascia_margine_al_caso_vero(self):
        """Il numero, non la sua applicazione. Se un giorno qualcuno lo
        abbassasse per prudenza, questo dice qual era il ragionamento."""
        from app.api.public.whatsapp import MAX_WEBHOOK_BYTES

        # ~20 parametri, testo al massimo che WhatsApp consente, 10 media.
        caso_grosso = 4096 + 10 * 120 + 20 * 40
        assert MAX_WEBHOOK_BYTES > caso_grosso * 5


class TestWebhookAuthenticity:
    async def test_unsigned_request_is_rejected(self, client, db):
        resp = await client.post(WEBHOOK, data=inbound_params())
        assert resp.status_code == 403

        stored = (await db.execute(select(Conversation))).scalars().all()
        assert stored == [], "un messaggio non firmato non deve essere salvato"

    async def test_wrong_signature_is_rejected(self, client):
        resp = await client.post(
            WEBHOOK, data=inbound_params(), headers={"X-Twilio-Signature": "nope"}
        )
        assert resp.status_code == 403

    async def test_signature_over_different_params_is_rejected(self, client):
        """A signature valid for one payload must not authenticate another."""
        headers = signed(inbound_params(body="originale"))
        resp = await client.post(WEBHOOK, data=inbound_params(body="manomesso"), headers=headers)
        assert resp.status_code == 403

    async def test_signed_request_is_accepted(self, client, db):
        params = inbound_params()
        resp = await client.post(WEBHOOK, data=params, headers=signed(params))
        assert resp.status_code == 200

        conv = (await db.execute(select(Conversation))).scalar_one()
        assert conv.phone == "+393331234567"
        assert conv.unread_count == 1

    async def test_rejected_when_no_auth_token_configured(self, client, monkeypatch):
        """With no shared secret there is nothing to verify — refuse rather than trust."""
        from app.config import settings

        monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
        params = inbound_params()
        resp = await client.post(WEBHOOK, data=params, headers=signed(params))
        assert resp.status_code == 403


class TestThreading:
    async def test_messages_from_same_number_share_a_conversation(self, client, db):
        for i, text in enumerate(["primo", "secondo"], start=1):
            params = inbound_params(body=text, sid=f"SM{i}")
            resp = await client.post(WEBHOOK, data=params, headers=signed(params))
            assert resp.status_code == 200

        convs = (await db.execute(select(Conversation))).scalars().all()
        assert len(convs) == 1
        assert convs[0].unread_count == 2

    async def test_duplicate_delivery_is_ignored(self, client, db):
        """Twilio retries webhooks; the same SID must not be stored twice."""
        params = inbound_params(sid="SM-DUP")
        for _ in range(2):
            resp = await client.post(WEBHOOK, data=params, headers=signed(params))
            assert resp.status_code == 200

        conv = (await db.execute(select(Conversation))).scalar_one()
        assert conv.unread_count == 1, "il retry ha duplicato il messaggio"

    async def test_known_client_is_linked_to_the_thread(self, client, db, other_client):
        params = inbound_params(phone=f"whatsapp:{other_client.phone}")
        await client.post(WEBHOOK, data=params, headers=signed(params))

        conv = (await db.execute(select(Conversation))).scalar_one()
        assert conv.client_id == other_client.id

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("whatsapp:+393331234567", "+393331234567"),
            ("+39 333 1234567", "+393331234567"),
            ("393331234567", "+393331234567"),
        ],
    )
    def test_phone_normalisation(self, raw, expected):
        assert normalise_phone(raw) == expected


class TestInboxAccess:
    async def test_collaborator_can_read_and_reply(self, client, db, collab_tokens):
        params = inbound_params()
        await client.post(WEBHOOK, data=params, headers=signed(params))

        listing = await client.get("/api/admin/chat/conversations", headers=auth(collab_tokens))
        assert listing.status_code == 200, "il collaboratore deve poter leggere la chat"
        conv_id = listing.json()[0]["id"]

        reply = await client.post(
            f"/api/admin/chat/conversations/{conv_id}/reply",
            headers=auth(collab_tokens),
            json={"body": "Certo, giovedì alle 15 va bene"},
        )
        assert reply.status_code == 200
        assert reply.json()["direction"] == "outbound"

    async def test_client_token_cannot_read_the_inbox(self, client, client_tokens):
        resp = await client.get("/api/admin/chat/conversations", headers=auth(client_tokens))
        assert resp.status_code == 401

    async def test_opening_a_thread_marks_it_read(self, client, admin_tokens):
        params = inbound_params()
        await client.post(WEBHOOK, data=params, headers=signed(params))

        listing = await client.get("/api/admin/chat/conversations", headers=auth(admin_tokens))
        conv_id = listing.json()[0]["id"]
        assert listing.json()[0]["unread_count"] == 1

        detail = await client.get(
            f"/api/admin/chat/conversations/{conv_id}", headers=auth(admin_tokens)
        )
        assert detail.status_code == 200
        assert detail.json()["unread_count"] == 0

    async def test_display_name_prefers_the_client_record(
        self, client, admin_tokens, other_client
    ):
        params = inbound_params(phone=f"whatsapp:{other_client.phone}")
        await client.post(WEBHOOK, data=params, headers=signed(params))

        listing = await client.get("/api/admin/chat/conversations", headers=auth(admin_tokens))
        name = listing.json()[0]["display_name"]
        assert other_client.first_name in name


class TestReplyWindow:
    async def test_reply_allowed_inside_the_window(self, client, admin_tokens):
        params = inbound_params()
        await client.post(WEBHOOK, data=params, headers=signed(params))

        listing = await client.get("/api/admin/chat/conversations", headers=auth(admin_tokens))
        conv = listing.json()[0]
        assert conv["can_reply_freely"] is True
        assert conv["window_expires_at"] is not None

        resp = await client.post(
            f"/api/admin/chat/conversations/{conv['id']}/reply",
            headers=auth(admin_tokens),
            json={"body": "Rispondo entro le 24h"},
        )
        assert resp.status_code == 200

    async def test_reply_blocked_once_the_window_closes(self, client, db, admin_tokens):
        params = inbound_params()
        await client.post(WEBHOOK, data=params, headers=signed(params))

        conv = (await db.execute(select(Conversation))).scalar_one()
        conv.last_inbound_at = datetime.now(timezone.utc) - timedelta(
            hours=REPLY_WINDOW_HOURS + 1
        )
        await db.commit()

        resp = await client.post(
            f"/api/admin/chat/conversations/{conv.id}/reply",
            headers=auth(admin_tokens),
            json={"body": "Troppo tardi per il testo libero"},
        )
        assert resp.status_code == 409
        assert "template" in resp.json()["detail"].lower()

    async def test_never_contacted_thread_cannot_be_replied_to(self, client, db, admin_tokens):
        """No inbound message means no open window, so free text is not allowed."""
        conv = Conversation(phone="+393339999999")
        db.add(conv)
        await db.commit()

        resp = await client.post(
            f"/api/admin/chat/conversations/{conv.id}/reply",
            headers=auth(admin_tokens),
            json={"body": "Messaggio a freddo"},
        )
        assert resp.status_code == 409


class TestOutboundRecording:
    async def test_failed_send_is_recorded_not_lost(
        self, client, db, admin_tokens, monkeypatch
    ):
        params = inbound_params()
        await client.post(WEBHOOK, data=params, headers=signed(params))
        conv = (await db.execute(select(Conversation))).scalar_one()

        import app.services.chat as chat_service

        async def boom(*_args, **_kwargs):
            raise RuntimeError("Twilio giù")

        monkeypatch.setattr(chat_service, "_dispatch_whatsapp", boom)

        resp = await client.post(
            f"/api/admin/chat/conversations/{conv.id}/reply",
            headers=auth(admin_tokens),
            json={"body": "Questo fallisce"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == MessageStatus.failed.value
        assert "Twilio giù" in resp.json()["error"]

    async def test_reply_records_the_author(self, client, db, admin_tokens, admin_user):
        params = inbound_params()
        await client.post(WEBHOOK, data=params, headers=signed(params))
        conv = (await db.execute(select(Conversation))).scalar_one()

        resp = await client.post(
            f"/api/admin/chat/conversations/{conv.id}/reply",
            headers=auth(admin_tokens),
            json={"body": "Firmato"},
        )
        assert resp.json()["sent_by_user_id"] == admin_user.id
        assert resp.json()["direction"] == MessageDirection.outbound.value


class TestChannelStatus:
    """The banner that tells the salon whether WhatsApp is actually live."""

    async def test_sandbox_number_is_not_live(self, client, admin_tokens, monkeypatch):
        from app.config import settings
        from app.services.chat import TWILIO_SANDBOX_FROM

        monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC-test")
        monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", TWILIO_SANDBOX_FROM)

        body = (await client.get("/api/admin/chat/status", headers=auth(admin_tokens))).json()
        assert body["mode"] == "sandbox"
        assert body["is_live"] is False

    async def test_missing_credentials_are_not_live(self, client, admin_tokens, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "")
        monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "")

        body = (await client.get("/api/admin/chat/status", headers=auth(admin_tokens))).json()
        assert body["mode"] == "not_configured"
        assert body["is_live"] is False

    async def test_own_number_is_live(self, client, admin_tokens, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC-test")
        monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "whatsapp:+390123456789")

        body = (await client.get("/api/admin/chat/status", headers=auth(admin_tokens))).json()
        assert body["mode"] == "production"
        assert body["is_live"] is True

    async def test_collaborator_can_read_status(self, client, collab_tokens):
        resp = await client.get("/api/admin/chat/status", headers=auth(collab_tokens))
        assert resp.status_code == 200
