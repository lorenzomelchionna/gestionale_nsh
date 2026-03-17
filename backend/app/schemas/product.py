from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.product import MovementType


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    purchase_price: float
    sale_price: float
    category: str
    quantity: int = 0
    min_quantity: int = 2
    photo_url: Optional[str] = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    name: Optional[str] = None
    purchase_price: Optional[float] = None
    sale_price: Optional[float] = None
    category: Optional[str] = None


class ProductOut(ProductBase):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime


class ProductMovementCreate(BaseModel):
    product_id: int
    type: MovementType
    quantity: int
    notes: Optional[str] = None
    appointment_id: Optional[int] = None


class ProductMovementOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    product_id: int
    type: MovementType
    quantity: int
    notes: Optional[str] = None
    appointment_id: Optional[int] = None
    created_at: datetime
