from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class BookingConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    min_advance_hours: int | None = None
    max_advance_days: int | None = None
    min_cancel_hours: int | None = None
    slot_duration_minutes: int | None = None
    closed_weekdays: list[int] | None = None
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
    whatsapp_enabled: bool
    whatsapp_reminder_hours: int
    whatsapp_booking_message: Optional[str] = None
    whatsapp_reminder_message: Optional[str] = None
    updated_at: datetime
