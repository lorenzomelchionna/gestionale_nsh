"""Celery tasks for appointment reminders and booking notifications."""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_, extract
from app.tasks.celery_app import celery_app


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.reminders.send_appointment_reminders")
def send_appointment_reminders():
    """Send email reminders for appointments starting in 1-2 hours."""
    _run_async(_async_send_reminders())


async def _async_send_reminders():
    from app.database import AsyncSessionLocal
    from app.models.appointment import Appointment, AppointmentStatus
    from app.utils.email import send_appointment_reminder

    now = datetime.now(timezone.utc)
    window_start = now + timedelta(hours=1)
    window_end = now + timedelta(hours=2)

    async with AsyncSessionLocal() as db:
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
        appointments = result.scalars().all()

        for appt in appointments:
            if appt.client and appt.client.email:
                try:
                    await send_appointment_reminder(appt)
                    appt.reminder_sent = True
                except Exception as e:
                    print(f"Failed to send reminder for appointment {appt.id}: {e}")

        await db.commit()


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
        clients = result.scalars().all()

        for client in clients:
            try:
                await send_birthday_greeting(client)
            except Exception as e:
                print(f"Failed to send birthday greeting for client {client.id}: {e}")


@celery_app.task(name="app.tasks.reminders.notify_new_booking")
def notify_new_booking(appointment_id: int):
    """Notify salon staff of a new online booking."""
    _run_async(_async_notify_new_booking(appointment_id))


async def _async_notify_new_booking(appointment_id: int):
    from app.database import AsyncSessionLocal
    from app.models.appointment import Appointment
    from app.models.user import User, UserRole
    # Placeholder: in production, send push/email to all admin users
    print(f"New online booking: appointment #{appointment_id}")
