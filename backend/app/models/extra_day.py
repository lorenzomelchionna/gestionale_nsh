from datetime import datetime, date, time
from typing import Optional
from sqlalchemy import DateTime, Date, Time, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CollaboratorExtraDay(Base):
    __tablename__ = "collaborator_extra_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("collaborators.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collaborator: Mapped["Collaborator"] = relationship("Collaborator", back_populates="extra_days")
