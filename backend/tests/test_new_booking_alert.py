"""
An online booking has to reach a human.

The portal files a booking as `pending` and answers the client with "in attesa".
Nothing else happens: the salon only finds out by opening the "In attesa" page
on its own initiative. If nobody opens it, a real person waits for an answer
that was never going to come — so the alert is not a nicety, it is the only
thing closing that loop.

Three separate failures are covered here, because the feature had all three:
the endpoint never queued anything, the task body was a `print()`, and a task
that queues before the transaction commits finds nothing to read.
"""
import asyncio
import concurrent.futures
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import giorno_lavorativo
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.api.public.booking as booking_api
import app.utils.notifications as notifications
from app.models.appointment import Appointment, appointment_detail_loads
from app.models.service import Service
from app.models.user import User, UserRole
from app.utils.auth import hash_password
from tests.conftest import TEST_DATABASE_URL, auth

TOMORROW = (giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=1))).date()

# Captured at import, before the autouse `no_celery` fixture stubs it out, so a
# test can put the real dispatch back when the dispatch is what it is testing.
_REAL_TRIGGER = booking_api._trigger_new_booking_alert


def _slot(hour: int = 10) -> tuple[str, str]:
    start = datetime.combine(TOMORROW, datetime.min.time(), tzinfo=timezone.utc).replace(hour=hour)
    return start.isoformat(), (start + timedelta(hours=1)).isoformat()


async def _book(http, tokens, collaborator, service_ids, hour=10, notes=None):
    start, end = _slot(hour)
    payload = {
        "client_id": 0,  # ignored — taken from the token
        "collaborator_id": collaborator.id,
        "start_time": start,
        "end_time": end,
        "service_ids": service_ids,
    }
    if notes is not None:
        payload["notes"] = notes
    resp = await http.post("/api/public/appointments", headers=auth(tokens), json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def queued(monkeypatch) -> list[int]:
    """Record what the endpoint hands to Celery, instead of reaching a broker."""
    ids: list[int] = []
    monkeypatch.setattr(booking_api, "_trigger_new_booking_alert", ids.append)
    return ids


@pytest.fixture
def sent(monkeypatch) -> list[tuple[str, str, str]]:
    """Capture outgoing mail at the transport, so the whole body is assertable."""
    box: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, html_body: str) -> None:
        box.append((to, subject, html_body))

    monkeypatch.setattr("app.utils.email.send_email", fake_send_email)
    return box


@pytest_asyncio.fixture
async def second_service(db) -> Service:
    """A second bookable service, so a mail naming only the first still fails."""
    svc = Service(
        name="Barba test",
        price=15.0,
        duration_slots=1,
        category="Barba",
        bookable_online=True,
        is_active=True,
    )
    db.add(svc)
    await db.commit()
    return svc


@pytest_asyncio.fixture
async def collaborator_two_services(db, collaborator, second_service):
    from app.models.collaborator import CollaboratorService

    db.add(CollaboratorService(collaborator_id=collaborator.id, service_id=second_service.id))
    await db.commit()
    return collaborator


class TestTheAlertIsQueued:
    async def test_an_online_booking_queues_the_alert(
        self, client, booking_config, client_tokens, collaborator, service, queued
    ):
        body = await _book(client, client_tokens, collaborator, [service.id])
        assert queued == [body["id"]]

    async def test_a_salon_booking_does_not_queue_it(
        self, client, db, booking_config, admin_tokens, client_account, collaborator, service, queued
    ):
        """Staff typing an appointment in already know about it."""
        from app.models.client import Client

        c = (await db.execute(select(Client))).scalars().first()
        start, end = _slot(14)
        resp = await client.post(
            "/api/admin/appointments",
            headers=auth(admin_tokens),
            json={
                "client_id": c.id,
                "collaborator_id": collaborator.id,
                "start_time": start,
                "end_time": end,
                "service_ids": [service.id],
            },
        )
        assert resp.status_code == 201, resp.text
        assert queued == []

    async def test_a_broker_outage_does_not_sink_the_booking(
        self, client, db, monkeypatch, booking_config, client_tokens, collaborator, service
    ):
        """The client did nothing wrong if Redis is down; the row must survive."""
        def explode(appointment_id):
            raise ConnectionError("broker unreachable")

        monkeypatch.setattr(booking_api, "_trigger_new_booking_alert", _REAL_TRIGGER)
        monkeypatch.setattr("app.tasks.reminders.notify_new_booking.delay", explode)

        body = await _book(client, client_tokens, collaborator, [service.id])

        stored = (await db.execute(
            select(Appointment).where(Appointment.id == body["id"])
        )).scalar_one_or_none()
        assert stored is not None, "prenotazione persa perché il broker era giù"


class TestTheBookingIsReadableWhenTheAlertIsQueued:
    async def test_committed_before_the_task_is_handed_off(
        self, client, monkeypatch, booking_config, client_tokens, collaborator, service
    ):
        """
        The worker is another process with its own transaction. Queueing while
        the request's transaction is still open is a race it loses: the task
        starts, the row is not visible yet, and the alert is dropped as
        "appointment vanished". Nothing about that failure is visible in
        development, where the worker is slow to pick anything up.

        So the check runs from a genuinely separate connection, at the exact
        moment the endpoint hands the id over.
        """
        visible: list[bool] = []
        monkeypatch.setattr(
            booking_api,
            "_trigger_new_booking_alert",
            lambda appointment_id: visible.append(_row_exists_elsewhere(appointment_id)),
        )

        await _book(client, client_tokens, collaborator, [service.id])
        assert visible == [True], "l'alert è stato accodato prima del commit"


def _row_exists_elsewhere(appointment_id: int) -> bool:
    """Look for the appointment over a fresh connection in its own event loop.

    A thread is what makes this honest: same-loop, same-session reads would see
    the caller's uncommitted work and always pass.
    """
    async def check() -> bool:
        eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        try:
            async with eng.connect() as conn:
                result = await conn.execute(
                    text("SELECT 1 FROM appointments WHERE id = :i"),
                    {"i": appointment_id},
                )
                return result.scalar() is not None
        finally:
            await eng.dispose()

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(lambda: asyncio.run(check())).result(timeout=15)


class TestWhoIsTold:
    async def test_admins_and_the_booked_collaborator(
        self, db, booking_config, client_account, collaborator, service, admin_user, sent
    ):
        appt = await _stored_appointment(db, client_account, collaborator, [service])
        recipients = await notifications.notify_staff_new_booking(db, appt)

        assert set(recipients) == {admin_user.email, collaborator.email}
        assert {to for to, _, _ in sent} == {admin_user.email, collaborator.email}

    async def test_a_collaborator_without_an_address_is_skipped(
        self, db, booking_config, client_account, collaborator, service, admin_user, sent
    ):
        collaborator.email = None
        await db.commit()

        appt = await _stored_appointment(db, client_account, collaborator, [service])
        assert await notifications.notify_staff_new_booking(db, appt) == [admin_user.email]

    async def test_a_deactivated_admin_is_not_written_to(
        self, db, booking_config, client_account, collaborator, service, sent
    ):
        db.add(User(
            email="ex-titolare@nsh-test.it",
            password_hash=await hash_password("x"),
            role=UserRole.admin,
            is_active=False,
        ))
        await db.commit()

        appt = await _stored_appointment(db, client_account, collaborator, [service])
        assert await notifications.notify_staff_new_booking(db, appt) == [collaborator.email]

    async def test_the_same_person_twice_gets_one_mail(
        self, db, booking_config, client_account, collaborator, service, admin_user, sent
    ):
        """An owner who both runs the salon and takes appointments is one inbox."""
        collaborator.email = admin_user.email.upper()  # same address, salon spelling
        await db.commit()

        appt = await _stored_appointment(db, client_account, collaborator, [service])
        assert await notifications.notify_staff_new_booking(db, appt) == [admin_user.email]

    async def test_one_dead_address_does_not_silence_the_others(
        self, db, monkeypatch, booking_config, client_account, collaborator, service, admin_user
    ):
        async def fail_for_the_admin(to: str, subject: str, html_body: str) -> None:
            if to == admin_user.email:
                raise RuntimeError("mailbox full")

        monkeypatch.setattr("app.utils.email.send_email", fail_for_the_admin)

        appt = await _stored_appointment(db, client_account, collaborator, [service])
        assert await notifications.notify_staff_new_booking(db, appt) == [collaborator.email]


class TestWhatTheMailSays:
    async def test_it_carries_everything_needed_to_answer(
        self, db, booking_config, client_account, collaborator_two_services, service,
        second_service, admin_user, sent,
    ):
        appt = await _stored_appointment(
            db, client_account, collaborator_two_services, [service, second_service]
        )
        await notifications.notify_staff_new_booking(db, appt)

        _, subject, body = next(t for t in sent if t[0] == admin_user.email)

        assert "Giulia Test" in subject
        assert "Giulia Test" in body
        assert "+393330000002" in body, "senza telefono il salone non può richiamare"
        assert appt.start_time.strftime("%d/%m/%Y alle %H:%M") in body
        assert "Sofia Test" in body
        # Both services, not just the first: a basket named halfway is how the
        # salon prepares for the wrong appointment.
        assert "Taglio test" in body
        assert "Barba test" in body
        assert "/admin/appointments/pending" in body

    async def test_a_booking_note_cannot_smuggle_markup(
        self, db, booking_config, client_account, collaborator, service, admin_user, sent
    ):
        """The note is typed by a stranger and lands in the salon's inbox."""
        appt = await _stored_appointment(
            db, client_account, collaborator, [service],
            notes='<a href="https://phish.example">clicca qui</a>',
        )
        await notifications.notify_staff_new_booking(db, appt)

        _, _, body = next(t for t in sent if t[0] == admin_user.email)
        assert "<a href=\"https://phish.example\"" not in body
        assert "&lt;a href=" in body


class TestTheTaskItself:
    async def test_it_reads_the_appointment_and_sends(
        self, db, booking_config, client_account, collaborator, service, admin_user, sent
    ):
        """End to end through the Celery body, which used to be a `print()`."""
        from app.tasks.reminders import _async_notify_new_booking

        appt = await _stored_appointment(db, client_account, collaborator, [service])
        await _async_notify_new_booking(appt.id)

        assert [to for to, _, _ in sent] == [admin_user.email, collaborator.email]

    async def test_a_deleted_appointment_is_survived(
        self, db, booking_config, admin_user, sent
    ):
        from app.tasks.reminders import _async_notify_new_booking

        await _async_notify_new_booking(999999)
        assert sent == []


async def _stored_appointment(db, client_account, collaborator, services, notes=None):
    """Commit a pending online booking and hand it back fully loaded."""
    from app.models.appointment import (
        AppointmentOrigin, AppointmentService, AppointmentStatus,
    )
    from app.models.client import Client

    c = (await db.execute(
        select(Client).where(Client.account_id == client_account.id)
    )).scalar_one()

    start = datetime.combine(TOMORROW, datetime.min.time(), tzinfo=timezone.utc).replace(hour=10)
    appt = Appointment(
        client_id=c.id,
        collaborator_id=collaborator.id,
        start_time=start,
        end_time=start + timedelta(hours=1),
        notes=notes,
        status=AppointmentStatus.pending,
        origin=AppointmentOrigin.online,
    )
    db.add(appt)
    await db.flush()
    for svc in services:
        db.add(AppointmentService(
            appointment_id=appt.id, service_id=svc.id, price_snapshot=float(svc.price),
        ))
    await db.commit()

    return (await db.execute(
        select(Appointment).options(*appointment_detail_loads()).where(Appointment.id == appt.id)
    )).scalar_one()
