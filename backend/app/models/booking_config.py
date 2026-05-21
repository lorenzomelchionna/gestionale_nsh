from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, Integer, DateTime, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

_DEFAULT_BOOKING_MSG = (
    "Ciao {nome}! La tua prenotazione da New Style Hair è confermata "
    "per il {data} alle {ora} con {collaboratore}. A presto! 💇"
)
_DEFAULT_REMINDER_MSG = (
    "Ciao {nome}! Ti ricordiamo il tuo appuntamento da New Style Hair "
    "il {data} alle {ora} con {collaboratore}. A presto! 💇"
)


class BookingConfig(Base):
    __tablename__ = "booking_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_advance_hours: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    max_advance_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    min_cancel_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    # Salon closed weekdays: list of JS-convention day numbers (0=Sun, 1=Mon … 6=Sat)
    closed_weekdays: Mapped[list] = mapped_column(JSON, default=lambda: [0, 1], nullable=False)

    # WhatsApp reminders
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whatsapp_reminder_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    whatsapp_booking_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    whatsapp_reminder_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
