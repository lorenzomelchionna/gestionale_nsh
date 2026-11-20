from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class ChiusuraSalone(BaseModel):
    """Un periodo in cui il salone è chiuso, estremi compresi.

    Un giorno solo è `dal == al`.
    """
    dal: date
    al: date
    nota: str = Field("", max_length=80)

    @model_validator(mode="after")
    def _in_ordine(self):
        if self.al < self.dal:
            raise ValueError("La fine della chiusura viene prima dell'inizio")
        return self


class BookingConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    min_advance_hours: int | None = None
    max_advance_days: int | None = None
    min_cancel_hours: int | None = None
    slot_duration_minutes: int | None = None
    closed_weekdays: list[int] | None = None
    # Il tetto evita che un errore nella pagina — o una richiesta scritta a
    # mano — riempia la configurazione che ogni calcolo di disponibilità legge.
    closed_dates: list[ChiusuraSalone] | None = Field(None, max_length=200)
    whatsapp_enabled: bool | None = None
    whatsapp_reminder_hours: int | None = None
    whatsapp_booking_message: Optional[str] = None
    whatsapp_reminder_message: Optional[str] = None


class BookingConfigOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    is_enabled: bool
    min_advance_hours: int
    max_advance_days: int
    min_cancel_hours: int
    slot_duration_minutes: int
    closed_weekdays: list[int] = [0, 1]
    closed_dates: list[ChiusuraSalone] = []
    whatsapp_enabled: bool
    whatsapp_reminder_hours: int
    whatsapp_booking_message: Optional[str] = None
    whatsapp_reminder_message: Optional[str] = None
    updated_at: datetime
