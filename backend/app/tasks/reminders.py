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


# ── Periodic: email + WA reminders ───────────────────────────────

@celery_app.task(name="app.tasks.reminders.send_appointment_reminders")
def send_appointment_reminders():
    """Send email/WA reminders for upcoming appointments (runs every 15 min)."""
    _run_async(_async_send_reminders())


async def _async_send_reminders():
    from app.database import AsyncSessionLocal
    from app.models.appointment import Appointment, AppointmentStatus
    from app.models.booking_config import BookingConfig
    from app.utils.email import send_appointment_reminder
    from app.utils.whatsapp import send_reminder_message

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        cfg_result = await db.execute(select(BookingConfig).limit(1))
        cfg = cfg_result.scalar_one_or_none()

        # ── Email reminders (fixed 1–2 h window) ──────────────────
        email_window_start = now + timedelta(hours=1)
        email_window_end   = now + timedelta(hours=2)

        result = await db.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.client),
                selectinload(Appointment.collaborator),
                selectinload(Appointment.appointment_services),
            )
            .where(
                and_(
                    Appointment.start_time >= email_window_start,
                    Appointment.start_time <= email_window_end,
                    Appointment.status == AppointmentStatus.confirmed,
                    Appointment.reminder_sent == False,
                )
            )
        )
        for appt in result.scalars().all():
            if appt.client and appt.client.email:
                try:
                    await send_appointment_reminder(appt)
                    appt.reminder_sent = True
                except Exception as e:
                    print(f"[EMAIL] Reminder failed for appointment {appt.id}: {e}")

        # ── WhatsApp reminders (configurable hours, 15-min window) ─
        if cfg and cfg.whatsapp_enabled:
            hours = cfg.whatsapp_reminder_hours
            wa_window_start = now + timedelta(hours=hours)
            wa_window_end   = now + timedelta(hours=hours, minutes=15)

            wa_result = await db.execute(
                select(Appointment)
                .options(
                    selectinload(Appointment.client),
                    selectinload(Appointment.collaborator),
                )
                .where(
                    and_(
                        Appointment.start_time >= wa_window_start,
                        Appointment.start_time <= wa_window_end,
                        Appointment.status == AppointmentStatus.confirmed,
                        Appointment.whatsapp_reminder_sent == False,
                    )
                )
            )
            for appt in wa_result.scalars().all():
                if appt.client and appt.client.phone:
                    try:
                        await send_reminder_message(appt, cfg)
                        appt.whatsapp_reminder_sent = True
                    except Exception as e:
                        print(f"[WA] Reminder failed for appointment {appt.id}: {e}")

        await db.commit()


# ── Periodic: birthday greetings ─────────────────────────────────

@celery_app.task(name="app.tasks.reminders.send_birthday_greetings")
def send_birthday_greetings():
    """Send birthday greetings to clients whose birthday is today."""
    _run_async(_async_send_birthday_greetings())


async def _async_send_birthday_greetings():
    from app.database import AsyncSessionLocal
    from app.models.client import Client
    from app.utils.email import send_birthday_greeting

    today = datetime.now(timezone.utc).date()

    async with AsyncSessionLocal() as db:
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
                await send_birthday_greeting(client)
            except Exception as e:
                print(f"Failed to send birthday greeting for client {client.id}: {e}")


# ── One-shot: WA booking confirmation ────────────────────────────

@celery_app.task(name="app.tasks.reminders.send_whatsapp_confirmation")
def send_whatsapp_confirmation(appointment_id: int):
    """Send immediate WhatsApp booking confirmation to the client."""
    _run_async(_async_send_whatsapp_confirmation(appointment_id))


async def _async_send_whatsapp_confirmation(appointment_id: int):
    from app.database import AsyncSessionLocal
    from app.models.appointment import Appointment
    from app.models.booking_config import BookingConfig
    from app.utils.whatsapp import send_booking_confirmation

    async with AsyncSessionLocal() as db:
        cfg_result = await db.execute(select(BookingConfig).limit(1))
        cfg = cfg_result.scalar_one_or_none()
        if not cfg or not cfg.whatsapp_enabled:
            return

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

        try:
            await send_booking_confirmation(appt, cfg)
        except Exception as e:
            print(f"[WA] Confirmation failed for appointment {appt.id}: {e}")


@celery_app.task(name="app.tasks.reminders.notify_new_booking")
def notify_new_booking(appointment_id: int):
    """Notify salon staff of a new online booking."""
    _run_async(_async_notify_new_booking(appointment_id))


async def _async_notify_new_booking(appointment_id: int):
    # Placeholder: in production, send push/email to all admin users
    print(f"New online booking: appointment #{appointment_id}")
