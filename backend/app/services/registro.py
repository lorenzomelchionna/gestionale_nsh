"""Registro dei messaggi inviati: chi scrive, chi aggiorna lo stato, chi pulisce.

Il modello e il perché stanno in `models/registro_messaggi.py`. Qui c'è come
si usa:

    with invio("conferma", client_id=c.id, appointment_id=a.id):
        await email_util.send_booking_confirmation_email(a)

`invio` dice *che cosa* si sta mandando; il punto che spedisce davvero
(`whatsapp._invia`, `chat._dispatch_whatsapp`, `email.send_email`) chiama
`registra` e trova il contesto da sé. Così chi aggiunge un tipo di messaggio
domani non deve ricordarsi di scrivere nel registro: al massimo il tipo
risulta `altro`, e il testo non si salva finché non lo dichiara.
"""
from __future__ import annotations

import html
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.registro_messaggi import RegistroMessaggio

log = logging.getLogger("nsh.notifiche")

#: Sei mesi, decisione di Lorenzo (2026-11-20): sono dati personali di tutte
#: le clienti, e un registro senza scadenza cresce per sempre.
CONSERVAZIONE_GIORNI = 183

#: I tipi e come si leggono nella pagina. Le chiavi finiscono nel database:
#: rinominarle lascia le righe vecchie col nome vecchio.
TIPI: dict[str, str] = {
    "conferma": "Conferma appuntamento",
    "promemoria": "Promemoria",
    "compleanno": "Auguri di compleanno",
    "messaggio_manuale": "Messaggio dalla pagina Messaggi",
    "risposta_chat": "Risposta in chat",
    "codice_verifica": "Codice di verifica",
    "codice_ospite": "Codice prenotazione senza account",
    "reset_password": "Reset password",
    "buono_regalo": "Buono regalo",
    "avviso_nuova_prenotazione": "Avviso allo staff: nuova prenotazione",
    "avviso_modifica": "Avviso allo staff: richiesta di modifica",
    "avviso_annullamento": "Avviso allo staff: annullamento",
    "altro": "Altro",
}

#: Di questi si conserva il testo. Gli altri no, e non per spazio: codici di
#: verifica, link di reset e codici dei buoni sono chiavi d'accesso, e un
#: registro che li tiene diventa il posto da cui rubarle. Elenco di quelli
#: permessi, non di quelli vietati: un tipo nuovo parte senza testo finché
#: qualcuno non decide che è sicuro.
TIPI_CON_TESTO = frozenset({
    "conferma", "promemoria", "compleanno", "messaggio_manuale", "risposta_chat",
    "avviso_nuova_prenotazione", "avviso_modifica", "avviso_annullamento",
})


@dataclass(frozen=True)
class _Contesto:
    tipo: str
    client_id: Optional[int] = None
    appointment_id: Optional[int] = None


_contesto: ContextVar[Optional[_Contesto]] = ContextVar("registro_contesto", default=None)


@contextmanager
def invio(
    tipo: str, *, client_id: Optional[int] = None, appointment_id: Optional[int] = None,
) -> Iterator[None]:
    """Dichiara cosa stanno per spedire le chiamate dentro il blocco."""
    if tipo not in TIPI:
        raise ValueError(f"tipo di messaggio sconosciuto: {tipo}")
    token = _contesto.set(_Contesto(tipo, client_id, appointment_id))
    try:
        yield
    finally:
        _contesto.reset(token)


# Una connessione propria, senza pool: il registro si scrive anche dai compiti
# Celery, che girano ognuno in un event loop nuovo, e un pool condiviso con
# connessioni nate in un altro loop si rompe («attached to a different loop»).
# E fuori dalla transazione di chi chiama: se la richiesta poi fallisce, il
# messaggio è partito lo stesso, e il registro deve dirlo.
_fabbrica: Optional[async_sessionmaker] = None


def _sessioni() -> async_sessionmaker:
    global _fabbrica
    if _fabbrica is None:
        motore = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        _fabbrica = async_sessionmaker(motore, class_=AsyncSession, expire_on_commit=False)
    return _fabbrica


def html_in_testo(corpo: str) -> str:
    """Il testo che la cliente legge, senza i tag dell'email."""
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h[1-6]|li)>", "\n", corpo)
    t = re.sub(r"(?s)<(style|script)[^>]*>.*?</\1>", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


async def registra(
    *,
    canale: str,
    destinatario: str,
    stato: str,
    testo: Optional[str] = None,
    oggetto: Optional[str] = None,
    formato: Optional[str] = None,
    errore: Optional[str] = None,
    id_fornitore: Optional[str] = None,
) -> None:
    """Scrive una riga. Non solleva mai: un registro che si rompe non deve
    impedire a un promemoria di partire, né far credere che non sia partito."""
    ctx = _contesto.get() or _Contesto("altro")
    try:
        async with _sessioni()() as s:
            s.add(RegistroMessaggio(
                canale=canale,
                tipo=ctx.tipo,
                destinatario=(destinatario or "")[:255],
                client_id=ctx.client_id,
                appointment_id=ctx.appointment_id,
                oggetto=oggetto[:300] if oggetto else None,
                testo=(testo[:10000] if testo else None) if ctx.tipo in TIPI_CON_TESTO else None,
                formato=formato,
                stato=stato,
                errore=errore[:1000] if errore else None,
                id_fornitore=id_fornitore,
            ))
            await s.commit()
    except Exception:
        log.exception("registro messaggi non scritto", extra={"canale": canale, "tipo": ctx.tipo})


# ── Stato di consegna (WhatsApp, dal callback di Twilio) ───────────────

# Twilio manda gli stati in ordine sparso: «read» può arrivare prima di
# «delivered». Si va solo avanti, mai indietro.
_DA_TWILIO = {
    "accepted": "inviato", "queued": "inviato", "sending": "inviato", "sent": "inviato",
    "delivered": "consegnato",
    "read": "letto",
    "undelivered": "non_consegnato", "failed": "non_consegnato",
}
_RANGO = {"inviato": 1, "consegnato": 2, "letto": 3, "non_consegnato": 4, "errore": 4}

#: I codici che si sono visti davvero su questo numero, in parole. Gli altri
#: restano col numero: la documentazione di Twilio li spiega uno per uno.
CODICI_TWILIO = {
    "63003": "Il numero non ha WhatsApp",
    "63016": "Fuori dalla finestra di 24 ore: serviva un template",
    "63024": "Destinatario non valido per WhatsApp",
    "63049": "Meta ha scelto di non consegnarlo",
    "63032": "La cliente ha bloccato i messaggi del salone",
}


async def aggiorna_stato(
    db: AsyncSession, id_fornitore: str, stato_twilio: str, codice_errore: Optional[str],
) -> bool:
    """Aggiorna la riga del messaggio. `False` se non è nel registro (un
    messaggio di prima del registro, o già cancellato dalla pulizia)."""
    nuovo = _DA_TWILIO.get((stato_twilio or "").lower())
    if not nuovo:
        return False
    riga = (await db.execute(
        select(RegistroMessaggio).where(RegistroMessaggio.id_fornitore == id_fornitore)
    )).scalar_one_or_none()
    if riga is None:
        return False
    if _RANGO.get(nuovo, 0) > _RANGO.get(riga.stato, 0):
        riga.stato = nuovo
        riga.stato_aggiornato_il = datetime.now(timezone.utc)
        if nuovo == "non_consegnato" and codice_errore:
            riga.errore = f"{codice_errore}: {CODICI_TWILIO.get(codice_errore, 'vedi codice Twilio')}"
    await db.flush()
    return True


async def pulisci(db: AsyncSession, adesso: Optional[datetime] = None) -> int:
    """Cancella le righe più vecchie di `CONSERVAZIONE_GIORNI`."""
    limite = (adesso or datetime.now(timezone.utc)) - timedelta(days=CONSERVAZIONE_GIORNI)
    risultato = await db.execute(
        delete(RegistroMessaggio).where(RegistroMessaggio.creato_il < limite)
    )
    await db.flush()
    return risultato.rowcount or 0
