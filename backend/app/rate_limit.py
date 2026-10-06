"""Limiti di frequenza sugli endpoint che chiunque può chiamare.

Il gestionale espone quattro rotte senza autenticazione — registrazione,
login, verifica del codice, rinvio del codice — e finora nessuna aveva un
tetto. Chiamandole in ciclo si riempiva l'anagrafica di clienti falsi, si
bruciava la quota Brevo (300 email al giorno sul piano gratuito, e quando
finisce non partono più **neanche** le conferme delle prenotazioni vere) e si
provavano password a raffica.

È l'unica misura che *ferma* qualcuno invece di limitarsi a renderlo più
lento.

**Per persona, non solo per IP.** Le rotte della registrazione contano due
volte: per indirizzo email (`per_email`, il tetto stretto) e per IP (un
tetto largo, contro chi prova in ciclo). Contavano solo per IP, e il salone
ha **un** IP per tutto il Wi-Fi: il 3 ottobre una cliente che non riusciva a
confermare l'email ha consumato il budget di tutte, e un'altra, sullo stesso
Wi-Fi, è stata respinta alla registrazione con «Troppi tentativi».
"""
import hashlib
import hmac
import json
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.config import settings


def client_ip(request: Request) -> str:
    """Chi sta chiamando, visto da dietro il proxy di Railway.

    L'IP della connessione non serve: è sempre quello del proxy, quindi tutte
    le clienti finirebbero nello stesso secchio e la prima che sfora
    bloccherebbe le altre.

    L'ordine di preferenza sotto non è teorico, è quello che ha funzionato
    quando è stato provato in produzione.

    **Prima versione, sbagliata**: prendeva l'ultima voce di
    `X-Forwarded-For`, ragionando che la catena si legge client → proxy e che
    quindi l'ultima è l'unica non scrivibile da chi chiama. Il ragionamento è
    giusto in generale e falso qui: Railway accoda l'IP di un suo nodo
    interno, e quel nodo **cambia a ogni richiesta** (nei log si vedono
    `100.64.0.2`, `.3`, `.4` alternarsi). Ogni richiesta prendeva quindi una
    chiave diversa, cioè un secchio nuovo, cioè nessun limite: dodici login
    sbagliati di fila in produzione passavano tutti.

    `X-Envoy-External-Address` è la risposta giusta dove c'è: Railway sta
    dietro Envoy, e quel campo lo scrive il suo bordo con l'indirizzo esterno
    reale — non è un valore che il chiamante può imporre.

    La prima voce di `X-Forwarded-For` è il ripiego. È falsificabile, e va
    detto: chi la cambia a ogni richiesta si compra un secchio nuovo ogni
    volta. Resta comunque meglio dell'alternativa vera, che non è «un limite
    inviolabile» ma «nessun limite affatto» — che è esattamente quello che
    c'era prima di questa correzione.
    """
    esterno = request.headers.get("x-envoy-external-address")
    if esterno and esterno.strip():
        return esterno.strip()

    inoltrato = request.headers.get("x-forwarded-for")
    if inoltrato:
        catena = [pezzo.strip() for pezzo in inoltrato.split(",") if pezzo.strip()]
        if catena:
            return catena[0]

    return request.client.host if request.client else "sconosciuto"


def email_della_richiesta(request: Request) -> str:
    """L'indirizzo scritto nel corpo JSON, minuscolo e senza spazi; vuoto se manca.

    Si legge quello che FastAPI ha già letto: il limitatore controlla dentro
    l'endpoint, cioè dopo che il corpo è stato validato contro lo schema, e
    Starlette tiene il risultato in `_json`. Minuscolo perché le caselle di
    posta non distinguono: `Mario@…` e `mario@…` sono la stessa persona, e
    contarle a parte raddoppierebbe il budget di chi scrive alla stessa
    casella.
    """
    corpo = getattr(request, "_json", None)
    if corpo is None:
        grezzo = getattr(request, "_body", None)
        if grezzo:
            try:
                corpo = json.loads(grezzo)
            except ValueError:
                corpo = None
    if not isinstance(corpo, dict):
        return ""
    email = corpo.get("email")
    return email.strip().lower() if isinstance(email, str) else ""


def per_email(request: Request) -> str:
    """Chiave dei limiti per persona: l'indirizzo della richiesta, non l'IP.

    Nella chiave finisce un'impronta (HMAC con `SECRET_KEY`), non l'indirizzo:
    slowapi scrive la chiave in chiaro nel log quando un limite scatta, e lo
    storage è Redis. Con l'indirizzo dentro, entrambi diventerebbero un
    elenco di email non mascherate — esattamente quello che `maschera_email`
    esiste per evitare.

    Vuota se il corpo non ha un indirizzo: slowapi allora salta questo limite
    e resta quello per IP. Sulle rotte che lo usano non succede, perché lo
    schema rende l'indirizzo obbligatorio e una richiesta senza viene
    respinta con 422 prima di arrivare qui.
    """
    email = email_della_richiesta(request)
    if not email:
        return ""
    impronta = hmac.new(
        settings.SECRET_KEY.encode(), email.encode(), hashlib.sha256
    ).hexdigest()[:24]
    return f"email:{impronta}"


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

    Il 429 finisce anche nei log, a `WARNING`. È il momento in cui il tetto ha
    davvero fermato qualcuno: se non lo si scrive, l'unico modo di sapere che
    è successo è che se ne lamenti qualcuno — e chi si lamenta è la cliente
    bloccata per sbaglio, non chi stava provando le password.
    """
    # Import qui e non in cima: `audit` importa questo modulo per leggere l'IP
    # con la stessa logica, e in cima sarebbe un ciclo.
    from app.audit import LIMITE_SUPERATO, evento
    from app.logging_config import maschera_email

    # Quale dei due tetti ha fermato la richiesta: «una persona che insiste»
    # e «un IP che prova in ciclo» sono fatti diversi, e senza questo campo
    # nel log sarebbero indistinguibili quando hanno lo stesso valore.
    per_persona = getattr(getattr(exc, "limit", None), "key_func", None) is per_email
    campi = {"chiave": "email", "email": maschera_email(email_della_richiesta(request))} \
        if per_persona else {"chiave": "ip"}
    evento(
        LIMITE_SUPERATO,
        logging.WARNING,
        percorso=request.url.path,
        ip=client_ip(request),
        limite=str(getattr(exc, "detail", "")),
        **campi,
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Troppi tentativi. Riprova fra qualche minuto."},
        headers={"Retry-After": "60"},
    )
