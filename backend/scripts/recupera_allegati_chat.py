"""
Recupera da Twilio i messaggi WhatsApp con allegati che il webhook ha scartato.

Fino al 2026-09-25 il webhook salvava un messaggio solo se aveva del testo:
una foto o un vocale senza didascalia non lasciavano traccia nel gestionale.
Su Twilio però ci sono ancora — il registro dei messaggi e i file — quindi si
possono rimettere al loro posto.

Entrano con la loro data, non con quella di oggi. Non è un dettaglio: la
finestra delle 24 ore in cui si può rispondere liberamente si calcola
dall'ultimo messaggio ricevuto, e un vocale di tre giorni fa registrato come
«adesso» la riaprirebbe per finta — la risposta verrebbe poi rifiutata da Meta.

Salta i messaggi già presenti (stesso SID), quindi rilanciarlo non duplica.
Senza --apply mostra cosa farebbe e non scrive.

Uso (DATABASE_URL verso il database di produzione, p.es. dal tunnel Railway):
    DATABASE_URL=postgresql+asyncpg://... TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... \\
    TWILIO_WHATSAPP_FROM=whatsapp:+39... python scripts/recupera_allegati_chat.py [--apply]
"""
import asyncio
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.logging_config import maschera_telefono  # noqa: E402
from app.models.chat import ChatMessage, MessageDirection, MessageStatus  # noqa: E402
from app.services.chat import etichetta_allegato, get_or_create_conversation  # noqa: E402

API = "https://api.twilio.com"


async def _messaggi_con_allegati(http: httpx.AsyncClient) -> list[dict]:
    """Tutti i messaggi arrivati al numero del salone che portano allegati."""
    trovati = []
    percorso = f"/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    params = {"To": settings.TWILIO_WHATSAPP_FROM, "PageSize": 1000}
    while percorso:
        r = await http.get(API + percorso, params=params)
        r.raise_for_status()
        pagina = r.json()
        trovati += [m for m in pagina["messages"] if int(m.get("num_media") or 0) > 0]
        percorso, params = pagina.get("next_page_uri"), None
    return trovati


async def _allegati(http: httpx.AsyncClient, sid: str) -> list[dict[str, str]]:
    r = await http.get(
        f"{API}/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages/{sid}/Media.json"
    )
    r.raise_for_status()
    # L'URI della risorsa senza `.json` è il file stesso: è la forma che il
    # webhook manda in `MediaUrl0`, e quella che il backend sa scaricare.
    return [
        {"url": API + m["uri"].removesuffix(".json"), "content_type": m["content_type"]}
        for m in r.json()["media_list"]
    ]


async def main() -> int:
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM):
        print("Servono TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN e TWILIO_WHATSAPP_FROM", file=sys.stderr)
        return 1
    applica = "--apply" in sys.argv

    async with httpx.AsyncClient(
        auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN), timeout=30.0
    ) as http, AsyncSessionLocal() as db:
        candidati = await _messaggi_con_allegati(http)
        gia = set((await db.execute(
            select(ChatMessage.provider_sid).where(
                ChatMessage.provider_sid.in_([m["sid"] for m in candidati])
            )
        )).scalars().all())
        mancanti = sorted(
            (m for m in candidati if m["sid"] not in gia),
            key=lambda m: parsedate_to_datetime(m["date_created"]),
        )

        print(f"Messaggi con allegati su Twilio: {len(candidati)}")
        print(f"Già nel gestionale:              {len(gia)}")
        print(f"Da recuperare:                   {len(mancanti)}")

        for m in mancanti:
            quando = parsedate_to_datetime(m["date_created"])
            allegati = await _allegati(http, m["sid"])
            numero = m["from"].removeprefix("whatsapp:")
            tipi = ", ".join(etichetta_allegato(a["content_type"]) for a in allegati)
            print(f"  {quando:%d/%m %H:%M} UTC  {maschera_telefono(numero)}  {tipi}"
                  + (f"  «{m['body'][:40]}»" if m["body"] else ""))
            if not applica:
                continue

            conv = await get_or_create_conversation(db, numero)
            db.add(ChatMessage(
                conversation_id=conv.id,
                direction=MessageDirection.inbound,
                body=m["body"] or "",
                status=MessageStatus.received,
                provider_sid=m["sid"],
                media=allegati,
                created_at=quando,
            ))
            # Le date della conversazione avanzano solo se questo messaggio è
            # davvero il più recente: mai spostate a «adesso».
            if conv.last_message_at is None or quando > conv.last_message_at:
                conv.last_message_at = quando
            if conv.last_inbound_at is None or quando > conv.last_inbound_at:
                conv.last_inbound_at = quando
            conv.unread_count += 1
            conv.is_archived = False
            await db.flush()

        if not mancanti:
            print("\nNiente da fare.")
        elif applica:
            await db.commit()
            print(f"\nRecuperati {len(mancanti)} messaggi.")
        else:
            print("\nDry run. Rilancia con --apply per scrivere.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
