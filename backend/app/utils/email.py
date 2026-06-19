"""Email utility using smtplib (simple, no heavy deps)."""
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings


def _resolve_ipv4(host: str) -> str:
    """
    Return the IPv4 address for `host`.

    Railway containers resolve smtp.gmail.com to an IPv6 (AAAA) record but have
    no routable IPv6 egress, so the SMTP connection fails with
    "[Errno 101] Network is unreachable". Forcing IPv4 avoids this.
    """
    return socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]


async def send_email(to: str, subject: str, html_body: str) -> None:
    if not settings.SMTP_USER:
        print(f"[EMAIL STUB] To: {to} | Subject: {subject}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    # Connect over IPv4 explicitly (Railway has no IPv6 egress) but keep the
    # hostname for TLS certificate verification via starttls.
    host_ipv4 = _resolve_ipv4(settings.SMTP_HOST)
    with smtplib.SMTP(host_ipv4, settings.SMTP_PORT, timeout=30) as server:
        server.ehlo(settings.SMTP_HOST)
        server.starttls()
        server.ehlo(settings.SMTP_HOST)
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAILS_FROM_EMAIL, to, msg.as_string())


async def send_appointment_reminder(appointment) -> None:
    client = appointment.client
    if not client or not client.email:
        return
    collab = appointment.collaborator
    start = appointment.start_time.strftime("%d/%m/%Y alle %H:%M")
    collab_name = f"{collab.first_name} {collab.last_name}" if collab else "il tuo collaboratore"
    subject = f"Promemoria appuntamento – {start}"
    body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {client.first_name},</p>
    <p>Ti ricordiamo il tuo appuntamento <strong>{start}</strong> con <strong>{collab_name}</strong>.</p>
    <p>Se hai bisogno di cancellare o spostare, contattaci il prima possibile.</p>
    <p>A presto!</p>
    """
    await send_email(client.email, subject, body)


async def send_custom_message(client, subject: str, body: str) -> None:
    """Send a custom message to a client.

    NOTE: Currently email-only. To add SMS/WhatsApp: implement the provider
    call here using client.phone when no email is available.
    """
    if not client.email:
        print(f"[MESSAGING STUB] No email for {client.first_name} {client.last_name} (id={client.id})")
        return
    html_body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {client.first_name},</p>
    {body.replace(chr(10), '<br>')}
    <p>A presto,<br><strong>New Style Hair</strong></p>
    """
    await send_email(client.email, subject, html_body)


async def send_birthday_greeting(client) -> None:
    """Send a birthday greeting to a client.

    Currently email-only. To add SMS/WhatsApp: implement the provider call
    here alongside (or instead of) the email, using client.phone.
    """
    if not client.email:
        # TODO: fallback to SMS/WhatsApp when a provider is configured
        print(f"[BIRTHDAY STUB] No email for {client.first_name} {client.last_name} (id={client.id})")
        return
    subject = "Tanti auguri di buon compleanno! – New Style Hair"
    body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {client.first_name},</p>
    <p>Tutto il team di <strong>New Style Hair</strong> ti augura un <strong>felice compleanno</strong>! 🎉</p>
    <p>Passa a trovarci: il tuo giorno speciale merita una coccola in più.</p>
    <p>A presto e ancora tanti auguri!</p>
    """
    await send_email(client.email, subject, body)


async def send_booking_confirmation_email(appointment) -> None:
    """Email confirmation sent immediately when an appointment is confirmed."""
    client = appointment.client
    if not client or not client.email:
        return
    collab = appointment.collaborator
    start = appointment.start_time.strftime("%d/%m/%Y alle %H:%M")
    collab_name = f"{collab.first_name} {collab.last_name}" if collab else "il collaboratore"
    subject = f"Prenotazione confermata – {start}"
    body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {client.first_name},</p>
    <p>La tua prenotazione è <strong>confermata</strong>:</p>
    <ul>
      <li>Data: <strong>{start}</strong></li>
      <li>Con: <strong>{collab_name}</strong></li>
    </ul>
    <p>Ti aspettiamo!</p>
    """
    await send_email(client.email, subject, body)


async def send_password_reset_email(to_email: str, first_name: str, reset_url: str) -> None:
    """Email containing the password reset link."""
    subject = "Reset password – New Style Hair"
    body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {first_name or ''},</p>
    <p>Hai richiesto il reset della password. Clicca sul link qui sotto per impostarne una nuova:</p>
    <p><a href="{reset_url}">{reset_url}</a></p>
    <p>Il link è valido per 2 ore. Se non hai richiesto tu il reset, ignora questa email.</p>
    """
    await send_email(to_email, subject, body)


async def send_booking_status_email(appointment, status_msg: str) -> None:
    client = appointment.client
    if not client or not client.email:
        return
    subject = f"Aggiornamento prenotazione – New Style Hair"
    body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {client.first_name},</p>
    <p>{status_msg}</p>
    <p>Accedi alla tua area personale per maggiori dettagli.</p>
    """
    await send_email(client.email, subject, body)
