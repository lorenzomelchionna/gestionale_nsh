from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
from app.models.waitlist import WaitlistStatus


class WaitlistCreate(BaseModel):
    """Payload per creare un'iscrizione alla lista d'attesa."""
    service_id: int
    collaborator_id: Optional[int] = None   # None = qualsiasi collaboratore
    preferred_date: Optional[date] = None   # None = qualsiasi data
    notes: Optional[str] = None


class WaitlistOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    client_id: int
    service_id: int
    collaborator_id: Optional[int]
    preferred_date: Optional[date]
    notes: Optional[str]
    status: WaitlistStatus
    notified_at: Optional[datetime]
    created_at: datetime


class WaitlistOutWithNames(WaitlistOut):
    client_name: str = ""
    service_name: str = ""
    collaborator_name: Optional[str] = None
