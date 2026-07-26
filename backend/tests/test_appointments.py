"""
Appointment lifecycle and availability.

Covers the status machine and the rule that a cancelled or rejected slot
becomes bookable again — a bug that was fixed in the calendar and must not
regress on the API side either.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import auth


def next_weekday(target: int, weeks_ahead: int = 1) -> date:
    """
    A future date falling on `target` (Monday=0). Kept a week out so it clears
    any minimum-advance rule and never lands in the past mid-run.
    """
    today = date.today()
    ahead = (target - today.weekday()) % 7
    return today + timedelta(days=ahead + 7 * weeks_ahead)


def at(day: date, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc).isoformat()


@pytest.fixture
def workday() -> date:
    """A Tuesday: inside the seeded Mon–Sat schedule."""
    return next_weekday(1)


async def create_appointment(client, tokens, collaborator, service, client_id, day, hour):
    return await client.post(
        "/api/admin/appointments",
        headers=auth(tokens),
        json={
            "client_id": client_id,
            "collaborator_id": collaborator.id,
            "start_time": at(day, hour),
            "end_time": at(day, hour + 1),
            "service_ids": [service.id],
        },
    )


class TestCreation:
    async def test_salon_created_appointment_is_confirmed(
        self, client, admin_tokens, collaborator, service, other_client, workday
    ):
        resp = await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 10
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "confirmed"
        assert body["origin"] == "salon"
        assert body["total_price"] == pytest.approx(service.price)

    async def test_collaborator_can_create(
        self, client, collab_tokens, collaborator, service, other_client, workday
    ):
        resp = await create_appointment(
            client, collab_tokens, collaborator, service, other_client.id, workday, 11
        )
        assert resp.status_code == 201

    async def test_unknown_service_rejected(
        self, client, admin_tokens, collaborator, other_client, workday
    ):
        resp = await client.post(
            "/api/admin/appointments",
            headers=auth(admin_tokens),
            json={
                "client_id": other_client.id,
                "collaborator_id": collaborator.id,
                "start_time": at(workday, 12),
                "end_time": at(workday, 13),
                "service_ids": [999999],
            },
        )
        assert resp.status_code == 400


class TestStatusTransitions:
    async def test_cancel_sets_status_and_reason(
        self, client, admin_tokens, collaborator, service, other_client, workday
    ):
        appt = (await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 10
        )).json()

        resp = await client.post(
            f"/api/admin/appointments/{appt['id']}/cancel",
            headers=auth(admin_tokens),
            json={"reason": "cliente indisposto"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        assert resp.json()["rejection_reason"] == "cliente indisposto"

    async def test_cancel_twice_is_rejected(
        self, client, admin_tokens, collaborator, service, other_client, workday
    ):
        appt = (await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 10
        )).json()
        first = await client.post(
            f"/api/admin/appointments/{appt['id']}/cancel",
            headers=auth(admin_tokens), json={"reason": None},
        )
        assert first.status_code == 200
        second = await client.post(
            f"/api/admin/appointments/{appt['id']}/cancel",
            headers=auth(admin_tokens), json={"reason": None},
        )
        assert second.status_code == 400

    async def test_confirm_only_from_pending(
        self, client, admin_tokens, collaborator, service, other_client, workday
    ):
        appt = (await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 10
        )).json()
        # Already confirmed on creation.
        resp = await client.post(
            f"/api/admin/appointments/{appt['id']}/confirm", headers=auth(admin_tokens)
        )
        assert resp.status_code == 400

    async def test_complete_then_cancel_is_rejected(
        self, client, admin_tokens, collaborator, service, other_client, workday
    ):
        appt = (await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 10
        )).json()

        done = await client.post(
            f"/api/admin/appointments/{appt['id']}/complete", headers=auth(admin_tokens)
        )
        assert done.status_code == 200
        assert done.json()["status"] == "completed"

        resp = await client.post(
            f"/api/admin/appointments/{appt['id']}/cancel",
            headers=auth(admin_tokens), json={"reason": None},
        )
        assert resp.status_code == 400, "un appuntamento completato non deve essere annullabile"

    async def test_missing_appointment_is_404(self, client, admin_tokens):
        resp = await client.get("/api/admin/appointments/999999", headers=auth(admin_tokens))
        assert resp.status_code == 404


class TestAvailability:
    async def _slots(self, client, tokens, collaborator, day, duration=2):
        resp = await client.get(
            "/api/admin/availability",
            headers=auth(tokens),
            params={
                "collaborator_id": collaborator.id,
                "target_date": day.isoformat(),
                "duration_slots": duration,
            },
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def test_working_day_has_slots(
        self, client, admin_tokens, collaborator, booking_config, workday
    ):
        slots = await self._slots(client, admin_tokens, collaborator, workday)
        assert slots, "un giorno lavorativo deve avere slot liberi"

    async def test_non_working_day_has_no_slots(
        self, client, admin_tokens, collaborator, booking_config
    ):
        sunday = next_weekday(6)
        slots = await self._slots(client, admin_tokens, collaborator, sunday)
        assert slots == [], "la domenica il collaboratore non lavora"

    async def test_booking_removes_slot_and_cancelling_restores_it(
        self, client, admin_tokens, collaborator, service, other_client, booking_config, workday
    ):
        """The regression: a cancelled appointment must free its slot again."""
        before = await self._slots(client, admin_tokens, collaborator, workday)
        taken = next(s for s in before if "T10:00" in s)

        appt = (await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 10
        )).json()

        during = await self._slots(client, admin_tokens, collaborator, workday)
        assert taken not in during, "lo slot prenotato deve sparire dalla disponibilità"

        await client.post(
            f"/api/admin/appointments/{appt['id']}/cancel",
            headers=auth(admin_tokens), json={"reason": None},
        )

        after = await self._slots(client, admin_tokens, collaborator, workday)
        assert taken in after, "annullando l'appuntamento lo slot deve tornare libero"

    async def test_rejected_appointment_also_frees_slot(
        self, client, admin_tokens, collaborator, service, other_client,
        booking_config, workday,
    ):
        before = await self._slots(client, admin_tokens, collaborator, workday)
        taken = next(s for s in before if "T14:00" in s)

        appt = (await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 14
        )).json()

        # /reject only accepts pending or confirmed; creation yields confirmed.
        resp = await client.post(
            f"/api/admin/appointments/{appt['id']}/reject",
            headers=auth(admin_tokens), json={"reason": "orario non disponibile"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # Read back through the API rather than a second DB session: a test-held
        # transaction alongside the app's own would only add lifecycle noise.
        reread = await client.get(
            f"/api/admin/appointments/{appt['id']}", headers=auth(admin_tokens)
        )
        assert reread.json()["status"] == "rejected"

        after = await self._slots(client, admin_tokens, collaborator, workday)
        assert taken in after, "un appuntamento rifiutato deve liberare lo slot"


class TestListing:
    async def test_date_range_filter(
        self, client, admin_tokens, collaborator, service, other_client, workday
    ):
        await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 10
        )
        far = workday + timedelta(days=30)
        await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, far, 10
        )

        resp = await client.get(
            "/api/admin/appointments",
            headers=auth(admin_tokens),
            params={"date_from": at(workday, 0), "date_to": at(workday, 23)},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_pending_list_only_returns_pending(
        self, client, admin_tokens, collaborator, service, other_client, workday
    ):
        await create_appointment(
            client, admin_tokens, collaborator, service, other_client.id, workday, 10
        )
        resp = await client.get("/api/admin/appointments/pending", headers=auth(admin_tokens))
        assert resp.status_code == 200
        assert resp.json() == [], "gli appuntamenti creati dal salone non sono 'in attesa'"
