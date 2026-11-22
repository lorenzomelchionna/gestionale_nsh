"""Sentry: gli errori di produzione arrivano per email, con lo stack, invece di
restare nei log finché qualcuno non li va a cercare.

Si accende solo con `SENTRY_DSN` impostato. Lo chiamano sia l'API
(`app/main.py`) sia il worker (`app/tasks/celery_app.py`): il worker è un
processo a parte, e senza la sua chiamata promemoria, auguri e notifiche
fallirebbero di nuovo in silenzio.

**Cosa non parte mai verso Sentry**, che è un servizio esterno. Le stesse
regole dei log (`app/logging_config.py`), più quelle che i log non avevano
bisogno di avere:

- il corpo delle richieste (`max_request_body_size="never"`): lì dentro ci
  sono nomi, telefoni, note sulle clienti e le password dei login;
- le variabili locali degli stack (`include_local_variables=False`): l'SDK le
  allega a ogni riga dello stack per default, e una funzione di login ha la
  password in chiaro in una variabile;
- IP, cookie e utente (il default dell'SDK, che qui non si tocca), e le query string, dove
  finiscono le ricerche per nome;
- dentro i testi che restano (messaggi d'errore, breadcrumb dei log): email e
  telefoni mascherati come nei log, JWT e `Bearer` tolti, e i campi che
  sanno di segreto sostituiti. Un `IntegrityError` di Postgres riporta il
  valore duplicato per intero: «Key (email)=(…)».

Al loro posto, per ritrovare l'errore nei log di Railway: `richiesta` (lo
stesso id dell'header `X-Request-ID`), `attore` (`client:41`, non un nome) e
il servizio.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from app.config import settings
from app.logging_config import (
    CAMPI_SEGRETI, SOSTITUTO, _ripulisci, attore, id_richiesta,
    maschera_email, maschera_telefono,
)
from app.version import __version__

log = logging.getLogger("nsh")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Nove cifre o più, con spazi o trattini in mezzo: un numero di telefono.
# Gli id degli oggetti (fino a qualche migliaio) e gli anni restano.
_TELEFONO = re.compile(r"\+?\d(?:[\s-]?\d){8,}")

# Le intestazioni che servono a capire un errore. Le altre non partono.
# `password=…`, `token: …` dentro un testo libero (un messaggio d'errore,
# una riga di log scritta in fretta).
_COPPIA_SEGRETA = re.compile(r"(?i)\b(password|token|secret|codice|code|otp)(\s*[=:]\s*)[^\s&,;]+")

_INTESTAZIONI_UTILI = frozenset({"user-agent", "content-type", "accept", "host", "x-request-id"})

#: Quante volte lo stesso errore può partire verso Sentry in `FINESTRA_SECONDI`,
#: per processo. Il piano gratuito ha 5.000 eventi al mese: un errore che si
#: ripete a ogni promemoria (ogni 15 minuti) o a ogni richiesta li
#: consumerebbe in un giorno, e da lì in poi gli errori nuovi non arrivano.
#: Il primo basta a sapere che c'è; il conteggio esatto sta nei log.
MAX_PER_ERRORE = 5
FINESTRA_SECONDI = 600
_visti: dict[str, list[float]] = {}


def _testo(s: str) -> str:
    s = _ripulisci(s)
    s = _COPPIA_SEGRETA.sub(lambda m: f"{m.group(1)}{m.group(2)}{SOSTITUTO}", s)
    s = _EMAIL.sub(lambda m: maschera_email(m.group(0)), s)
    return _TELEFONO.sub(lambda m: maschera_telefono(m.group(0)), s)


def ripulisci(valore: Any, chiave: str = "") -> Any:
    """Toglie i dati personali da un evento o da un suo pezzo, ricorsivamente."""
    if chiave and any(s in chiave.lower() for s in CAMPI_SEGRETI):
        return SOSTITUTO
    if isinstance(valore, str):
        return _testo(valore)
    if isinstance(valore, dict):
        return {k: ripulisci(v, str(k)) for k, v in valore.items()}
    if isinstance(valore, (list, tuple)):
        return [ripulisci(v) for v in valore]
    return valore


def _chiave(evento: dict) -> str:
    """Lo stesso errore: stesso tipo di eccezione nello stesso punto del codice,
    o lo stesso messaggio di log."""
    for ecc in (evento.get("exception") or {}).get("values") or []:
        frames = (ecc.get("stacktrace") or {}).get("frames") or []
        dove = f"{frames[-1].get('module')}:{frames[-1].get('lineno')}" if frames else ""
        return f"{ecc.get('type')}@{dove}"
    msg = evento.get("logentry") or {}
    return str(msg.get("message") or evento.get("message") or "")


def _troppi(chiave: str, adesso: Optional[float] = None) -> bool:
    adesso = time.monotonic() if adesso is None else adesso
    recenti = [t for t in _visti.get(chiave, []) if adesso - t < FINESTRA_SECONDI]
    if len(recenti) >= MAX_PER_ERRORE:
        _visti[chiave] = recenti
        return True
    recenti.append(adesso)
    _visti[chiave] = recenti
    return False


def prepara_evento(evento: dict, _hint: Optional[dict] = None) -> Optional[dict]:
    """`before_send`: l'ultimo passaggio prima che l'evento esca dal server."""
    if _troppi(_chiave(evento)):
        return None

    richiesta = evento.get("request")
    if isinstance(richiesta, dict):
        richiesta.pop("data", None)
        richiesta.pop("cookies", None)
        richiesta.pop("query_string", None)
        richiesta.pop("env", None)
        if isinstance(richiesta.get("url"), str):
            richiesta["url"] = richiesta["url"].split("?", 1)[0].split("#", 1)[0]
        intestazioni = richiesta.get("headers")
        if isinstance(intestazioni, dict):
            richiesta["headers"] = {
                k: v for k, v in intestazioni.items() if k.lower() in _INTESTAZIONI_UTILI
            }
    evento.pop("user", None)

    tag = evento.setdefault("tags", {})
    if id_richiesta.get() != "-":
        tag.setdefault("richiesta", id_richiesta.get())
    tag.setdefault("attore", attore.get())

    return ripulisci(evento)


def prepara_breadcrumb(crumb: dict, _hint: Optional[dict] = None) -> Optional[dict]:
    """`before_breadcrumb`: le righe di log e le chiamate HTTP che precedono
    l'errore. Utili, ma sono testo libero: stesso filtro."""
    dati = crumb.get("data")
    if isinstance(dati, dict) and isinstance(dati.get("url"), str):
        dati["url"] = dati["url"].split("?", 1)[0]
    dati_http = crumb.get("data") or {}
    if isinstance(dati_http, dict):
        dati_http.pop("http.query", None)
        dati_http.pop("http.fragment", None)
    return ripulisci(crumb)


def avvia_sentry(servizio: str) -> bool:
    """Accende Sentry per questo processo. `False` se non è configurato."""
    if not settings.SENTRY_DSN:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        release=f"gestionale-nsh@{__version__}",
        server_name=servizio,
        # Né `send_default_pii` né `data_collection`: l'SDK allora non raccoglie
        # IP, cookie e utente e tiene il suo filtro dei campi sensibili.
        # `send_default_pii=False` scritto esplicitamente è deprecato dalla 2.7x.
        include_local_variables=False,
        max_request_body_size="never",
        # Solo errori. Il tracciamento delle prestazioni consuma un'altra
        # quota e manda gli URL di ogni richiesta: per ora non serve.
        traces_sample_rate=0,
        before_send=prepara_evento,
        before_breadcrumb=prepara_breadcrumb,
    )
    sentry_sdk.set_tag("servizio", servizio)
    log.info("Sentry attivo", extra={"servizio": servizio})
    return True
