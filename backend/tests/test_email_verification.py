"""
Proving the email address belongs to whoever typed it.

Without this anyone could register under someone else's address: the salon's
appointment mail would go to a stranger, and the real owner would find their
address taken. So the tests that matter most are not "the happy path works" but
the ones about what a code must refuse — replay, brute force, expiry — and the
one showing an unverified sign-up cannot hold an address hostage.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.client import Client, ClientAccount
from app.services.email_verification import MAX_ATTEMPTS
from tests.conftest import auth

REGISTER = "/api/public/auth/register"
VERIFY = "/api/public/auth/verify-email"
RESEND = "/api/public/auth/resend-code"
LOGIN = "/api/public/auth/login"

EMAIL = "chiara.nuova@nsh-test.it"
PASSWORD = "una-password-lunga-2026"


def registration(**overrides):
    base = {
        "first_name": "Chiara",
        "last_name": "Nuova",
        "phone": "334 777 8899",
        "email": EMAIL,
        "password": PASSWORD,
        "birth_date": "1990-04-02",
    }
    base.update(overrides)
    return base


@pytest.fixture
def sent_codes(monkeypatch):
    """Capture the codes that would have been emailed."""
    import app.api.public.auth as auth_api

    codes: list[tuple[str, str]] = []

    async def fake_send(to_email, first_name, code, ttl_minutes):
        codes.append((to_email, code))

    monkeypatch.setattr(auth_api, "send_verification_code_email", fake_send)
    return codes


async def _register(client, sent_codes, **overrides) -> str:
    resp = await client.post(REGISTER, json=registration(**overrides))
    assert resp.status_code == 201, resp.text
    return sent_codes[-1][1]


class TestRegistrationIssuesACode:
    async def test_registration_does_not_hand_out_a_session(self, client, sent_codes):
        resp = await client.post(REGISTER, json=registration())
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["verification_required"] is True
        assert body["email"] == EMAIL
        assert "access_token" not in body, "sessione emessa prima della verifica"

    async def test_a_code_is_sent_to_the_address_given(self, client, sent_codes):
        await client.post(REGISTER, json=registration())
        assert len(sent_codes) == 1
        to, code = sent_codes[0]
        assert to == EMAIL
        assert code.isdigit() and len(code) == 6

    async def test_the_account_starts_unverified(self, client, db, sent_codes):
        await client.post(REGISTER, json=registration())
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        assert account.email_verified is False
        assert account.verification_code_hash is not None

    async def test_the_code_is_not_stored_in_the_clear(self, client, db, sent_codes):
        code = await _register(client, sent_codes)
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        assert code not in (account.verification_code_hash or "")


class TestDeliveryFailureIsReported:
    """
    A send that fails must not look like one that worked.

    This is not hypothetical: the mail provider started rejecting the server's
    IP, every code silently vanished, and the screen kept telling people to
    check an inbox nothing had been sent to.
    """

    @pytest.fixture
    def failing_mail(self, monkeypatch):
        import app.api.public.auth as auth_api

        async def boom(*args, **kwargs):
            raise RuntimeError("Brevo error 401: unrecognised IP address")

        monkeypatch.setattr(auth_api, "send_verification_code_email", boom)

    async def test_registration_says_the_mail_did_not_leave(self, client, failing_mail):
        resp = await client.post(REGISTER, json=registration())
        assert resp.status_code == 201, resp.text
        assert resp.json()["email_sent"] is False

    async def test_the_account_survives_so_a_resend_can_recover_it(
        self, client, db, failing_mail
    ):
        await client.post(REGISTER, json=registration())
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        assert account.verification_code_hash is not None

    async def test_resend_says_so_too(self, client, failing_mail):
        await client.post(REGISTER, json=registration())
        resp = await client.post(RESEND, json={"email": EMAIL})
        assert resp.status_code == 200
        assert resp.json()["email_sent"] is False

    async def test_a_working_send_still_reports_success(self, client, sent_codes):
        resp = await client.post(REGISTER, json=registration())
        assert resp.json()["email_sent"] is True

    async def test_an_unknown_address_never_reports_a_failure(
        self, client, failing_mail
    ):
        """Nothing is sent for it, so nothing can fail — and nothing is leaked."""
        resp = await client.post(RESEND, json={"email": "mai.visto@nsh-test.it"})
        assert resp.json()["email_sent"] is True


class TestUnverifiedCannotAct:
    async def test_login_is_refused_before_verifying(self, client, sent_codes):
        await client.post(REGISTER, json=registration())
        resp = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
        assert resp.status_code == 403
        assert "verificat" in resp.json()["detail"].lower()

    async def test_the_shared_sign_in_refuses_too(self, client, sent_codes):
        """The unified screen must not be a way around the portal's own check."""
        await client.post(REGISTER, json=registration())
        resp = await client.post(
            "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert resp.status_code == 403


class TestVerifying:
    async def test_the_right_code_returns_a_session(self, client, sent_codes):
        code = await _register(client, sent_codes)
        resp = await client.post(VERIFY, json={"email": EMAIL, "code": code})
        assert resp.status_code == 200, resp.text
        assert resp.json()["access_token"]

    async def test_that_session_actually_works(self, client, sent_codes):
        code = await _register(client, sent_codes)
        tokens = (await client.post(VERIFY, json={"email": EMAIL, "code": code})).json()
        mine = await client.get("/api/public/appointments", headers=auth(tokens))
        assert mine.status_code == 200

    async def test_login_works_afterwards(self, client, sent_codes):
        code = await _register(client, sent_codes)
        await client.post(VERIFY, json={"email": EMAIL, "code": code})
        resp = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
        assert resp.status_code == 200

    async def test_a_code_cannot_be_used_twice(self, client, sent_codes):
        code = await _register(client, sent_codes)
        assert (await client.post(VERIFY, json={"email": EMAIL, "code": code})).status_code == 200

        again = await client.post(VERIFY, json={"email": EMAIL, "code": code})
        assert again.status_code == 400


class TestRejections:
    async def test_a_wrong_code_is_refused(self, client, sent_codes):
        code = await _register(client, sent_codes)
        wrong = "000000" if code != "000000" else "111111"
        resp = await client.post(VERIFY, json={"email": EMAIL, "code": wrong})
        assert resp.status_code == 400

    async def test_guessing_is_capped(self, client, db, sent_codes):
        """Six digits would fall in seconds without a budget."""
        code = await _register(client, sent_codes)
        wrong = "000000" if code != "000000" else "111111"

        for _ in range(MAX_ATTEMPTS):
            await client.post(VERIFY, json={"email": EMAIL, "code": wrong})

        # Even the correct code is refused once the budget is spent.
        resp = await client.post(VERIFY, json={"email": EMAIL, "code": code})
        assert resp.status_code == 400
        assert "tentativi" in resp.json()["detail"].lower()

        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        assert account.email_verified is False

    async def test_an_expired_code_is_refused(self, client, db, sent_codes):
        code = await _register(client, sent_codes)
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalar_one()
        account.verification_expires = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()

        resp = await client.post(VERIFY, json={"email": EMAIL, "code": code})
        assert resp.status_code == 400
        assert "scadut" in resp.json()["detail"].lower()

    async def test_an_unknown_address_is_refused(self, client):
        resp = await client.post(
            VERIFY, json={"email": "mai.visto@nsh-test.it", "code": "123456"}
        )
        assert resp.status_code == 400


class TestResend:
    async def test_a_new_code_replaces_the_old_one(self, client, sent_codes):
        first = await _register(client, sent_codes)
        assert (await client.post(RESEND, json={"email": EMAIL})).status_code == 200
        second = sent_codes[-1][1]
        assert second != first, "codice identico dopo il rinvio"

        assert (await client.post(VERIFY, json={"email": EMAIL, "code": first})).status_code == 400
        assert (await client.post(VERIFY, json={"email": EMAIL, "code": second})).status_code == 200

    async def test_resending_restores_the_attempt_budget(self, client, sent_codes):
        """A new code is the documented way out of a spent budget."""
        code = await _register(client, sent_codes)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(MAX_ATTEMPTS):
            await client.post(VERIFY, json={"email": EMAIL, "code": wrong})

        await client.post(RESEND, json={"email": EMAIL})
        fresh = sent_codes[-1][1]
        assert (await client.post(VERIFY, json={"email": EMAIL, "code": fresh})).status_code == 200

    async def test_it_does_not_reveal_who_is_registered(self, client, sent_codes):
        known = await client.post(REGISTER, json=registration())
        assert known.status_code == 201

        a = await client.post(RESEND, json={"email": EMAIL})
        b = await client.post(RESEND, json={"email": "mai.visto@nsh-test.it"})
        assert a.status_code == b.status_code == 200
        assert a.json() == b.json()

    async def test_a_verified_account_gets_nothing(self, client, sent_codes):
        code = await _register(client, sent_codes)
        await client.post(VERIFY, json={"email": EMAIL, "code": code})
        before = len(sent_codes)

        resp = await client.post(RESEND, json={"email": EMAIL})
        assert resp.status_code == 200
        assert len(sent_codes) == before, "codice inviato per un account già verificato"


class TestAddressCannotBeHeldHostage:
    """
    An unverified sign-up proves nothing about who owns the address, so it must
    not block the real owner: registering again takes the pending account over.
    """

    async def test_registering_again_over_a_pending_account_is_allowed(
        self, client, db, sent_codes
    ):
        await client.post(REGISTER, json=registration(password="password-di-chi-squatta"))

        second = await client.post(REGISTER, json=registration(password=PASSWORD))
        assert second.status_code == 201, second.text

        code = sent_codes[-1][1]
        assert (await client.post(VERIFY, json={"email": EMAIL, "code": code})).status_code == 200

        # The address ends up with the password of whoever completed it.
        assert (await client.post(
            LOGIN, json={"email": EMAIL, "password": PASSWORD}
        )).status_code == 200

        accounts = (await db.execute(
            select(ClientAccount).where(ClientAccount.email == EMAIL)
        )).scalars().all()
        assert len(accounts) == 1, "registrarsi di nuovo ha duplicato l'account"

    async def test_a_verified_address_cannot_be_taken_over(self, client, sent_codes):
        code = await _register(client, sent_codes)
        await client.post(VERIFY, json={"email": EMAIL, "code": code})

        resp = await client.post(REGISTER, json=registration(password="tentativo-di-furto"))
        assert resp.status_code == 400
        assert "già registrata" in resp.json()["detail"].lower()

        # The original password still works — nothing was overwritten.
        assert (await client.post(
            LOGIN, json={"email": EMAIL, "password": PASSWORD}
        )).status_code == 200


class TestClientRecord:
    async def test_the_client_record_is_created_with_the_account(
        self, client, db, sent_codes
    ):
        """Details are captured at sign-up, even though the session comes later."""
        await client.post(REGISTER, json=registration())
        row = (await db.execute(
            select(Client).where(Client.email == EMAIL)
        )).scalar_one()
        assert row.phone == "+393347778899"
        assert row.birth_date.isoformat() == "1990-04-02"
