"""
WhatsApp inbox for the salon.

Guarded with `get_current_user`, not `require_admin`: answering clients is
day-to-day work that collaborators do too, and it exposes no financial data.
"""
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.chat import Conversation, MessageDirection
from app.models.user import User
from app.schemas.chat import (
    ChatMessageOut, ConversationDetail, ConversationOut, ReplyRequest,
)
from app.config import settings
from app.services.chat import (
    REPLY_WINDOW_HOURS, can_reply_freely, mark_read, send_reply,
    whatsapp_mode, window_expires_at,
)

router = APIRouter(prefix="/chat", tags=["Chat"])


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
        out.last_message_preview = f"{prefix}{last.body[:80]}"

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
