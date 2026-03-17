from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.payment import PaymentMethod, PaymentType


class PaymentCreate(BaseModel):
    client_id: Optional[int] = None
    appointment_id: Optional[int] = None
    amount: float
    method: PaymentMethod
    type: PaymentType = PaymentType.service
    notes: Optional[str] = None


class PaymentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    client_id: Optional[int] = None
    appointment_id: Optional[int] = None
    amount: float
    method: PaymentMethod
    type: PaymentType
    date: datetime
    notes: Optional[str] = None
