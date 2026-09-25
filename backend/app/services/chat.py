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
        db.add(conv)
    elif contact_name and contact_name != conv.contact_name:
        # Il nome del profilo WhatsApp lo sceglie la persona e lo può cambiare:
        # vale l'ultimo. Prima si fissava al primo messaggio e non si
        # aggiornava più, quindi la chat poteva mostrare un nome che il
        # contatto non usa da mesi.
        conv.contact_name = contact_name

    # Attach a known client when the number matches, so the thread shows a
    # name and links to their history instead of a bare number. Tried on every
    # message, not only when the thread is created: someone who wrote before
    # the salon had a record for them — or before they booked without an
    # account — would otherwise keep showing their WhatsApp name for good.
    if conv.client_id is None:
        client = await find_client_by_phone(db, phone)
        if client:
            conv.client_id = client.id

    await db.flush()
    return conv


async def find_client_by_phone(db: AsyncSession, phone: str) -> Optional[Client]:
    """
    The one active client with this number, or None.

    Stored numbers are not guaranteed to be normalised, so comparison happens on
    the digits rather than the raw string.

    None, rather than a guess, when two active records share the number —
    mother and daughter on the home landline. Picking one would put a name on
    the thread that is right half the time; the WhatsApp profile name is at
    least the sender's own. A deactivated record ("Elimina", or the losing side
    of a merge) is not a candidate: it stands for nobody any more.
    """
    target = normalise_phone(phone)
    if not target:
        return None
    clients = (await db.execute(
        select(Client).where(Client.is_active == True)  # noqa: E712 — confronto SQL
    )).scalars().all()
    matches = [c for c in clients if c.phone and normalise_phone(c.phone) == target]
    return matches[0] if len(matches) == 1 else None


async def collega_conversazione(db: AsyncSession, client: Client) -> None:
    """Dà il nome della scheda alla chat di quel numero, appena la scheda c'è.

    Il collegamento al messaggio in arrivo (`get_or_create_conversation`)
    arriva tardi per il caso più comune: una persona scrive, il salone la
    registra, e la chat continua a mostrare il nome del profilo WhatsApp
    finché lei non scrive di nuovo — che può essere fra un mese. Chiamata
    quando una scheda nasce o prende un numero, chiude quel vuoto.

    Stessa regola del collegamento in arrivo: solo se questa è l'**unica**
    scheda attiva con quel numero. Vale anche per una chat già collegata: se
    la sua scheda il numero non ce l'ha più — cambiato, o scheda eliminata —
    la chat segue il numero. Se ce l'ha ancora, le schede col numero sono
    due e la regola lascia tutto com'è.
    """
    if not client.phone or not client.is_active:
        return
    numero = normalise_phone(client.phone)
    conv = (await db.execute(
        select(Conversation).where(Conversation.phone == numero)
    )).scalar_one_or_none()
    if conv is None or conv.client_id == client.id:
        return
    unica = await find_client_by_phone(db, numero)
    if unica is not None and unica.id == client.id:
        conv.client_id = client.id
        await db.flush()


async def record_inbound(
    db: AsyncSession,
    *,
    from_phone: str,
    body: str,
    provider_sid: Optional[str],
    contact_name: Optional[str] = None,
    media: Optional[list[dict[str, str]]] = None,
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
        media=media or None,
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


# ── Allegati ──────────────────────────────────────────────────────

# Il più grosso che WhatsApp consegna è un video da 16 MB. Oltre, non è un
# allegato di una cliente: si smette di leggere invece di tenerlo in memoria.
MAX_ALLEGATO_BYTES = 20 * 1024 * 1024


class AllegatoNonDisponibile(Exception):
    """Twilio non ha dato il file: credenziali mancanti, file cancellato, rete."""


async def scarica_allegato(url: str) -> tuple[bytes, Optional[str]]:
    """Il file dietro un URL media di Twilio, col suo tipo.

    Twilio lo protegge con le credenziali dell'account (senza: 401, provato
    il 2026-09-25) e poi rimanda a un indirizzo firmato su un altro dominio.
    httpx toglie da sé l'intestazione di autenticazione quando il redirect
    cambia dominio, quindi le credenziali non escono dall'API di Twilio.
    """
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN):
        raise AllegatoNonDisponibile("Twilio non configurato")
    if not url.startswith("https://api.twilio.com/"):
        raise AllegatoNonDisponibile("URL non di Twilio")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as http:
            async with http.stream(
                "GET", url, auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            ) as resp:
                if resp.status_code != 200:
                    raise AllegatoNonDisponibile(f"Twilio ha risposto {resp.status_code}")
                pezzi, totale = [], 0
                async for pezzo in resp.aiter_bytes():
                    totale += len(pezzo)
                    if totale > MAX_ALLEGATO_BYTES:
                        raise AllegatoNonDisponibile("allegato troppo grande")
                    pezzi.append(pezzo)
                return b"".join(pezzi), resp.headers.get("content-type")
    except httpx.HTTPError as e:
        raise AllegatoNonDisponibile(str(e)) from e


def etichetta_allegato(content_type: str) -> str:
    """Come chiamare un allegato dove c'è posto solo per una riga."""
    tipo = (content_type or "").split("/")[0]
    return {
        "image": "📷 Foto",
        "audio": "🎤 Messaggio vocale",
        "video": "🎬 Video",
    }.get(tipo, "📎 Allegato")
