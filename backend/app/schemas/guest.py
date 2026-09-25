"""Prenotare dal portale senza account: chi sei, il codice, l'appuntamento."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.utils.phone import to_e164


class GuestIdentity(BaseModel):
    """Nome, cognome e numero: tutto quello che il salone chiede al telefono."""
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str

    @field_validator("first_name", "last_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Campo obbligatorio")
        return value

    @field_validator("phone")
    @classmethod
    def normalise_phone(cls, value: str) -> str:
        # Stessa forma che hanno le schede del salone: è confrontando questa
        # stringa che la prenotazione trova la scheda giusta.
        normalised = to_e164(value)
        if normalised is None:
            raise ValueError("Il numero di telefono è obbligatorio")
        return normalised


class GuestCodeRequest(GuestIdentity):
    pass


class GuestCodeSent(BaseModel):
    """False quando WhatsApp non l'ha preso: il codice c'è, ma non è partito."""
    whatsapp_sent: bool


class GuestBooking(GuestIdentity):
    code: str = Field(min_length=1, max_length=12)
    collaborator_id: int
    start_time: datetime
    service_ids: List[int] = Field(min_length=1)
    notes: Optional[str] = Field(default=None, max_length=1000)
