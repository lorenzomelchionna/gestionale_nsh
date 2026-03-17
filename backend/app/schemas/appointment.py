from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models.appointment import AppointmentStatus, AppointmentOrigin


class AppointmentServiceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    service_id: int
    price_snapshot: float


class AppointmentBase(BaseModel):
    client_id: int
    collaborator_id: int
    start_time: datetime
    end_time: datetime
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    service_ids: List[int]
    origin: AppointmentOrigin = AppointmentOrigin.salon


class AppointmentUpdate(BaseModel):
    collaborator_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    notes: Optional[str] = None
    visit_notes: Optional[str] = None
    service_ids: Optional[List[int]] = None


class AppointmentReject(BaseModel):
    reason: Optional[str] = None


class AppointmentReschedule(BaseModel):
    alternative_time: datetime


class AppointmentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    client_id: int
    collaborator_id: int
    start_time: datetime
    end_time: datetime
    status: AppointmentStatus
    origin: AppointmentOrigin
    notes: Optional[str] = None
    visit_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    alternative_time: Optional[datetime] = None
    reminder_sent: bool
    created_at: datetime
    appointment_services: List[AppointmentServiceOut] = []


class AppointmentOutWithNames(AppointmentOut):
    client_name: str = ""
    collaborator_name: str = ""
    service_names: List[str] = []
    total_price: float = 0.0
