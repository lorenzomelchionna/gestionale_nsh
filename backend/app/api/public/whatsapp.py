"""
Inbound WhatsApp webhook.

Twilio POSTs here whenever a client writes to the salon's number. The endpoint
is unauthenticated by necessity — Twilio cannot hold our credentials — so every
request is checked against the Twilio signature before anything is stored.

Ma la firma si calcola **sui parametri**, quindi per verificarla bisogna prima
averli letti: c'è per forza un pezzo di lavoro che questo endpoint fa per
chiunque bussi, prima di poter decidere se buttare la richiesta. È una
proprietà del protocollo, non una svista, ed è il motivo per cui questo file
è il posto più esposto del gestionale.

Da lì sono già passati due problemi della stessa famiglia: il DoS quadratico
di `python-multipart` (GHSA-5rvq-cxj2-64vf, vedi `requirements.txt`) e
PYSEC-2026-249, in cui `request.form()` accetta `max_fields` e `max_part_size`
ma **li ignora in silenzio** sui corpi `application/x-www-form-urlencoded`.
Misurato prima della correzione: 200.000 campi, 1,8 MB, parsati per intero in
0,42 s prima del 403 — senza credenziali e senza limite di tentativi, perché
qui non c'è nemmeno un `@limiter.limit`.

La risposta è smettere di leggere a un tetto, invece di sperare che la
libreria di turno rispetti il suo.
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import evento
from app.database import get_db
from app.services.chat import record_inbound
from app.utils.twilio_webhook import is_valid_twilio_request

import logging

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

log = logging.getLogger("nsh.whatsapp")

# Twilio treats any 2xx as delivered and stops retrying. An empty TwiML document
# is the documented way to say "received, nothing to send back".
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

# Quanto siamo disposti a leggere prima di sapere chi sta chiamando.
#
# Un messaggio WhatsApp vero sta in pochi kB: una ventina di parametri, il
# testo (che WhatsApp limita a 4096 caratteri) e al più una decina di URL di
# media. 64 kB sono quindici volte il caso più grosso plausibile, e trenta
# volte meno di quello che passava prima. Il margine sta da questa parte di
# proposito: il costo di essere troppo stretti è un messaggio di una cliente
# che si perde, quello di essere troppo larghi è qualche kB di CPU.
MAX_WEBHOOK_BYTES = 64 * 1024


async def _corpo_limitato(request: Request) -> Optional[bytes]:
    """Il corpo della richiesta, oppure `None` se sfora il tetto.

    Si ferma **mentre** legge, non dopo: `await request.body()` avrebbe già
    portato tutto in memoria prima di poterlo misurare, che è esattamente il
    costo da evitare. Uscire dal ciclo lascia il resto del corpo non letto, ed
    è voluto — chi sta mandando dieci megabyte non deve vederli accettati.
    """
    pezzi: list[bytes] = []
    totale = 0
    async for pezzo in request.stream():
        totale += len(pezzo)
        if totale > MAX_WEBHOOK_BYTES:
            return None
        pezzi.append(pezzo)
    return b"".join(pezzi)


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    corpo = await _corpo_limitato(request)
    if corpo is None:
        # 413 e non 403, benché il 403 dica meno a chi sonda: se un domani un
        # messaggio legittimo sforasse, un 403 manderebbe a cercare un problema
        # di firma per ore. Qui il codice dice cosa è successo davvero, e non
        # rivela niente che chi ha appena spedito il corpo non sappia già.
        evento(
            "webhook_corpo_troppo_grande",
            logging.WARNING,
            percorso=request.url.path,
            limite_byte=MAX_WEBHOOK_BYTES,
        )
        # `CONTENT_TOO_LARGE` e non `REQUEST_ENTITY_TOO_LARGE`: stesso 413, ma
        # il secondo nome è deprecato da starlette 1.x. Il valore è identico,
        # quindi per chi chiama non cambia niente.
        return Response(status_code=status.HTTP_413_CONTENT_TOO_LARGE)

    # I byte già limitati tornano al parser di starlette invece di essere
    # interpretati a mano. Riscrivere il parsing con `parse_qsl` avrebbe
    # funzionato — provato, stesso risultato su accenti, emoji, `+` e `&` —
    # ma la firma si calcola su questi valori: qualunque differenza di
    # decodifica, anche in un caso limite non provato, si manifesterebbe come
    # messaggi veri rifiutati. Così l'unica cosa che cambia è quanto si legge.
    async def _rigioca():
        return {"type": "http.request", "body": corpo, "more_body": False}

    form = await Request(request.scope, _rigioca).form()
    params = {k: str(v) for k, v in form.items()}

    if not is_valid_twilio_request(request, params):
        # 403 without detail: an attacker probing the endpoint learns nothing.
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    from_phone = params.get("From", "")
    body = params.get("Body", "")
    sid = params.get("MessageSid") or params.get("SmsMessageSid")
    profile_name = params.get("ProfileName")

    if from_phone and body:
        await record_inbound(
            db,
            from_phone=from_phone,
            body=body,
            provider_sid=sid,
            contact_name=profile_name,
        )

    return Response(content=EMPTY_TWIML, media_type="application/xml")
