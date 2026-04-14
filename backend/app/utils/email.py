"""Email utility using smtplib (simple, no heavy deps)."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings


async def send_email(to: str, subject: str, html_body: str) -> None:
    if not settings.SMTP_USER:
        print(f"[EMAIL STUB] To: {to} | Subject: {subject}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
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
