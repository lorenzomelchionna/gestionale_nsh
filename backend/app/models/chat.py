import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MessageDirection(str, enum.Enum):
    inbound = "inbound"    # written by the client
    outbound = "outbound"  # written by the salon


class MessageStatus(str, enum.Enum):
    received = "received"
    queued = "queued"
    sent = "sent"
    failed = "failed"


class Conversation(Base):
    """
    One WhatsApp thread with a phone number.

    Keyed by phone rather than client: a message can arrive from a number that
    is not in the address book yet, and the conversation must still be readable.
    `client_id` is filled in when a matching client exists (or later, by hand).
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    # Display name for numbers with no client record (WhatsApp profile name).
    contact_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # Drives both the unread badge and the 24h reply window, so it is stored
    # rather than derived from the message list on every request.
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_inbound_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unread_count: Mapped[int] = mapped_column(default=0, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    client: Mapped[Optional["Client"]] = relationship("Client")
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    __table_args__ = (
        Index("ix_conversations_last_message_at", "last_message_at"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus), default=MessageStatus.received, nullable=False
    )

    # Twilio's message id, kept so a redelivered webhook can be recognised as a
    # duplicate instead of inserting the same message twice.
    provider_sid: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Which staff member sent an outbound message (null for inbound).
    sent_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )
    sent_by: Mapped[Optional["User"]] = relationship("User")
