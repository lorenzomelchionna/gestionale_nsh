"""
Proving the WhatsApp number belongs to whoever typed it — the second step.

Sibling of test_email_verification.py, one channel later: registration only
sends the emailed code; the WhatsApp one goes out once `/verify-email`
succeeds (see TestVerifying there), and a session only exists once *both*
have been entered. See app/services/phone_verification.py for why: without
this, anyone can type a stranger's number at sign-up and that stranger starts
receiving the salon's WhatsApp messages.

The tests that matter most are the same shape as the email ones — what a
code must refuse — plus one property specific to this step: it cannot be
skipped by calling it before the address is proven.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.client import ClientAccount
from app.services.phone_verification import MAX_ATTEMPTS
from tests.conftest import auth

REGISTER = "/api/public/auth/register"
VERIFY = "/api/public/auth/verify-email"
VERIFY_PHONE = "/api/public/auth/verify-phone"
RESEND_PHONE = "/api/public/auth/resend-phone-code"
LOGIN = "/api/public/auth/login"

EMAIL = "marta.nuova@nsh-test.it"
PASSWORD = "una-password-lunga-2026"
PHONE = "+393349990011"


def registration(**overrides):
    base = {
        "first_name": "Marta",
        "last_name": "Nuova",
        "phone": PHONE,
        "email": EMAIL,
        "password": PASSWORD,
        "birth_date": "1988-11-20",
    }
    base.update(overrides)
    return base


@pytest.fixture
def sent_codes(monkeypatch):
    """Capture the codes that would have been emailed (the first step still
    has to run before the second one is reachable)."""
    import app.api.public.auth as auth_api

    codes: list[tuple[str, str]] = []

    async def fake_send(to_email, first_name, code, ttl_minutes):
        codes.append((to_email, code))

    monkeypatch.setattr(auth_api, "send_verification_code_email", fake_send)
    return codes


@pytest.fixture
def sent_whatsapp_codes(monkeypatch):
    """Capture the codes that would have been sent over WhatsApp."""
    import app.api.public.auth as auth_api

    codes: list[tuple[str, str]] = []

    async def fake_send(to_phone, code):
        codes.append((to_phone, code))

    monkeypatch.setattr(auth_api, "send_verification_code_whatsapp", fake_send)
    return codes


async def _register_and_verify_email(client, sent_codes, sent_whatsapp_codes, **overrides) -> str:
    """Registration through the emailed code — returns the WhatsApp code
    that step queues, ready for the tests in this file to consume."""
    resp = await client.post(REGISTER, json=registration(**overrides))
    assert resp.status_code == 201, resp.text
    email = overrides.get("email", EMAIL)
    email_code = sent_codes[-1][1]
    step = await client.post(VERIFY, json={"email": email, "code": email_code})
    assert step.status_code == 200, step.text
    assert step.json()["phone_verification_required"] is True
    return sent_whatsapp_codes[-1][1]


class TestOrdering:
    """Il telefono non si verifica prima dell'indirizzo — non è un dettaglio
    implementativo, è la regola che decide quale schermata il portale mostra
    per prima."""

    async def test_verifying_the_phone_before_the_email_is_refused(self, client):
        resp = await client.post(REGISTER, json=registration())
        assert resp.status_code == 201

        resp = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": "123456"})
        assert resp.status_code == 400
        assert "email" in resp.json()["detail"].lower()

    async def test_no_whatsapp_code_exists_yet_at_that_point(self, client, db):
        await client.post(REGISTER, json=registration())
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        assert account.phone_verification_code_hash is None


class TestVerifying:
    async def test_the_right_code_returns_a_session(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        resp = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": phone_code})
        assert resp.status_code == 200, resp.text
        assert resp.json()["access_token"]

    async def test_that_session_actually_works(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        tokens = (await client.post(
            VERIFY_PHONE, json={"email": EMAIL, "code": phone_code}
        )).json()
        mine = await client.get("/api/public/appointments", headers=auth(tokens))
        assert mine.status_code == 200

    async def test_login_works_afterwards(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": phone_code})
        resp = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
        assert resp.status_code == 200

    async def test_the_shared_sign_in_refuses_an_unverified_phone_too(
        self, client, sent_codes
    ):
        """La schermata unica deve rifiutare quello che rifiuta il portale —
        altrimenti diventa la scorciatoia per aggirare questo passo."""
        resp = await client.post(REGISTER, json=registration())
        assert resp.status_code == 201
        email_code = sent_codes[-1][1]
        await client.post(VERIFY, json={"email": EMAIL, "code": email_code})

        resp = await client.post(
            "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert resp.status_code == 403
        assert "telefono" in resp.json()["detail"].lower()

    async def test_the_account_is_marked_verified(
        self, client, db, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": phone_code})
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        assert account.phone_verified is True
        assert account.phone_verification_code_hash is None, "il codice consumato deve sparire"

    async def test_a_code_cannot_be_used_twice(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        assert (await client.post(
            VERIFY_PHONE, json={"email": EMAIL, "code": phone_code}
        )).status_code == 200

        again = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": phone_code})
        assert again.status_code == 400


class TestRejections:
    async def test_a_wrong_code_is_refused(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        wrong = "000000" if phone_code != "000000" else "111111"
        resp = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": wrong})
        assert resp.status_code == 400

    async def test_guessing_is_capped(
        self, client, db, sent_codes, sent_whatsapp_codes
    ):
        """Six digits would fall in seconds without a budget."""
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        wrong = "000000" if phone_code != "000000" else "111111"

        for _ in range(MAX_ATTEMPTS):
            await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": wrong})

        # Even the correct code is refused once the budget is spent.
        resp = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": phone_code})
        assert resp.status_code == 400
        assert "tentativi" in resp.json()["detail"].lower()

        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        assert account.phone_verified is False

    async def test_an_expired_code_is_refused(
        self, client, db, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        account.phone_verification_expires = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()

        resp = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": phone_code})
        assert resp.status_code == 400
        assert "scadut" in resp.json()["detail"].lower()

    async def test_an_unknown_address_is_refused(self, client):
        resp = await client.post(
            VERIFY_PHONE, json={"email": "mai.visto@nsh-test.it", "code": "123456"}
        )
        assert resp.status_code == 400


class TestResend:
    async def test_a_new_code_replaces_the_old_one(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        first = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        assert (await client.post(RESEND_PHONE, json={"email": EMAIL})).status_code == 200
        second = sent_whatsapp_codes[-1][1]
        assert second != first, "codice identico dopo il rinvio"

        assert (await client.post(
            VERIFY_PHONE, json={"email": EMAIL, "code": first}
        )).status_code == 400
        assert (await client.post(
            VERIFY_PHONE, json={"email": EMAIL, "code": second}
        )).status_code == 200

    async def test_resending_restores_the_attempt_budget(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        wrong = "000000" if phone_code != "000000" else "111111"
        for _ in range(MAX_ATTEMPTS):
            await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": wrong})

        await client.post(RESEND_PHONE, json={"email": EMAIL})
        fresh = sent_whatsapp_codes[-1][1]
        assert (await client.post(
            VERIFY_PHONE, json={"email": EMAIL, "code": fresh}
        )).status_code == 200

    async def test_it_does_not_reveal_who_is_registered(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)

        a = await client.post(RESEND_PHONE, json={"email": EMAIL})
        b = await client.post(RESEND_PHONE, json={"email": "mai.visto@nsh-test.it"})
        assert a.status_code == b.status_code == 200
        assert a.json() == b.json()

    async def test_before_the_email_step_nothing_is_sent(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        """Rinviare il codice telefono prima ancora che l'indirizzo sia
        provato non deve mandare nulla: non c'è ancora niente da rinviare, e
        rispondere `True` comunque direbbe a chi chiama più di quanto deve
        sapere su un indirizzo che non ha nemmeno verificato."""
        await client.post(REGISTER, json=registration())

        resp = await client.post(RESEND_PHONE, json={"email": EMAIL})
        assert resp.status_code == 200
        assert len(sent_whatsapp_codes) == 0, "codice mandato prima di verificare l'email"

    async def test_a_verified_account_gets_nothing(
        self, client, sent_codes, sent_whatsapp_codes
    ):
        phone_code = await _register_and_verify_email(client, sent_codes, sent_whatsapp_codes)
        await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": phone_code})
        before = len(sent_whatsapp_codes)

        resp = await client.post(RESEND_PHONE, json={"email": EMAIL})
        assert resp.status_code == 200
        assert len(sent_whatsapp_codes) == before, "codice inviato per un account già verificato"


class TestDeliveryFailureIsReported:
    """Stesso principio del canale email: un invio fallito non deve sembrare
    riuscito — altrimenti la cliente resta a fissare WhatsApp aspettando un
    codice che non è mai partito."""

    @pytest.fixture
    def failing_whatsapp(self, monkeypatch):
        import app.api.public.auth as auth_api

        async def boom(*args, **kwargs):
            raise RuntimeError("Twilio error 63016: outside the 24h window")

        monkeypatch.setattr(auth_api, "send_verification_code_whatsapp", boom)

    async def test_verify_email_says_the_whatsapp_message_did_not_leave(
        self, client, sent_codes, failing_whatsapp
    ):
        resp = await client.post(REGISTER, json=registration())
        assert resp.status_code == 201
        email_code = sent_codes[-1][1]

        resp = await client.post(VERIFY, json={"email": EMAIL, "code": email_code})
        assert resp.status_code == 200, resp.text
        assert resp.json()["whatsapp_sent"] is False

    async def test_the_account_survives_so_a_resend_can_recover_it(
        self, client, db, sent_codes, failing_whatsapp
    ):
        await client.post(REGISTER, json=registration())
        email_code = sent_codes[-1][1]
        await client.post(VERIFY, json={"email": EMAIL, "code": email_code})

        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        assert account.phone_verification_code_hash is not None


class TestGrandfathering:
    """Chi si è registrato prima che questo passo esistesse — o chi l'ha già
    completato — non lo rifà: `verify-email` gli dà la sessione subito, come
    faceva prima di questa funzionalità."""

    async def test_an_account_with_phone_already_verified_gets_a_session_immediately(
        self, client, db, sent_codes, sent_whatsapp_codes
    ):
        resp = await client.post(REGISTER, json=registration())
        assert resp.status_code == 201
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        account.phone_verified = True
        await db.commit()

        email_code = sent_codes[-1][1]
        resp = await client.post(VERIFY, json={"email": EMAIL, "code": email_code})
        assert resp.status_code == 200, resp.text
        assert resp.json()["access_token"], "un account già verificato deve entrare subito"
        assert len(sent_whatsapp_codes) == 0, "non deve partire un codice che non serve"
