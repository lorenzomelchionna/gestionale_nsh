import enum
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Enum, DateTime, Date, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class WaitlistStatus(str, enum.Enum):
    waiting = "waiting"        # In attesa di uno slot
    notified = "notified"      # Salone ha notificato il cliente
    fulfilled = "fulfilled"    # Cliente ha prenotato
    cancelled = "cancelled"    # Rimosso


class WaitlistEntry(Base):
    __tablename__ = "waitlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    collaborator_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("collaborators.id", ondelete="SET NULL"), nullable=True
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )

    preferred_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[WaitlistStatus] = mapped_column(
        Enum(WaitlistStatus), default=WaitlistStatus.waiting, nullable=False
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    client: Mapped["Client"] = relationship("Client", back_populates="waitlist_entries")
    collaborator: Mapped[Optional["Collaborator"]] = relationship("Collaborator", back_populates="waitlist_entries")
    service: Mapped["Service"] = relationship("Service", back_populates="waitlist_entries")
