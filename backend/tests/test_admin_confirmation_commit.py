"""
The client's confirmation must survive leaving the request.

`_trigger_booking_confirmation` hands an appointment id to a Celery worker that
runs in another process, with its own transaction. Queueing while this request
is still open is a race the worker loses: it looks the id up, sees nothing, and
`_async_send_booking_confirmation` returns without sending. Nothing is logged as
wrong — the client simply never hears that the appointment is confirmed.

Development hides it, because a worker that takes a moment to pick the job up
usually finds the row committed by then. So these tests read the row from a
genuinely separate connection at the instant the id is handed over.

The portal had the same bug; see tests/test_new_booking_alert.py.
"""
import asyncio
import concurrent.futures
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.api.admin.appointments as appointments_api
from app.models.appointment import (
    Appointment, AppointmentOrigin, AppointmentService, AppointmentStatus,
)
from app.models.client import Client
from tests.conftest import TEST_DATABASE_URL, auth

TOMORROW = (datetime.now(timezone.utc) + timedelta(days=1)).date()


def _slot(hour: int = 10) -> tuple[str, str]:
    start = datetime.combine(TOMORROW, datetime.min.time(), tzinfo=timezone.utc).replace(hour=hour)
    return start.isoformat(), (start + timedelta(hours=1)).isoformat()


def _visible_elsewhere(appointment_id: int) -> bool:
    """Is the appointment readable outside this request's transaction?

    Runs on a thread with its own engine and event loop — a same-session read
    would see the caller's uncommitted work and pass no matter what.
    """
    async def check() -> bool:
        eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        try:
            async with eng.connect() as conn:
                result = await conn.execute(
                    text("SELECT 1 FROM appointments WHERE id = :i"), {"i": appointment_id}
                )
                return result.scalar() is not None
        finally:
            await eng.dispose()

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(lambda: asyncio.run(check())).result(timeout=15)


def _status_elsewhere(appointment_id: int) -> str | None:
    """The status the worker would read, from outside this transaction."""
    async def check() -> str | None:
        eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        try:
            async with eng.connect() as conn:
                result = await conn.execute(
                    text("SELECT status::text FROM appointments WHERE id = :i"),
                    {"i": appointment_id},
                )
                return result.scalar()
        finally:
            await eng.dispose()

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(lambda: asyncio.run(check())).result(timeout=15)


@pytest_asyncio.fixture
async def a_client(db, client_account) -> Client:
    return (await db.execute(
        select(Client).where(Client.account_id == client_account.id)
    )).scalar_one()


@pytest_asyncio.fixture
async def pending_online_appointment(db, a_client, collaborator, service) -> Appointment:
    """A portal booking waiting for the salon to answer."""
    start = datetime.combine(TOMORROW, datetime.min.time(), tzinfo=timezone.utc).replace(hour=15)
    appt = Appointment(
        client_id=a_client.id,
        collaborator_id=collaborator.id,
        start_time=start,
        end_time=start + timedelta(hours=1),
        status=AppointmentStatus.pending,
        origin=AppointmentOrigin.online,
    )
    db.add(appt)
    await db.flush()
    db.add(AppointmentService(
        appointment_id=appt.id, service_id=service.id, price_snapshot=float(service.price),
    ))
    await db.commit()
    return appt


class TestCreatingAnAppointment:
    async def test_the_row_exists_when_the_confirmation_is_queued(
        self, client, monkeypatch, admin_tokens, a_client, collaborator, service
    ):
        seen: list[bool] = []
        monkeypatch.setattr(
            appointments_api,
            "_trigger_booking_confirmation",
            lambda appointment_id: seen.append(_visible_elsewhere(appointment_id)),
        )

        start, end = _slot()
        resp = await client.post(
            "/api/admin/appointments",
            headers=auth(admin_tokens),
            json={
                "client_id": a_client.id,
                "collaborator_id": collaborator.id,
                "start_time": start,
                "end_time": end,
                "service_ids": [service.id],
            },
        )
        assert resp.status_code == 201, resp.text
        assert seen == [True], "conferma accodata prima del commit: il worker non troverebbe la riga"

    async def test_the_response_still_carries_the_services(
        self, client, admin_tokens, a_client, collaborator, service
    ):
        """Committing mid-endpoint must not break the projection built after it."""
        start, end = _slot(11)
        resp = await client.post(
            "/api/admin/appointments",
            headers=auth(admin_tokens),
            json={
                "client_id": a_client.id,
                "collaborator_id": collaborator.id,
                "start_time": start,
                "end_time": end,
                "service_ids": [service.id],
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["service_names"] == [service.name]
        assert body["client_name"] == f"{a_client.first_name} {a_client.last_name}"
        assert body["total_price"] == pytest.approx(float(service.price))


class TestConfirmingAnAppointment:
    async def test_the_worker_would_read_the_new_status(
        self, client, monkeypatch, admin_tokens, pending_online_appointment
    ):
        """A confirmation queued mid-transaction describes an appointment the
        worker still sees as `pending`."""
        seen: list[str | None] = []
        monkeypatch.setattr(
            appointments_api,
            "_trigger_booking_confirmation",
            lambda appointment_id: seen.append(_status_elsewhere(appointment_id)),
        )

        resp = await client.post(
            f"/api/admin/appointments/{pending_online_appointment.id}/confirm",
            headers=auth(admin_tokens),
        )
        assert resp.status_code == 200, resp.text
        assert seen == ["confirmed"], "stato non ancora committato quando parte la conferma"

    async def test_confirming_twice_is_still_refused(
        self, client, admin_tokens, pending_online_appointment
    ):
        """The early commit must not turn the state guard into a no-op."""
        first = await client.post(
            f"/api/admin/appointments/{pending_online_appointment.id}/confirm",
            headers=auth(admin_tokens),
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            f"/api/admin/appointments/{pending_online_appointment.id}/confirm",
            headers=auth(admin_tokens),
        )
        assert second.status_code == 400
        assert "in attesa" in second.json()["detail"]
