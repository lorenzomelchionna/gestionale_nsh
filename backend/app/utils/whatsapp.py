"""WhatsApp messaging via Twilio REST API (no twilio SDK needed — uses httpx)."""
import json
import logging
import httpx
from app.config import settings
from app.logging_config import maschera_telefono

log = logging.getLogger("nsh.whatsapp")

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


async def _invia(to_phone: str, contenuto: dict[str, str]) -> None:
    """Parte comune fra testo libero e template: configurazione, numero, POST.

    `contenuto` porta la sola differenza fra i due — `Body` per il testo
    libero, `ContentSid` più `ContentVariables` per un template approvato.
    """
    if not _is_configured():
        # Il testo del messaggio non entra nel log: contiene il nome della
        # cliente e l'orario del suo appuntamento, cioè esattamente i dati che
        # i log non devono duplicare. Che il messaggio non sia partito si vede
        # lo stesso, ed è l'unica informazione azionabile.
        log.warning(
            "Twilio non configurato: messaggio WhatsApp non inviato",
            extra={"destinatario": maschera_telefono(to_phone)},
        )
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
                **contenuto,
            },
            timeout=10.0,
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Twilio error {resp.status_code}: {resp.text}")


async def send_whatsapp(to_phone: str, message: str) -> None:
    """
    Manda testo libero via Twilio.

    **Vale solo dentro la finestra di 24 ore** da un messaggio della cliente.
    Fuori, WhatsApp lo rifiuta (errore 63016) e serve un template approvato:
    vedi `send_whatsapp_template`. Le risposte dalla pagina Chat stanno dentro
    la finestra per definizione — esistono perché la cliente ha scritto — ed è
    l'unico posto in cui questa funzione va chiamata da sola.

    `to_phone` in E.164 (es. '+393331234567'). Se Twilio non è configurato,
    scrive un avviso e non manda niente.
    """
    await _invia(to_phone, {"Body": message})


async def send_whatsapp_template(
    to_phone: str,
    content_sid: str,
    variabili: dict[str, str],
    *,
    ripiego: str,
) -> None:
    """
    Manda un template approvato da Meta.

    È la forma obbligatoria per i messaggi che **parte il salone**: conferme,
    promemoria, auguri, reset password. Quelli arrivano a freddo, quindi quasi
    sempre fuori dalla finestra di 24 ore.

    `variabili` sono posizionali, come vuole Meta: `{"1": "Giulia", "2": ...}`
    riempie `{{1}}`, `{{2}}` nel testo approvato. L'ordine è quello con cui il
    template è stato scritto, quindi cambiare il template senza cambiare qui
    sposta i valori nei posti sbagliati — è il motivo per cui ogni chiamata
    costruisce il dizionario per esteso invece di passare una lista.

    **`ripiego` non è una rete di sicurezza per la produzione.** Serve finché
    `content_sid` è vuoto, cioè in Sandbox e nel tempo in cui Meta sta ancora
    approvando: lì il testo libero funziona e permette di provare tutto il
    percorso. In produzione, senza template, quel testo verrebbe rifiutato da
    WhatsApp — il ripiego non lo salva, lo fa solo fallire con un errore
    parlante invece che con un `None` silenzioso.
    """
    if not content_sid:
        log.info(
            "nessun template configurato: invio come testo libero",
            extra={
                "destinatario": maschera_telefono(to_phone),
                # Il testo no, il *perché* sì: senza questa riga un salone che
                # ha dimenticato di configurare un SID dopo l'approvazione se
                # ne accorge solo quando le clienti smettono di ricevere.
                "motivo": "content_sid_assente",
            },
        )
        await send_whatsapp(to_phone, ripiego)
        return

    await _invia(to_phone, {
        "ContentSid": content_sid,
        "ContentVariables": json.dumps(variabili, ensure_ascii=False),
    })


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
    await send_whatsapp_template(
        client.phone,
        settings.TWILIO_TEMPLATE_CONFERMA,
        {
            "1": client.first_name,
            "2": start.strftime("%d/%m/%Y"),
            "3": start.strftime("%H:%M"),
            "4": collab_name,
        },
        ripiego=message,
    )


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
    await send_whatsapp_template(
        client.phone,
        settings.TWILIO_TEMPLATE_PROMEMORIA,
        {
            "1": client.first_name,
            "2": start.strftime("%d/%m/%Y"),
            "3": start.strftime("%H:%M"),
            "4": collab_name,
        },
        ripiego=message,
    )


async def send_birthday_message(client) -> None:
    """Send birthday greeting via WhatsApp."""
    if not client.phone:
        return
    message = (
        f"Ciao {client.first_name}! 🎉 Tutto il team di New Style Hair ti augura "
        f"un felice compleanno. Passa a trovarci, il tuo giorno speciale "
        f"merita una coccola in più. 💇"
    )
    await send_whatsapp_template(
        client.phone,
        settings.TWILIO_TEMPLATE_COMPLEANNO,
        {"1": client.first_name},
        ripiego=message,
    )


async def send_password_reset_message(phone: str, first_name: str, reset_url: str) -> None:
    """Send password reset link via WhatsApp."""
    message = (
        f"Ciao {first_name or ''}! Hai richiesto il reset della password "
        f"per New Style Hair. Apri questo link per impostarne una nuova "
        f"(valido 2h): {reset_url}"
    )
    await send_whatsapp_template(
        phone,
        settings.TWILIO_TEMPLATE_RESET_PASSWORD,
        {"1": first_name or "", "2": reset_url},
        ripiego=message,
    )


async def send_custom_message_wa(client, body: str) -> None:
    """Messaggio libero dalla pagina Messaggi — testo semplice, niente HTML.

    **Resta testo libero, e questo è il limite da conoscere**: arriva solo a
    chi ha scritto al salone nelle ultime 24 ore. Fuori da quella finestra
    WhatsApp lo rifiuta, e non c'è un template da usare al suo posto — per
    definizione un messaggio scritto a mano non è un testo pre-approvato.

    Non è un difetto da correggere qui: è come funziona WhatsApp. Chi scrive
    a una cliente che non ha scritto per prima deve usare l'email, oppure uno
    dei messaggi automatici, che i template ce l'hanno.
    """
    if not client.phone:
        return
    # Personalizza con il nome se possibile (template con {nome})
    text = body.replace("{nome}", client.first_name)
    await send_whatsapp(client.phone, text)
