"""Limiti di frequenza sugli endpoint che chiunque può chiamare.

Il gestionale espone quattro rotte senza autenticazione — registrazione,
login, verifica del codice, rinvio del codice — e finora nessuna aveva un
tetto. Chiamandole in ciclo si riempiva l'anagrafica di clienti falsi, si
bruciava la quota Brevo (300 email al giorno sul piano gratuito, e quando
finisce non partono più **neanche** le conferme delle prenotazioni vere) e si
provavano password a raffica.

È l'unica misura che *ferma* qualcuno invece di limitarsi a renderlo più
lento.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.config import settings


def client_ip(request: Request) -> str:
    """Chi sta chiamando, visto da dietro il proxy di Railway.

    Contare sull'IP della connessione qui sarebbe inutile: in produzione è
    sempre quello del proxy, quindi tutte le clienti finirebbero nello stesso
    secchio e la prima che sfora bloccherebbe le altre.

    Di `X-Forwarded-For` si prende l'**ultima** voce, non la prima. La catena
    si legge da sinistra (client) a destra (proxy più vicino), e ogni proxy
    accoda: chi manda un `X-Forwarded-For` inventato lo vede quindi apparire
    *prima* di quello vero che aggiunge Railway. La prima voce è scrivibile da
    chi chiama — cioè aggirabile cambiandola a ogni richiesta — l'ultima no.
    """
    inoltrato = request.headers.get("x-forwarded-for")
    if inoltrato:
        catena = [pezzo.strip() for pezzo in inoltrato.split(",") if pezzo.strip()]
        if catena:
            return catena[-1]
    return request.client.host if request.client else "sconosciuto"


limiter = Limiter(
    key_func=client_ip,
    # Redis c'è già per Celery. Serve perché i contatori sopravvivano ai
    # riavvii: tenerli in memoria vorrebbe dire che un `docker restart` — o un
    # redeploy — azzera il budget di chi stava insistendo.
    storage_uri=settings.RATE_LIMIT_STORAGE_URI or settings.REDIS_URL,
    enabled=settings.RATE_LIMIT_ENABLED,
    # Nessun limite globale: le rotte non elencate restano libere. Un tetto su
    # tutto colpirebbe l'agenda, che dal salone viene interrogata di continuo.
    default_limits=[],
    # Se Redis non risponde si continua a contare in memoria invece di
    # rifiutare la richiesta. Provato: senza questo, con Redis spento ogni
    # login rispondeva 500 — cioè il salone chiuso fuori dal proprio
    # gestionale perché è caduta una cache. Fino a ieri Redis giù voleva dire
    # soltanto notifiche non spedite, e non deve diventare qualcosa di
    # peggio.
    in_memory_fallback_enabled=True,
    # Rete dell'ultima parola: qualunque altro errore del limitatore lascia
    # passare la richiesta. Un tetto di frequenza è una protezione, non una
    # dipendenza da cui far dipendere l'accesso.
    swallow_errors=True,
)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """La risposta a chi ha superato il limite.

    Il messaggio non dice quale limite né quanto manca: a chi sta lavorando
    non serve, e a chi sta provando password servirebbe per tarare i tempi.
    `Retry-After` invece c'è, perché è lo standard e i client seri lo leggono.
    """
    return JSONResponse(
        status_code=429,
        content={"detail": "Troppi tentativi. Riprova fra qualche minuto."},
        headers={"Retry-After": "60"},
    )
