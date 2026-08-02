"""
Notification orchestrator — single entry point for all client-facing messages.

Each event tries BOTH channels (email + WhatsApp) when contacts/config allow.
Failures on one channel never block the other.

For custom messages (admin Messaggi page), the caller picks the channel(s).
"""
from typing import Literal, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.booking_config import BookingConfig
from app.models.client import Client
from app.utils import email as email_util
from app.utils import whatsapp as wa_util


Channel = Literal["email", "whatsapp", "both"]


async def _get_config(db: AsyncSession) -> Optional[BookingConfig]:
    result = await db.execute(select(BookingConfig).limit(1))
    return result.scalar_one_or_none()


def _wa_enabled(cfg: Optional[BookingConfig]) -> bool:
    return bool(cfg and cfg.whatsapp_enabled)


# ── Per-event orchestrators ──────────────────────────────────────────

async def notify_booking_confirmation(db: AsyncSession, appointment) -> None:
    """Sent when an appointment is confirmed (admin create or pending→confirmed)."""
    cfg = await _get_config(db)
    client = appointment.client
    if not client:
        return
    if client.email:
        try:
            await email_util.send_booking_confirmation_email(appointment)
        except Exception as e:
            print(f"[NOTIFY:booking-confirm:email] appt={appointment.id} err={e}")
    if _wa_enabled(cfg) and client.phone:
        try:
            await wa_util.send_booking_confirmation(appointment, cfg)
        except Exception as e:
            print(f"[NOTIFY:booking-confirm:wa] appt={appointment.id} err={e}")


async def notify_appointment_reminder(db: AsyncSession, appointment) -> None:
    """Sent X hours before the appointment (cfg.whatsapp_reminder_hours)."""
    cfg = await _get_config(db)
    client = appointment.client
    if not client:
        return
    if client.email:
        try:
            await email_util.send_appointment_reminder(appointment)
        except Exception as e:
            print(f"[NOTIFY:reminder:email] appt={appointment.id} err={e}")
    if _wa_enabled(cfg) and client.phone:
        try:
            await wa_util.send_reminder_message(appointment, cfg)
        except Exception as e:
            print(f"[NOTIFY:reminder:wa] appt={appointment.id} err={e}")


async def notify_staff_new_booking(db: AsyncSession, appointment) -> list[str]:
    """Sent when a client books online — the request lands as `pending` and
    nobody in the salon is told unless this runs.

    Goes to everyone who can actually answer it: the admins, plus the
    collaborator the slot was booked with, since confirming is a `staff`-level
    action and not an admin-only one. Email only — WhatsApp reaches staff
    through the same Twilio Sandbox that only talks to numbers which have sent
    `join`, so it would be a channel that silently drops messages.

    Returns the addresses written to, so the caller can log an empty salon
    instead of assuming it worked.
    """
    from app.models.user import User, UserRole

    recipients: list[str] = []
    seen: set[str] = set()

    admins = await db.execute(
        select(User).where(User.role == UserRole.admin, User.is_active == True)  # noqa: E712
    )
    for user in admins.scalars().all():
        if user.email and user.email.lower() not in seen:
            seen.add(user.email.lower())
            recipients.append(user.email)

    collab = appointment.collaborator
    if collab and collab.email and collab.email.lower() not in seen:
        seen.add(collab.email.lower())
        recipients.append(collab.email)

    sent: list[str] = []
    for address in recipients:
        try:
            await email_util.send_new_booking_staff_email(address, appointment)
            sent.append(address)
        except Exception as e:
            print(f"[NOTIFY:new-booking:email] appt={appointment.id} to={address} err={e}")
    return sent


async def notify_birthday(db: AsyncSession, client) -> None:
    """Sent every morning to clients whose birthday is today."""
    cfg = await _get_config(db)
    if client.email:
        try:
            await email_util.send_birthday_greeting(client)
        except Exception as e:
            print(f"[NOTIFY:birthday:email] client={client.id} err={e}")
    if _wa_enabled(cfg) and client.phone:
        try:
            await wa_util.send_birthday_message(client)
        except Exception as e:
            print(f"[NOTIFY:birthday:wa] client={client.id} err={e}")


async def notify_password_reset(
    db: AsyncSession, account, reset_url: str
) -> None:
    """Sent when a client requests a password reset."""
    cfg = await _get_config(db)
    # Find linked client (for first_name + phone)
    client_result = await db.execute(
        select(Client).where(Client.account_id == account.id)
    )
    client = client_result.scalar_one_or_none()
    first_name = client.first_name if client else ""

    # Email
    try:
        await email_util.send_password_reset_email(account.email, first_name, reset_url)
    except Exception as e:
        print(f"[NOTIFY:reset:email] account={account.id} err={e}")

    # WhatsApp (only if linked client has a phone)
    if _wa_enabled(cfg) and client and client.phone:
        try:
            await wa_util.send_password_reset_message(client.phone, first_name, reset_url)
        except Exception as e:
            print(f"[NOTIFY:reset:wa] account={account.id} err={e}")


async def notify_custom(
    db: AsyncSession,
    client,
    subject: str,
    body: str,
    channel: Channel = "both",
) -> tuple[bool, bool]:
    """
    Send a custom message on the chosen channel(s).
    Returns (email_ok, wa_ok) — True if a real send happened on that channel.
    """
    cfg = await _get_config(db)
    email_ok = False
    wa_ok = False

    if channel in ("email", "both") and client.email:
        try:
            await email_util.send_custom_message(client, subject, body)
            email_ok = True
        except Exception as e:
            print(f"[NOTIFY:custom:email] client={client.id} err={e}")

    if channel in ("whatsapp", "both") and _wa_enabled(cfg) and client.phone:
        try:
            await wa_util.send_custom_message_wa(client, body)
            wa_ok = True
        except Exception as e:
            print(f"[NOTIFY:custom:wa] client={client.id} err={e}")

    return email_ok, wa_ok
