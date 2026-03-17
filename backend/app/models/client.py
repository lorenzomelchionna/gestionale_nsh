from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Date, Text, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ClientAccount(Base):
    """Login credentials for the online booking portal."""
    __tablename__ = "client_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_token_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # One ClientAccount -> one Client
    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="account", uselist=False)


class Client(Base):
    """Salon client master record (used for both walk-in and online clients)."""
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Link to online account (optional – walk-in clients won't have one)
    account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("client_accounts.id", ondelete="SET NULL"), nullable=True
    )
    account: Mapped[Optional["ClientAccount"]] = relationship(
        "ClientAccount", back_populates="client"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="client")
    communications: Mapped[List["Communication"]] = relationship("Communication", back_populates="client")
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="client")
