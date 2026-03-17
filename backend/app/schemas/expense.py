from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel


class ExpenseCreate(BaseModel):
    description: str
    amount: float
    category: str
    date: date
    notes: Optional[str] = None


class ExpenseUpdate(ExpenseCreate):
    description: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    date: Optional[date] = None


class ExpenseOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    description: str
    amount: float
    category: str
    date: date
    notes: Optional[str] = None
    created_at: datetime
