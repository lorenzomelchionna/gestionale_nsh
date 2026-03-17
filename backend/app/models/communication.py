import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Enum, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CommunicationType(str, enum.Enum):
    email = "email"
    sms = "sms"
    whatsapp = "whatsapp"


class CommunicationStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"
    pending = "pending"


class Communication(Base):
    __tablename__ = "communications"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[CommunicationType] = mapped_column(Enum(CommunicationType), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CommunicationStatus] = mapped_column(
        Enum(CommunicationStatus), default=CommunicationStatus.pending
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="communications")
