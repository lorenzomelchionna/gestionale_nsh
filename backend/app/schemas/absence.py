from datetime import datetime, date, time
from typing import Optional
from pydantic import BaseModel, model_validator
from app.models.absence import AbsenceType


class AbsenceCreate(BaseModel):
    collaborator_id: int
    start_date: date
    end_date: date
    # Entrambe assenti = giornata intera. Valorizzate = solo quella fascia,
    # ripetuta su ogni giorno dell'intervallo.
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    type: AbsenceType
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _fascia_coerente(self):
        if self.end_date < self.start_date:
            raise ValueError("La data di fine precede quella di inizio.")
        # Una sola delle due ore lascerebbe l'assenza senza un confine: il
        # calendario non saprebbe dove farla finire e la tratterebbe come
        # giornata intera, cioè l'opposto di quello che si voleva chiedere.
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError(
                "Indica sia l'ora di inizio sia quella di fine, oppure nessuna "
                "delle due per un'assenza a giornata intera."
            )
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("L'ora di fine deve essere successiva a quella di inizio.")
        return self


class AbsenceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    collaborator_id: int
    start_date: date
    end_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    type: AbsenceType
    notes: Optional[str] = None
    created_at: datetime
