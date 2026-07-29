from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator

from app.utils.phone import to_e164


class ClientBase(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    birth_date: Optional[date] = None
    notes: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def normalise_phone(cls, value: Optional[str]) -> Optional[str]:
        """Store canonically so a hand-entered client and the same client
        registering online resolve to one record. See app/utils/phone.py."""
        return to_e164(value)


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

    @field_validator("phone")
    @classmethod
    def normalise_phone(cls, value: str) -> str:
        """Normalised before registration looks for an existing client by phone,
        so the lookup compares the same shape that admin-entered records hold."""
        normalised = to_e164(value)
        if normalised is None:
            raise ValueError("Il numero di telefono è obbligatorio")
        return normalised


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
