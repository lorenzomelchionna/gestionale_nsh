"""L'appuntamento da salvare nel calendario della cliente.

Due modi, nella mail di conferma:
- un file `.ics` allegato: Apple Calendario, Outlook e Gmail lo aprono e
  propongono «Aggiungi»;
- un link «Aggiungi a Google Calendar», per chi legge la mail dal telefono
  dove l'allegato è scomodo.

Dentro solo servizio, data, ora e salone. Niente nome della cliente né del
collaboratore: un calendario personale si condivide (famiglia, lavoro) e
finisce sincronizzato su servizi che non controlliamo.

Scritto a mano e non con `icalendar`: un solo evento, orari in UTC (niente
blocco VTIMEZONE da mantenere), e le due regole del formato che contano —
caratteri speciali da proteggere e righe lunghe da spezzare — stanno in
dieci righe. `METHOD:PUBLISH` e niente ORGANIZER/ATTENDEE: è un evento da
salvare, non un invito; con l'invito Gmail mostrerebbe «Parteciperai?».
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable

from app.config import settings
from app.utils.tempo import adesso

NOME_SALONE = "New Style Hair"
INDIRIZZO_SALONE = "Corso Italia, 32, 83030 Melito Irpino (AV)"
DOMINIO_UID = "newstylehair.it"


def _utc(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _testo(valore: str) -> str:
    """RFC 5545 §3.3.11: backslash, punto e virgola, virgola e a capo."""
    return (valore.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))


def _piega(riga: str) -> str:
    """RFC 5545 §3.1: al massimo 75 byte per riga, il resto su righe che
    iniziano con uno spazio. Si taglia sui byte UTF-8 senza spezzare un
    carattere accentato a metà."""
    out, corrente = [], ""
    for c in riga:
        limite = 75 if not out else 74
        if len((corrente + c).encode("utf-8")) > limite:
            out.append(corrente)
            corrente = c
        else:
            corrente += c
    out.append(corrente)
    return "\r\n ".join(out)


def _caricato(oggetto, attributo: str) -> bool:
    """Se una relazione ORM è già in memoria. Leggerne una non caricata, in
    un contesto async, fa partire una query che fallisce (`MissingGreenlet`):
    per il titolo di un evento non vale la pena di rischiarlo."""
    try:
        return attributo not in sa_inspect(oggetto).unloaded
    except NoInspectionAvailable:
        return True  # non è un oggetto ORM (test, SimpleNamespace)


def _servizi(appointment) -> str:
    if not _caricato(appointment, "appointment_services"):
        return ""
    nomi = [
        s.service.name for s in (appointment.appointment_services or [])
        if _caricato(s, "service") and s.service is not None
    ]
    return " + ".join(nomi)


def _titolo(appointment) -> str:
    servizi = _servizi(appointment)
    return f"{NOME_SALONE} – {servizi}" if servizi else NOME_SALONE


def _descrizione() -> str:
    return (f"Per spostare o annullare l'appuntamento: {settings.FRONTEND_URL}/booking "
            f"oppure chiama il salone.")


def file_ics(appointment) -> bytes:
    """Il file `.ics` dell'appuntamento.

    UID fisso per appuntamento: se la stessa conferma partisse due volte, il
    calendario aggiorna l'evento invece di duplicarlo."""
    righe = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//New Style Hair//Gestionale//IT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:appuntamento-{appointment.id}@{DOMINIO_UID}",
        "SEQUENCE:0",
        f"DTSTAMP:{_utc(adesso())}",
        f"DTSTART:{_utc(appointment.start_time)}",
        f"DTEND:{_utc(appointment.end_time)}",
        f"SUMMARY:{_testo(_titolo(appointment))}",
        f"LOCATION:{_testo(INDIRIZZO_SALONE)}",
        f"DESCRIPTION:{_testo(_descrizione())}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_testo(_titolo(appointment))}",
        "TRIGGER:-PT2H",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(_piega(r) for r in righe) + "\r\n").encode("utf-8")


def link_google(appointment) -> str:
    """Il link che apre Google Calendar con l'evento già compilato."""
    parametri = {
        "action": "TEMPLATE",
        "text": _titolo(appointment),
        "dates": f"{_utc(appointment.start_time)}/{_utc(appointment.end_time)}",
        "location": INDIRIZZO_SALONE,
        "details": _descrizione(),
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(parametri)
