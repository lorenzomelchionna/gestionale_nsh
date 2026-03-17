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
