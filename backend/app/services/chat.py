"""
WhatsApp inbox: recording inbound messages and sending replies.

Meta's customer service window governs what the salon may send. Within
`REPLY_WINDOW_HOURS` of the client's last message a free-text reply is allowed;
outside it, only templates pre-approved by Meta. The window is a platform rule,
not a setting we control — it lives here as a single constant so the UI, the API
and any future change to Meta's policy all read the same number.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chat import (
    ChatMessage, Conversation, MessageDirection, MessageStatus,
)
from app.models.client import Client

REPLY_WINDOW_HOURS = 24

# Twilio's shared sandbox number. Messages from it only reach people who have
# sent the join code, so a deployment still pointing here is not live yet.
TWILIO_SANDBOX_FROM = "whatsapp:+14155238886"


def whatsapp_mode() -> str:
    """
    How the WhatsApp channel is currently wired.

    `not_configured` — no Twilio credentials: replies are logged, not sent.
    `sandbox`        — Twilio's shared test number: reaches only joined numbers.
    `production`     — a dedicated number registered with Meta.
    """
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_WHATSAPP_FROM):
        return "not_configured"
    if settings.TWILIO_WHATSAPP_FROM.strip() == TWILIO_SANDBOX_FROM:
        return "sandbox"
    return "production"


def normalise_phone(raw: str) -> str:
    """
    Reduce a phone number to a comparable form.

    Twilio prefixes WhatsApp numbers with `whatsapp:`; stored client numbers may
    carry spaces. Both are stripped so the same person maps to one conversation.
    """
    phone = (raw or "").strip()
    if phone.startswith("whatsapp:"):
        phone = phone[len("whatsapp:"):]
    phone = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if phone and not phone.startswith("+"):
        phone = "+" + phone
    return phone


def window_expires_at(conversation: Conversation) -> Optional[datetime]:
    if conversation.last_inbound_at is None:
        return None
    last = conversation.last_inbound_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last + timedelta(hours=REPLY_WINDOW_HOURS)


def can_reply_freely(conversation: Conversation, now: Optional[datetime] = None) -> bool:
    """Whether a free-text reply is still allowed under Meta's rules."""
    expires = window_expires_at(conversation)
    if expires is None:
        return False
    return (now or datetime.now(timezone.utc)) < expires


async def get_or_create_conversation(
    db: AsyncSession, phone: str, contact_name: Optional[str] = None
) -> Conversation:
    phone = normalise_phone(phone)
    conv = (await db.execute(
        select(Conversation).where(Conversation.phone == phone)
    )).scalar_one_or_none()

    if conv is None:
        conv = Conversation(phone=phone, contact_name=contact_name)
        # Attach a known client when the number matches, so the thread shows a
        # name and links to their history instead of a bare number.
        client = await find_client_by_phone(db, phone)
        if client:
            conv.client_id = client.id
        db.add(conv)
        await db.flush()
    elif contact_name and not conv.contact_name:
        conv.contact_name = contact_name

    return conv


async def find_client_by_phone(db: AsyncSession, phone: str) -> Optional[Client]:
    """
    Match a client by phone, ignoring formatting differences.

    Stored numbers are not guaranteed to be normalised, so comparison happens on
    the digits rather than the raw string.
    """
    target = normalise_phone(phone)
    if not target:
        return None
    clients = (await db.execute(select(Client))).scalars().all()
    for client in clients:
        if client.phone and normalise_phone(client.phone) == target:
            return client
    return None


async def record_inbound(
    db: AsyncSession,
    *,
    from_phone: str,
    body: str,
    provider_sid: Optional[str],
    contact_name: Optional[str] = None,
) -> Optional[ChatMessage]:
    """
    Store a message received from a client.

    Returns None when the provider SID has already been seen: Twilio retries
    webhooks it considers failed, and a retry must not duplicate the message.
    """
    if provider_sid:
        existing = (await db.execute(
            select(ChatMessage).where(ChatMessage.provider_sid == provider_sid)
        )).scalar_one_or_none()
        if existing:
            return None

    conv = await get_or_create_conversation(db, from_phone, contact_name)
    now = datetime.now(timezone.utc)

    message = ChatMessage(
        conversation_id=conv.id,
        direction=MessageDirection.inbound,
        body=body,
        status=MessageStatus.received,
        provider_sid=provider_sid,
    )
    db.add(message)

    conv.last_message_at = now
    conv.last_inbound_at = now
    conv.unread_count += 1
    conv.is_archived = False  # a new message pulls the thread back into the list

    await db.flush()
    return message


async def send_reply(
    db: AsyncSession,
    conversation: Conversation,
    body: str,
    sent_by_user_id: Optional[int] = None,
) -> ChatMessage:
    """
    Send a free-text reply and record it.

    The message row is written whatever happens, with the failure attached, so
    the operator can see that a reply did not go out instead of silently losing it.
    """
    message = ChatMessage(
        conversation_id=conversation.id,
        direction=MessageDirection.outbound,
        body=body,
        status=MessageStatus.queued,
        sent_by_user_id=sent_by_user_id,
    )
    db.add(message)

    try:
        sid = await _dispatch_whatsapp(conversation.phone, body)
        message.provider_sid = sid
        message.status = MessageStatus.sent
        conversation.last_message_at = datetime.now(timezone.utc)
    except Exception as exc:  # provider errors must not lose the message
        message.status = MessageStatus.failed
        message.error = str(exc)[:500]

    await db.flush()
    return message


async def _dispatch_whatsapp(to_phone: str, body: str) -> Optional[str]:
    """Send via Twilio and return the provider message id."""
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_WHATSAPP_FROM):
        print(f"[WA STUB] To: {to_phone} | Message: {body}")
        return None

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            data={
                "From": settings.TWILIO_WHATSAPP_FROM,
                "To": f"whatsapp:{normalise_phone(to_phone)}",
                "Body": body,
            },
            timeout=15.0,
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Twilio error {resp.status_code}: {resp.text}")
    return resp.json().get("sid")


async def mark_read(db: AsyncSession, conversation: Conversation) -> None:
    conversation.unread_count = 0
    await db.flush()
