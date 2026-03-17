from datetime import datetime, time
from typing import Optional, List
from pydantic import BaseModel, EmailStr


class CollaboratorScheduleBase(BaseModel):
    day_of_week: int
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_working: bool = True


class CollaboratorScheduleOut(CollaboratorScheduleBase):
    model_config = {"from_attributes": True}
    id: int
    collaborator_id: int


class CollaboratorBase(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    photo_url: Optional[str] = None
    is_active: bool = True
    visible_online: bool = True
    color: str = "#C8A96E"


class CollaboratorCreate(CollaboratorBase):
    pass


class CollaboratorUpdate(CollaboratorBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = None
    visible_online: Optional[bool] = None


class CollaboratorOut(CollaboratorBase):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime
    schedules: List[CollaboratorScheduleOut] = []
    service_ids: List[int] = []

    @classmethod
    def from_orm_with_services(cls, obj):
        d = {
            **{k: getattr(obj, k) for k in cls.model_fields},
            "service_ids": [s.id for s in (obj.services or [])],
            "schedules": obj.schedules or [],
        }
        return cls.model_validate(d)
