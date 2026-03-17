from datetime import datetime
from sqlalchemy import Boolean, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class BookingConfig(Base):
    __tablename__ = "booking_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_advance_hours: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    max_advance_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    min_cancel_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
