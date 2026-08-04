"""
Birth date is collected at sign-up.

The daily birthday task only greets clients whose date is on file, so a field
the registration form never asks about leaves the feature silently doing
nothing. Requiring it at sign-up is what makes the greeting reach anyone who
registers online.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.client import Client
from tests.conftest import auth

REGISTER = "/api/public/auth/register"
GOOD_PASSWORD = "una-password-lunga-2026"


def payload(**overrides):
    base = {
        "first_name": "Chiara",
        "last_name": "Esempio",
        "phone": "334 555 6677",
        "email": "chiara.esempio@nsh-test.it",
        "password": GOOD_PASSWORD,
        "birth_date": "1991-03-14",
    }
    base.update(overrides)
    return base


class TestStored:
    async def test_birth_date_is_saved_on_the_client(self, client, db):
        resp = await client.post(REGISTER, json=payload())
        assert resp.status_code == 201, resp.text

        row = (await db.execute(
            select(Client).where(Client.email == "chiara.esempio@nsh-test.it")
        )).scalar_one()
        assert row.birth_date == date(1991, 3, 14)

    async def test_the_birthday_task_would_find_them(self, client, db):
        """Stored in the shape the daily greeting queries by month and day."""
        today = date.today()
        birthday = today.replace(year=today.year - 30)
        resp = await client.post(REGISTER, json=payload(birth_date=birthday.isoformat()))
        assert resp.status_code == 201

        row = (await db.execute(
            select(Client).where(Client.email == "chiara.esempio@nsh-test.it")
        )).scalar_one()
        assert row.birth_date.month == today.month
        assert row.birth_date.day == today.day


class TestRequired:
    async def test_missing_birth_date_is_refused(self, client):
        body = payload()
        del body["birth_date"]
        resp = await client.post(REGISTER, json=body)
        assert resp.status_code == 422

    @pytest.mark.parametrize("bad", ["", "non-una-data", "1991-13-45"])
    async def test_unparseable_dates_are_refused(self, client, bad):
        resp = await client.post(REGISTER, json=payload(birth_date=bad))
        assert resp.status_code == 422


class TestPlausibility:
    async def test_today_is_refused(self, client):
        resp = await client.post(REGISTER, json=payload(birth_date=date.today().isoformat()))
        assert resp.status_code == 422

    async def test_a_future_date_is_refused(self, client):
        future = (date.today() + timedelta(days=1)).isoformat()
        resp = await client.post(REGISTER, json=payload(birth_date=future))
        assert resp.status_code == 422

    async def test_an_absurdly_old_date_is_refused(self, client):
        """Catches a mistyped year rather than trusting it."""
        resp = await client.post(REGISTER, json=payload(birth_date="1850-01-01"))
        assert resp.status_code == 422

    async def test_yesterday_is_accepted(self, client):
        """The bound is 'in the past', not an age limit — parents book for children."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        resp = await client.post(REGISTER, json=payload(birth_date=yesterday))
        assert resp.status_code == 201, resp.text


async def _verifica(http, db, email: str):
    """Inserisce il codice come farebbe chi possiede quella casella.

    Il collegamento con l'anagrafica del salone avviene qui e non alla
    registrazione: prima della verifica non è stato dimostrato niente.
    """
    from app.models.client import ClientAccount
    from app.services.email_verification import issue_code

    account = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == email)
    )).scalar_one()
    code = issue_code(account)
    await db.commit()
    resp = await http.post("/api/public/auth/verify-email", json={"email": email, "code": code})
    assert resp.status_code == 200, resp.text


class TestLinkingAnExistingClient:
    """Il collegamento avviene sull'indirizzo verificato: è l'unico dato che a
    quel punto è dimostrato. Il match sul telefono è stato tolto — vedi
    tests/test_registration_takeover.py per il motivo."""

    async def test_a_blank_birth_date_gets_filled_in(self, client, db, admin_tokens):
        """The salon rarely has it; the client supplies it when they register."""
        created = await client.post(
            "/api/admin/clients",
            headers=auth(admin_tokens),
            json={
                "first_name": "Chiara", "last_name": "Esempio",
                "email": "chiara.esempio@nsh-test.it",
            },
        )
        assert created.status_code == 201
        assert created.json()["birth_date"] is None

        resp = await client.post(REGISTER, json=payload())
        assert resp.status_code == 201, resp.text
        await _verifica(client, db, "chiara.esempio@nsh-test.it")

        rows = (await db.execute(
            select(Client).where(Client.email == "chiara.esempio@nsh-test.it")
        )).scalars().all()
        assert len(rows) == 1, "la registrazione ha duplicato il cliente"
        assert rows[0].birth_date == date(1991, 3, 14)

    async def test_an_existing_birth_date_is_not_overwritten(
        self, client, db, admin_tokens
    ):
        """What the salon recorded wins over what someone types at sign-up."""
        created = await client.post(
            "/api/admin/clients",
            headers=auth(admin_tokens),
            json={
                "first_name": "Chiara", "last_name": "Esempio",
                "email": "chiara.esempio@nsh-test.it", "birth_date": "1985-07-01",
            },
        )
        assert created.status_code == 201

        resp = await client.post(REGISTER, json=payload(birth_date="1991-03-14"))
        assert resp.status_code == 201
        await _verifica(client, db, "chiara.esempio@nsh-test.it")

        row = (await db.execute(
            select(Client).where(Client.email == "chiara.esempio@nsh-test.it")
        )).scalar_one()
        assert row.birth_date == date(1985, 7, 1)
