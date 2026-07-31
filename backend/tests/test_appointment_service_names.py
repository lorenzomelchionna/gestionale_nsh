"""
Every route that returns an appointment names the services it was booked for.

`service_names` sat on the schema with a default of `[]` and nothing ever
filled it, so every route below answered with an empty list for as long as the
field existed. Nothing failed: an empty list is a valid list, and the frontend
simply had nothing to show — the client record could not say what was actually
done.

The rule now lives in one place, `AppointmentOutWithNames.from_appointment`,
and these tests hold every caller to it. The next field added to that schema is
just as easy to forget in four routers as this one was.

Two services rather than one, on purpose: a route that named only the first
would still pass a single-service check.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.client import Client
from tests.conftest import auth


def next_weekday(target: int, weeks_ahead: int = 1) -> date:
    """A future date on `target` (Monday=0), a week out so it clears any
    minimum-advance rule and never lands in the past mid-run."""
    today = date.today()
    ahead = (target - today.weekday()) % 7
    return today + timedelta(days=ahead + 7 * weeks_ahead)


def at(day: date, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc).isoformat()


@pytest.fixture
def workday() -> date:
    """A Tuesday: inside the seeded Mon–Sat schedule."""
    return next_weekday(1)


async def linked_client_id(db, account) -> int:
    result = await db.execute(select(Client).where(Client.account_id == account.id))
    return result.scalar_one().id


async def book_two(http, admin_tokens, collaborator, service, unoffered_service, client_id, day):
    """One appointment carrying two services, created through the admin API."""
    resp = await http.post(
        "/api/admin/appointments",
        headers=auth(admin_tokens),
        json={
            "client_id": client_id,
            "collaborator_id": collaborator.id,
            "start_time": at(day, 10),
            "end_time": at(day, 12),
            "service_ids": [service.id, unoffered_service.id],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


BOTH = {"Taglio test", "Colore test"}


class TestAdminRoutes:
    async def test_create_returns_the_names(
        self, client, db, admin_tokens, collaborator, service, unoffered_service,
        client_account, workday,
    ):
        cid = await linked_client_id(db, client_account)
        body = await book_two(
            client, admin_tokens, collaborator, service, unoffered_service, cid, workday
        )
        assert set(body["service_names"]) == BOTH

    async def test_list_returns_the_names(
        self, client, db, admin_tokens, collaborator, service, unoffered_service,
        client_account, workday,
    ):
        cid = await linked_client_id(db, client_account)
        await book_two(
            client, admin_tokens, collaborator, service, unoffered_service, cid, workday
        )

        resp = await client.get("/api/admin/appointments", headers=auth(admin_tokens))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert set(items[0]["service_names"]) == BOTH

    async def test_detail_returns_the_names(
        self, client, db, admin_tokens, collaborator, service, unoffered_service,
        client_account, workday,
    ):
        cid = await linked_client_id(db, client_account)
        created = await book_two(
            client, admin_tokens, collaborator, service, unoffered_service, cid, workday
        )

        resp = await client.get(
            f"/api/admin/appointments/{created['id']}", headers=auth(admin_tokens)
        )
        assert resp.status_code == 200
        assert set(resp.json()["service_names"]) == BOTH

    async def test_client_history_returns_the_names(
        self, client, db, admin_tokens, collaborator, service, unoffered_service,
        client_account, workday,
    ):
        """The scheda cliente reads this route — it is the one the missing
        field was most visible on."""
        cid = await linked_client_id(db, client_account)
        await book_two(
            client, admin_tokens, collaborator, service, unoffered_service, cid, workday
        )

        resp = await client.get(
            f"/api/admin/clients/{cid}/appointments", headers=auth(admin_tokens)
        )
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 1
        assert set(history[0]["service_names"]) == BOTH

    async def test_confirm_returns_the_names(
        self, client, db, admin_tokens, client_tokens, collaborator, service,
        client_account, booking_config, workday,
    ):
        """Status transitions reload the appointment; the reload must carry the
        same projection as the list did."""
        booked = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,  # resolved server-side from the token
                "collaborator_id": collaborator.id,
                "start_time": at(workday, 14),
                "end_time": at(workday, 15),
                "service_ids": [service.id],
            },
        )
        assert booked.status_code == 201, booked.text

        pending = await client.get(
            "/api/admin/appointments/pending", headers=auth(admin_tokens)
        )
        assert pending.status_code == 200
        assert pending.json()[0]["service_names"] == ["Taglio test"]

        confirmed = await client.post(
            f"/api/admin/appointments/{booked.json()['id']}/confirm",
            headers=auth(admin_tokens),
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["service_names"] == ["Taglio test"]


class TestClientPortal:
    async def test_my_appointments_returns_the_names(
        self, client, db, admin_tokens, client_tokens, collaborator, service,
        unoffered_service, client_account, workday,
    ):
        """The client's own area shows what they booked, not just who with."""
        cid = await linked_client_id(db, client_account)
        await book_two(
            client, admin_tokens, collaborator, service, unoffered_service, cid, workday
        )

        resp = await client.get("/api/public/appointments", headers=auth(client_tokens))
        assert resp.status_code == 200
        mine = resp.json()
        assert len(mine) == 1
        assert set(mine[0]["service_names"]) == BOTH


class TestEdges:
    async def test_no_services_gives_an_empty_list(
        self, client, db, admin_tokens, collaborator, client_account, workday,
    ):
        """An appointment booked with no service is not an error — the field is
        empty because there is nothing to name, which is a different thing from
        the field never being filled."""
        cid = await linked_client_id(db, client_account)
        resp = await client.post(
            "/api/admin/appointments",
            headers=auth(admin_tokens),
            json={
                "client_id": cid,
                "collaborator_id": collaborator.id,
                "start_time": at(workday, 16),
                "end_time": at(workday, 17),
                "service_ids": [],
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["service_names"] == []
        assert resp.json()["total_price"] == 0.0

    async def test_names_follow_the_booked_order(
        self, client, db, admin_tokens, collaborator, service, unoffered_service,
        client_account, workday,
    ):
        """"Taglio + barba" is how it was sold, so that is the order it reads
        in — not alphabetical, and not whatever the database returns."""
        cid = await linked_client_id(db, client_account)
        resp = await client.post(
            "/api/admin/appointments",
            headers=auth(admin_tokens),
            json={
                "client_id": cid,
                "collaborator_id": collaborator.id,
                "start_time": at(workday, 10),
                "end_time": at(workday, 12),
                # Deliberately not alphabetical: "Taglio" after "Colore".
                "service_ids": [unoffered_service.id, service.id],
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["service_names"] == ["Colore test", "Taglio test"]
