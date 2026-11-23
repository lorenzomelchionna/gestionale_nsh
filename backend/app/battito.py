"""Il battito del worker: «sono vivo» a un servizio esterno, ogni 15 minuti.

Sentry dice quando qualcosa si rompe. Non può dire quando qualcosa smette di
succedere: se Celery beat si ferma, o il worker resta appeso, i promemoria
non partono e nessun errore viene mai sollevato. Il silenzio è il guasto.

Per questo, alla fine di ogni giro dei promemoria, il worker chiama
`HEARTBEAT_URL` (un heartbeat di Better Stack; Healthchecks.io accetta lo
stesso formato). Se il servizio non sente niente per un periodo + tolleranza,
apre un incidente e manda una mail. Un giro che fallisce chiama `…/fail` e
l'incidente si apre subito, senza aspettare.

Un battito che non parte non deve mai far fallire i promemoria: al massimo
arriva un allarme in più. L'URL non finisce nei log: chi lo conosce può
battere al posto del worker e nascondere un guasto.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

log = logging.getLogger("nsh.attivita")

TIMEOUT_SECONDI = 5


def batti(riuscito: bool = True) -> None:
    url = settings.HEARTBEAT_URL
    if not url:
        return
    if not riuscito:
        url = url.rstrip("/") + "/fail"
    try:
        httpx.get(url, timeout=TIMEOUT_SECONDI).raise_for_status()
    except httpx.HTTPError as e:
        log.warning("battito non inviato", extra={"errore": type(e).__name__})
