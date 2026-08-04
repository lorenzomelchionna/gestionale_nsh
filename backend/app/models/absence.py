import enum
from datetime import datetime, date, time
from typing import Optional
from sqlalchemy import String, Enum, DateTime, Date, Text, Time, ForeignKey, func
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

    # Un permesso di due ore non è una giornata di ferie, ma finora si poteva
    # registrare solo a giornata intera — quindi per prendersi il pomeriggio
    # bisognava togliersi tutto il giorno dal calendario.
    #
    # Entrambe NULL = giornata intera, cioè il comportamento di sempre. Quando
    # sono valorizzate, l'assenza blocca solo quella fascia e il resto della
    # giornata resta prenotabile. Su un intervallo di più giorni la fascia vale
    # per ogni giorno dell'intervallo: "tutte le mattine di questa settimana".
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    type: Mapped[AbsenceType] = mapped_column(Enum(AbsenceType), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collaborator: Mapped["Collaborator"] = relationship("Collaborator", back_populates="absences")
