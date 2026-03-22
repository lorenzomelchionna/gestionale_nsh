from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr


class ClientBase(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    birth_date: Optional[date] = None
    notes: Optional[str] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(ClientBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ClientOut(ClientBase):
    model_config = {"from_attributes": True}

    id: int
    is_active: bool
    account_id: Optional[int] = None
    created_at: datetime


class ClientRegister(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: EmailStr
    password: str


class ClientAccountOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    is_active: bool
    created_at: datetime


class ClientLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str
    new_password: str
