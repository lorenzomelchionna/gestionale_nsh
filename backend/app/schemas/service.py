from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    duration_slots: int = 1
    category: str
    bookable_online: bool = True
    is_active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    price: Optional[float] = None
    duration_slots: Optional[int] = None
    category: Optional[str] = None


class ServiceOut(ServiceBase):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime
