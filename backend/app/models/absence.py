import enum
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Enum, DateTime, Date, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AbsenceType(str, enum.Enum):
    vacation = "ferie"
    permit = "permesso"
    sick = "malattia"
    other = "altro"


class Absence(Base):
    __tablename__ = "absences"

    id: Mapped[int] = mapped_column(primary_key=True)
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("collaborators.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[AbsenceType] = mapped_column(Enum(AbsenceType), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collaborator: Mapped["Collaborator"] = relationship("Collaborator", back_populates="absences")
