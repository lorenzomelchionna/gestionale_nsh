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
    """An appointment with the names and the total the caller would otherwise
    have to fetch one by one.

    Every field below defaults to empty, so an endpoint that builds this by
    hand and forgets one answers with a plausible-looking blank instead of
    failing — which is exactly how `service_names` went out empty from every
    route for as long as it existed. Build it with `from_appointment` and the
    rule stays in one place.
    """

    client_name: str = ""
    collaborator_name: str = ""
    service_names: List[str] = []
    total_price: float = 0.0

    @classmethod
    def from_appointment(cls, a) -> "AppointmentOutWithNames":
        """Project an ORM appointment, with `appointment_detail_loads()` applied
        to the query that fetched it."""
        out = cls.model_validate(a)
        out.client_name = f"{a.client.first_name} {a.client.last_name}" if a.client else ""
        out.collaborator_name = (
            f"{a.collaborator.first_name} {a.collaborator.last_name}" if a.collaborator else ""
        )
        # Booked order, not alphabetical: "Taglio + barba" is how it was sold.
        out.service_names = [
            s.service.name for s in a.appointment_services if s.service is not None
        ]
        out.total_price = sum(s.price_snapshot for s in a.appointment_services)
        return out
