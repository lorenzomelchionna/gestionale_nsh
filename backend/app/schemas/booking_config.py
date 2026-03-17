from datetime import datetime
from pydantic import BaseModel


class BookingConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    min_advance_hours: int | None = None
    max_advance_days: int | None = None
    min_cancel_hours: int | None = None
    slot_duration_minutes: int | None = None


class BookingConfigOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    is_enabled: bool
    min_advance_hours: int
    max_advance_days: int
    min_cancel_hours: int
    slot_duration_minutes: int
    updated_at: datetime
