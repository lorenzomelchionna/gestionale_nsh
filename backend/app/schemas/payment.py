from datetime import datetime
from typing import Optional
from pydantic import BaseModel, model_validator
from app.models.payment import PaymentMethod, PaymentType


class PaymentCreate(BaseModel):
    client_id: Optional[int] = None
    appointment_id: Optional[int] = None
    amount: float
    method: PaymentMethod
    type: PaymentType = PaymentType.service
    notes: Optional[str] = None
    cash_amount: Optional[float] = None
    card_amount: Optional[float] = None

    @model_validator(mode="after")
    def validate_split(self) -> "PaymentCreate":
        if self.method == PaymentMethod.mixed:
            if self.cash_amount is None or self.card_amount is None:
                raise ValueError("Per pagamento misto specificare cash_amount e card_amount")
            if self.cash_amount < 0 or self.card_amount < 0:
                raise ValueError("Gli importi devono essere positivi")
            total = round(self.cash_amount + self.card_amount, 2)
            if abs(total - round(self.amount, 2)) > 0.01:
                raise ValueError(
                    f"cash_amount + card_amount ({total}) deve corrispondere ad amount ({self.amount})"
                )
        else:
            # Non misto: ignora i campi split
            self.cash_amount = None
            self.card_amount = None
        return self


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
    cash_amount: Optional[float] = None
    card_amount: Optional[float] = None
