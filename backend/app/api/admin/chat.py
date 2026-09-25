"""
WhatsApp inbox for the salon.

Guarded with `get_current_user`, not `require_admin`: answering clients is
day-to-day work that collaborators do too, and it exposes no financial data.
"""
from typing import Annotated, List, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.chat import ChatMessage, Conversation, MessageDirection
from app.models.user import User
from app.schemas.chat import (
    ChatMessageOut, ConversationDetail, ConversationOut, ReplyRequest,
)
from app.config import settings
from app.services.chat import (
    REPLY_WINDOW_HOURS, AllegatoNonDisponibile, can_reply_freely,
    etichetta_allegato, mark_read, scarica_allegato, send_reply,
    whatsapp_mode, window_expires_at,
)

router = APIRouter(prefix="/chat", tags=["Chat"])

log = logging.getLogger("nsh.whatsapp")

# Tipi che il browser mostra senza eseguire niente. Tutto il resto — un .html,
# un .svg, un file con un tipo inventato — si scarica e basta: servito «inline»
# dal dominio dell'API, un file mandato da chiunque su WhatsApp diventerebbe
# una pagina di quel dominio.
TIPI_DA_MOSTRARE = ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf")
FAMIGLIE_DA_MOSTRARE = ("audio/", "video/")


def _decorate(conv: Conversation, include_messages: bool = False) -> ConversationOut:
    """Fill the display-only fields the UI needs but the table does not store."""
    schema = ConversationDetail if include_messages else ConversationOut
    out = schema.model_validate(conv)

    if conv.client:
        out.display_name = f"{conv.client.first_name} {conv.client.last_name}".strip()
    else:
        out.display_name = conv.contact_name or conv.phone

    out.can_reply_freely = can_reply_freely(conv)
    out.window_expires_at = window_expires_at(conv)

    if include_messages:
        out.messages = [ChatMessageOut.model_validate(m) for m in conv.messages]
    elif conv.messages:
        last = conv.messages[-1]
        prefix = "" if last.direction == MessageDirection.inbound else "Tu: "
        testo = last.body or (etichetta_allegato(last.media[0]["content_type"]) if last.media else "")
        out.last_message_preview = f"{prefix}{testo[:80]}"

    return out


async def _load(db: AsyncSession, conversation_id: int) -> Conversation:
    conv = (await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.client), selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversazione non trovata")
    return conv


@router.get("/conversations", response_model=List[ConversationOut])
async def list_conversations(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    archived: bool = Query(False),
):
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.client), selectinload(Conversation.messages))
        .where(Conversation.is_archived == archived)
        .order_by(Conversation.last_message_at.desc().nullslast())
    )
    return [_decorate(c) for c in result.scalars().all()]


@router.get("/unread-count")
async def unread_count(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Drives the nav badge, so it stays a single cheap query."""
    total = (await db.execute(
        select(Conversation.unread_count).where(Conversation.is_archived == False)  # noqa: E712
    )).scalars().all()
    return {"unread": sum(total)}


@router.get("/status")
async def channel_status(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Whether the WhatsApp channel is live.

    Until the salon's number is migrated the deployment runs on Twilio's shared
    sandbox, which only reaches people who sent the join code. The UI surfaces
    this so nobody assumes a reply reached a client when it did not.
    """
    mode = whatsapp_mode()
    return {
        "mode": mode,
        "is_live": mode == "production",
        "from_number": settings.TWILIO_WHATSAPP_FROM or None,
        "reply_window_hours": REPLY_WINDOW_HOURS,
    }


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    conv = await _load(db, conversation_id)
    # Opening the thread is what marks it read.
    await mark_read(db, conv)
    return _decorate(conv, include_messages=True)


@router.post("/conversations/{conversation_id}/reply", response_model=ChatMessageOut)
async def reply(
    conversation_id: int,
    payload: ReplyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    conv = await _load(db, conversation_id)

    if not can_reply_freely(conv):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Finestra di risposta scaduta: WhatsApp consente messaggi liberi "
                "solo entro 24 ore dall'ultimo messaggio del cliente. Oltre, "
                "servono i template approvati."
            ),
        )

    message = await send_reply(db, conv, payload.body, sent_by_user_id=current_user.id)
    return ChatMessageOut.model_validate(message)


@router.patch("/conversations/{conversation_id}/archive", response_model=ConversationOut)
async def set_archived(
    conversation_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    archived: bool = Query(True),
):
    conv = await _load(db, conversation_id)
    conv.is_archived = archived
    await db.flush()
    return _decorate(conv)


@router.get("/messages/{message_id}/media/{index}")
async def message_media(
    message_id: int,
    index: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Un allegato di un messaggio, preso da Twilio con le credenziali del salone.

    Passa da qui perché l'URL di Twilio senza credenziali risponde 401: la
    pagina non potrebbe mostrarlo, e dargli le credenziali vorrebbe dire
    consegnare l'account Twilio a ogni browser dello staff.
    """
    msg = await db.get(ChatMessage, message_id)
    allegati = (msg.media or []) if msg else []
    if not 0 <= index < len(allegati):
        raise HTTPException(status_code=404, detail="Allegato non trovato")

    try:
        contenuto, tipo = await scarica_allegato(allegati[index]["url"])
    except AllegatoNonDisponibile:
        log.exception("allegato WhatsApp non scaricato", extra={"id_messaggio": message_id})
        raise HTTPException(status_code=502, detail="Allegato non disponibile al momento")

    tipo = (tipo or allegati[index].get("content_type") or "").split(";")[0].strip().lower()
    da_mostrare = tipo in TIPI_DA_MOSTRARE or tipo.startswith(FAMIGLIE_DA_MOSTRARE)
    return Response(
        content=contenuto,
        media_type=tipo if da_mostrare else "application/octet-stream",
        headers={
            "Content-Disposition": "inline" if da_mostrare else "attachment",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            # Privata: è la foto di una cliente, nessuna cache condivisa deve tenerla.
            "Cache-Control": "private, max-age=86400",
        },
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Cancella una conversazione e tutti i suoi messaggi, per sempre.

    Solo admin, a differenza del resto della chat: archiviare si annulla,
    questo no. Cancella la copia del gestionale e basta — Twilio tiene il suo
    registro, e se la persona riscrive nasce una conversazione nuova.
    """
    conv = await _load(db, conversation_id)
    await db.delete(conv)
    await db.flush()
    log.info(
        "conversazione WhatsApp cancellata",
        extra={"id_conversazione": conversation_id, "messaggi": len(conv.messages)},
    )
