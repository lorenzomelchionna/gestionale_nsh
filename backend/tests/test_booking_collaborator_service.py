"""
The booking portal may only book a collaborator who actually offers the service.

The browser already filters the collaborator list by the chosen service, so
these paths are not reachable by clicking. They are reachable by a stale tab, a
replayed request or a hand-made call, and the result would land in the salon's
calendar as a real appointment — someone booked for work they do not do.

The same rule covers collaborators hidden from the portal or deactivated: the
public listing excludes them, so booking one has to fail too.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.appointment import Appointment
from app.models.collaborator import Collaborator, CollaboratorSchedule, CollaboratorService
from app.models.service import Service
from tests.conftest import auth, giorno_lavorativo

TOMORROW = giorno_lavorativo((datetime.now(timezone.utc) + timedelta(days=1)).date())


def _slot(hour: int = 10) -> tuple[str, str]:
    start = datetime.combine(TOMORROW, datetime.min.time(), tzinfo=timezone.utc).replace(hour=hour)
    return start.isoformat(), (start + timedelta(hours=1)).isoformat()


class TestAvailability:
    async def test_service_the_collaborator_offers_is_allowed(
        self, client, booking_config, collaborator, service
    ):
        resp = await client.get(
            "/api/public/availability",
            params={
                "service_id": service.id,
                "collaborator_id": collaborator.id,
                "target_date": TOMORROW.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text

    async def test_service_the_collaborator_does_not_offer_is_rejected(
        self, client, booking_config, collaborator, unoffered_service
    ):
        resp = await client.get(
            "/api/public/availability",
            params={
                "service_id": unoffered_service.id,
                "collaborator_id": collaborator.id,
                "target_date": TOMORROW.isoformat(),
            },
        )
        assert resp.status_code == 400
        assert "non esegue" in resp.json()["detail"]

    async def test_collaborator_hidden_from_the_portal_is_rejected(
        self, client, booking_config, hidden_collaborator, service
    ):
        resp = await client.get(
            "/api/public/availability",
            params={
                "service_id": service.id,
                "collaborator_id": hidden_collaborator.id,
                "target_date": TOMORROW.isoformat(),
            },
        )
        assert resp.status_code == 404

    async def test_unknown_collaborator_is_rejected(
        self, client, booking_config, service
    ):
        resp = await client.get(
            "/api/public/availability",
            params={
                "service_id": service.id,
                "collaborator_id": 999999,
                "target_date": TOMORROW.isoformat(),
            },
        )
        assert resp.status_code == 404


class TestBooking:
    async def test_booking_an_offered_service_still_works(
        self, client, db, booking_config, client_tokens, collaborator, service
    ):
        start, end = _slot()
        resp = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,  # ignored — taken from the token
                "collaborator_id": collaborator.id,
                "start_time": start,
                "end_time": end,
                "service_ids": [service.id],
            },
        )
        assert resp.status_code == 201, resp.text

    async def test_booking_a_service_the_collaborator_does_not_offer_is_rejected(
        self, client, db, booking_config, client_tokens, collaborator, unoffered_service
    ):
        start, end = _slot(11)
        resp = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,
                "collaborator_id": collaborator.id,
                "start_time": start,
                "end_time": end,
                "service_ids": [unoffered_service.id],
            },
        )
        assert resp.status_code == 400
        assert "non esegue" in resp.json()["detail"]

        booked = (await db.execute(select(Appointment))).scalars().all()
        assert booked == [], "appuntamento creato nonostante il rifiuto"

    async def test_one_unoffered_service_rejects_the_whole_booking(
        self, client, db, booking_config, client_tokens, collaborator, service, unoffered_service
    ):
        """A mixed basket must not slip the unoffered service through."""
        start, end = _slot(12)
        resp = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,
                "collaborator_id": collaborator.id,
                "start_time": start,
                "end_time": end,
                "service_ids": [service.id, unoffered_service.id],
            },
        )
        assert resp.status_code == 400

        booked = (await db.execute(select(Appointment))).scalars().all()
        assert booked == []

    async def test_booking_a_hidden_collaborator_is_rejected(
        self, client, db, booking_config, client_tokens, hidden_collaborator, service
    ):
        start, end = _slot(13)
        resp = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,
                "collaborator_id": hidden_collaborator.id,
                "start_time": start,
                "end_time": end,
                "service_ids": [service.id],
            },
        )
        assert resp.status_code == 404

        booked = (await db.execute(select(Appointment))).scalars().all()
        assert booked == []
