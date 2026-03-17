from datetime import date
from typing import Annotated, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.dependencies import get_current_user
from app.services.availability import get_available_slots

router = APIRouter(prefix="/availability", tags=["Availability"])


@router.get("", response_model=List[str])
async def check_availability(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    collaborator_id: int = Query(...),
    target_date: date = Query(...),
    duration_slots: int = Query(1, ge=1),
    exclude_appointment_id: int = Query(None),
):
    slots = await get_available_slots(
        db, collaborator_id, target_date, duration_slots, exclude_appointment_id
    )
    return [s.isoformat() for s in slots]
