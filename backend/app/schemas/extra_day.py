from datetime import datetime, date, time
from typing import Optional
from pydantic import BaseModel


class ExtraDayCreate(BaseModel):
    collaborator_id: int
    date: date
    start_time: time
    end_time: time
    notes: Optional[str] = None


class ExtraDayOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    collaborator_id: int
    date: date
    start_time: time
    end_time: time
    notes: Optional[str] = None
    created_at: datetime
