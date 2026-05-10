"""WhatsApp messaging via Twilio REST API (no twilio SDK needed — uses httpx)."""
import httpx
from app.config import settings

# Default message templates (used when BookingConfig fields are NULL)
DEFAULT_BOOKING_MESSAGE = (
    "Ciao {nome}! La tua prenotazione da New Style Hair è confermata "
    "per il {data} alle {ora} con {collaboratore}. A presto! 💇"
)
DEFAULT_REMINDER_MESSAGE = (
    "Ciao {nome}! Ti ricordiamo il tuo appuntamento da New Style Hair "
    "il {data} alle {ora} con {collaboratore}. A presto! 💇"
)


def _is_configured() -> bool:
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM)


def _render(template: str | None, default: str, **kwargs) -> str:
    """Render a message template with the given variables."""
    tpl = template or default
    try:
        return tpl.format(**kwargs)
    except KeyError:
        # Fallback: use default if template has bad placeholders
        return default.format(**kwargs)


async def send_whatsapp(to_phone: str, message: str) -> None:
    """
    Send a WhatsApp message via Twilio.

    `to_phone` must be in E.164 format (e.g. '+393331234567').
    If Twilio is not configured, logs to stdout (stub mode).
    """
    if not _is_configured():
        print(f"[WA STUB] To: {to_phone} | Message: {message}")
        return

    # Normalize phone: strip non-digits except leading +
    phone = to_phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            data={
                "From": settings.TWILIO_WHATSAPP_FROM,
                "To": f"whatsapp:{phone}",
                "Body": message,
            },
            timeout=10.0,
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Twilio error {resp.status_code}: {resp.text}")


async def send_booking_confirmation(appointment, cfg) -> None:
    """Send booking confirmation WhatsApp message."""
    client = appointment.client
    if not client or not client.phone:
        return

    collab = appointment.collaborator
    collab_name = f"{collab.first_name} {collab.last_name}" if collab else "il collaboratore"
    start = appointment.start_time
    message = _render(
        cfg.whatsapp_booking_message,
        DEFAULT_BOOKING_MESSAGE,
        nome=client.first_name,
        data=start.strftime("%d/%m/%Y"),
        ora=start.strftime("%H:%M"),
        collaboratore=collab_name,
    )
    await send_whatsapp(client.phone, message)


async def send_reminder_message(appointment, cfg) -> None:
    """Send reminder WhatsApp message before appointment."""
    client = appointment.client
    if not client or not client.phone:
        return

    collab = appointment.collaborator
    collab_name = f"{collab.first_name} {collab.last_name}" if collab else "il collaboratore"
    start = appointment.start_time
    message = _render(
        cfg.whatsapp_reminder_message,
        DEFAULT_REMINDER_MESSAGE,
        nome=client.first_name,
        data=start.strftime("%d/%m/%Y"),
        ora=start.strftime("%H:%M"),
        collaboratore=collab_name,
    )
    await send_whatsapp(client.phone, message)
