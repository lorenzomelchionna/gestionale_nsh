"""Celery tasks for appointment reminders and booking notifications."""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_, extract
from sqlalchemy.orm import selectinload
from app.tasks.celery_app import celery_app


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Periodic: reminders (email + WA, single timing) ──────────────

@celery_app.task(name="app.tasks.reminders.send_appointment_reminders")
def send_appointment_reminders():
    """
    Send reminders (email + WhatsApp) for appointments starting in
    `whatsapp_reminder_hours` from now (default 24h). Runs every 15 min.
    """
    _run_async(_async_send_reminders())


async def _async_send_reminders():
    from app.database import create_task_session_factory
    from app.models.appointment import Appointment, AppointmentStatus
    from app.models.booking_config import BookingConfig
    from app.utils.notifications import notify_appointment_reminder

    now = datetime.now(timezone.utc)

    task_engine, session_factory = create_task_session_factory()
    try:
        async with session_factory() as db:
            cfg_result = await db.execute(select(BookingConfig).limit(1))
            cfg = cfg_result.scalar_one_or_none()

            # Single configurable window — used for both channels
            hours = cfg.whatsapp_reminder_hours if cfg else 24
            window_start = now + timedelta(hours=hours)
            window_end   = now + timedelta(hours=hours, minutes=15)

            result = await db.execute(
                select(Appointment)
                .options(
                    selectinload(Appointment.client),
                    selectinload(Appointment.collaborator),
                    selectinload(Appointment.appointment_services),
                )
                .where(
                    and_(
                        Appointment.start_time >= window_start,
                        Appointment.start_time <= window_end,
                        Appointment.status == AppointmentStatus.confirmed,
                        Appointment.reminder_sent == False,
                    )
                )
            )
            for appt in result.scalars().all():
                try:
                    await notify_appointment_reminder(db, appt)
                    appt.reminder_sent = True
                    appt.whatsapp_reminder_sent = True
                except Exception as e:
                    print(f"[REMINDER] failed for appointment {appt.id}: {e}")

            await db.commit()
    finally:
        await task_engine.dispose()


# ── Periodic: birthday greetings ─────────────────────────────────

@celery_app.task(name="app.tasks.reminders.send_birthday_greetings")
def send_birthday_greetings():
    """Send birthday greetings (email + WA) every day."""
    _run_async(_async_send_birthday_greetings())


async def _async_send_birthday_greetings():
    from app.database import create_task_session_factory
    from app.models.client import Client
    from app.utils.notifications import notify_birthday

    today = datetime.now(timezone.utc).date()

    task_engine, session_factory = create_task_session_factory()
    try:
        async with session_factory() as db:
            result = await db.execute(
                select(Client).where(
                    and_(
                        Client.birth_date.isnot(None),
                        extract("month", Client.birth_date) == today.month,
                        extract("day", Client.birth_date) == today.day,
                    )
                )
            )
            for client in result.scalars().all():
                try:
                    await notify_birthday(db, client)
                except Exception as e:
                    print(f"[BIRTHDAY] failed for client {client.id}: {e}")
    finally:
        await task_engine.dispose()


# ── One-shot: booking confirmation (email + WA) ──────────────────

@celery_app.task(name="app.tasks.reminders.send_booking_confirmation")
def send_booking_confirmation_task(appointment_id: int):
    """Sent immediately when an appointment is confirmed (email + WA)."""
    _run_async(_async_send_booking_confirmation(appointment_id))


async def _async_send_booking_confirmation(appointment_id: int):
    from app.database import create_task_session_factory
    from app.models.appointment import Appointment
    from app.utils.notifications import notify_booking_confirmation

    task_engine, session_factory = create_task_session_factory()
    try:
        async with session_factory() as db:
            result = await db.execute(
                select(Appointment)
                .options(
                    selectinload(Appointment.client),
                    selectinload(Appointment.collaborator),
                )
                .where(Appointment.id == appointment_id)
            )
            appt = result.scalar_one_or_none()
            if not appt:
                return
            await notify_booking_confirmation(db, appt)
    finally:
        await task_engine.dispose()


@celery_app.task(name="app.tasks.reminders.notify_new_booking")
def notify_new_booking(appointment_id: int):
    """Notify salon staff of a new online booking."""
    _run_async(_async_notify_new_booking(appointment_id))


async def _async_notify_new_booking(appointment_id: int):
    from app.database import create_task_session_factory
    from app.models.appointment import Appointment, appointment_detail_loads
    from app.utils.notifications import notify_staff_new_booking

    task_engine, session_factory = create_task_session_factory()
    try:
        async with session_factory() as db:
            result = await db.execute(
                select(Appointment)
                .options(*appointment_detail_loads())
                .where(Appointment.id == appointment_id)
            )
            appt = result.scalar_one_or_none()
            if not appt:
                print(f"[NEW-BOOKING] appointment {appointment_id} vanished before notifying")
                return
            sent = await notify_staff_new_booking(db, appt)
            # An online booking nobody hears about is the failure this task
            # exists to prevent, so a silent salon is logged as a problem
            # rather than as a successful run.
            if not sent:
                print(f"[NEW-BOOKING] appointment {appointment_id}: no staff address to notify")
    finally:
        await task_engine.dispose()


# Backwards compat alias (old call site used send_whatsapp_confirmation)
@celery_app.task(name="app.tasks.reminders.send_whatsapp_confirmation")
def send_whatsapp_confirmation(appointment_id: int):
    """Deprecated alias — routes to the dual-channel confirmation task."""
    _run_async(_async_send_booking_confirmation(appointment_id))


@celery_app.task(name="app.tasks.reminders.send_gift_card")
def send_gift_card_task(gift_card_id: int):
    """Manda il buono al destinatario, appena la vendita è registrata."""
    _run_async(_async_send_gift_card(gift_card_id))


async def _async_send_gift_card(gift_card_id: int):
    from datetime import datetime, timezone

    from app.database import create_task_session_factory
    from app.models.gift_card import GiftCard
    from app.utils.email import send_gift_card_email

    task_engine, session_factory = create_task_session_factory()
    try:
        async with session_factory() as db:
            result = await db.execute(
                select(GiftCard).where(GiftCard.id == gift_card_id)
            )
            card = result.scalar_one_or_none()
            if not card:
                return
            await send_gift_card_email(card)
            # Segnato solo dopo l'invio riuscito: se `send_gift_card_email`
            # solleva, il campo resta vuoto e la scheda continua a dire che
            # l'email non è mai partita — che è la verità.
            card.email_sent_at = datetime.now(timezone.utc)
            await db.commit()
    finally:
        await task_engine.dispose()
