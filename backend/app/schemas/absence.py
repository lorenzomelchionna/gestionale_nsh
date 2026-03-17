from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
from app.models.absence import AbsenceType


class AbsenceCreate(BaseModel):
    collaborator_id: int
    start_date: date
    end_date: date
    type: AbsenceType
    notes: Optional[str] = None


class AbsenceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    collaborator_id: int
    start_date: date
    end_date: date
    type: AbsenceType
    notes: Optional[str] = None
    created_at: datetime
