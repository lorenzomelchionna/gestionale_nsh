"""Email utility — Brevo HTTP API (preferred) with SMTP fallback."""
import html
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx
from app.config import settings

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def esc(value) -> str:
    """Escape a value on its way into an HTML email body.

    Every message in this module is an f-string of HTML, so anything
    interpolated is markup until proven otherwise. Names and notes reach here
    from three places — the sign-up form, the booking form and the salon's own
    records — and the first of those is an unauthenticated stranger, which
    makes `/register` a way to post arbitrary HTML from our own verified sender
    to any address. So the rule is applied everywhere rather than at the one
    spot that is obviously dangerous, because the obvious spot moves.
    """
    return html.escape("" if value is None else str(value))


def _resolve_ipv4(host: str) -> str:
    """
    Return the IPv4 address for `host`.

    Railway containers resolve smtp.gmail.com to an IPv6 (AAAA) record but have
    no routable IPv6 egress, so the SMTP connection fails with
    "[Errno 101] Network is unreachable". Forcing IPv4 avoids this.
    """
    return socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]


async def _send_via_brevo(to: str, subject: str, html_body: str) -> None:
    """Send through Brevo's transactional email HTTP API (works behind SMTP blocks)."""
    payload = {
        "sender": {"name": settings.EMAILS_FROM_NAME, "email": settings.EMAILS_FROM_EMAIL},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html_body,
    }
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "Content-Type": "application/json",
        "accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(BREVO_ENDPOINT, json=payload, headers=headers)
    if resp.status_code not in (200, 201, 202):
        raise RuntimeError(f"Brevo error {resp.status_code}: {resp.text}")


def _send_via_smtp(to: str, subject: str, html_body: str) -> None:
    """Fallback SMTP path (used for local dev; cloud hosts often block outbound SMTP)."""
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


async def send_email(to: str, subject: str, html_body: str) -> None:
    # Prefer Brevo HTTP API (HTTPS is not blocked on cloud hosts).
    if settings.BREVO_API_KEY:
        await _send_via_brevo(to, subject, html_body)
        return
    # Fallback to SMTP (e.g. local dev).
    if settings.SMTP_USER:
        _send_via_smtp(to, subject, html_body)
        return
    print(f"[EMAIL STUB] To: {to} | Subject: {subject}")


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
    <p>Ciao {esc(client.first_name)},</p>
    <p>Ti ricordiamo il tuo appuntamento <strong>{esc(start)}</strong> con <strong>{esc(collab_name)}</strong>.</p>
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
    # Escaped first, then newlines become breaks: staff write plain text in the
    # Messaggi page, so the line breaks are the only markup they mean to send.
    html_body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {esc(client.first_name)},</p>
    {esc(body).replace(chr(10), '<br>')}
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
    <p>Ciao {esc(client.first_name)},</p>
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
    <p>Ciao {esc(client.first_name)},</p>
    <p>La tua prenotazione è <strong>confermata</strong>:</p>
    <ul>
      <li>Data: <strong>{esc(start)}</strong></li>
      <li>Con: <strong>{esc(collab_name)}</strong></li>
    </ul>
    <p>Ti aspettiamo!</p>
    """
    await send_email(client.email, subject, body)


async def send_new_booking_staff_email(to_email: str, appointment) -> None:
    """Tell the salon that a client booked online and is waiting for an answer.

    This is the only message in this module that goes to staff rather than to a
    client, and the only one carrying text a stranger typed: the client's own
    name and notes. Everything interpolated here is escaped, because the
    recipient is an inbox we control and an unescaped `<a href>` in a booking
    note would be a phishing link with the salon's own sender on it.
    """
    client = appointment.client
    collab = appointment.collaborator
    start = appointment.start_time.strftime("%d/%m/%Y alle %H:%M")

    client_name = f"{client.first_name} {client.last_name}" if client else "Cliente sconosciuto"
    collab_name = f"{collab.first_name} {collab.last_name}" if collab else "—"
    services = " + ".join(
        s.service.name for s in appointment.appointment_services if s.service
    ) or "—"

    e = esc
    rows = [
        f"<li>Cliente: <strong>{e(client_name)}</strong></li>",
        f"<li>Quando: <strong>{e(start)}</strong></li>",
        f"<li>Con: <strong>{e(collab_name)}</strong></li>",
        f"<li>Servizi: <strong>{e(services)}</strong></li>",
    ]
    if client and client.phone:
        rows.insert(1, f"<li>Telefono: <strong>{e(client.phone)}</strong></li>")

    note_block = (
        f"<p>Note del cliente: <em>{e(appointment.notes)}</em></p>"
        if appointment.notes else ""
    )
    pending_url = f"{settings.FRONTEND_URL.rstrip('/')}/admin/appointments/pending"

    subject = f"Nuova prenotazione online – {start} – {client_name}"
    body = f"""
    <h2>New Style Hair</h2>
    <p><strong>Nuova prenotazione online</strong>, in attesa di conferma.</p>
    <ul>{''.join(rows)}</ul>
    {note_block}
    <p><a href="{e(pending_url)}">Apri le richieste in attesa</a></p>
    <p>Il cliente non riceve conferma finché la richiesta non viene accettata.</p>
    """
    await send_email(to_email, subject, body)


async def send_password_reset_email(to_email: str, first_name: str, reset_url: str) -> None:
    """Email containing the password reset link."""
    subject = "Reset password – New Style Hair"
    body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {esc(first_name)},</p>
    <p>Hai richiesto il reset della password. Clicca sul link qui sotto per impostarne una nuova:</p>
    <p><a href="{esc(reset_url)}">{esc(reset_url)}</a></p>
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
    <p>Ciao {esc(client.first_name)},</p>
    <p>{esc(status_msg)}</p>
    <p>Accedi alla tua area personale per maggiori dettagli.</p>
    """
    await send_email(client.email, subject, body)


async def send_verification_code_email(
    to_email: str, first_name: str, code: str, ttl_minutes: int
) -> None:
    """Email carrying the sign-up confirmation code."""
    subject = "Conferma il tuo indirizzo – New Style Hair"
    body = f"""
    <h2>New Style Hair</h2>
    <p>Ciao {esc(first_name)},</p>
    <p>Per completare la registrazione inserisci questo codice:</p>
    <p style="font-size:28px;font-weight:bold;letter-spacing:6px">{esc(code)}</p>
    <p>Il codice è valido per {ttl_minutes} minuti.</p>
    <p>Se non hai richiesto tu la registrazione, ignora questa email:
       senza il codice l'account non viene attivato.</p>
    """
    await send_email(to_email, subject, body)
