from datetime import date
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.service import Service
from app.models.user import User
from app.dependencies import get_current_user
from app.services.availability import busy_slot_offsets, get_available_slots

router = APIRouter(prefix="/availability", tags=["Availability"])


@router.get("", response_model=List[str])
async def check_availability(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    collaborator_id: int = Query(...),
    target_date: date = Query(...),
    duration_slots: int = Query(1, ge=1),
    exclude_appointment_id: int = Query(None),
    service_ids: Optional[str] = Query(
        None,
        description=(
            "Id dei servizi separati da virgola. Se presenti, la durata e il "
            "tempo di posa vengono ricavati da loro invece che da duration_slots."
        ),
    ),
):
    offsets = None
    if service_ids:
        ids = [int(x) for x in service_ids.split(",") if x.strip().isdigit()]
        if ids:
            result = await db.execute(select(Service).where(Service.id.in_(ids)))
            trovati = {s.id: s for s in result.scalars().all()}
            # Nell'ordine richiesto, non in quello del database: la posa di un
            # servizio cade in un punto diverso a seconda di cosa viene prima.
            servizi = [trovati[i] for i in ids if i in trovati]
            if servizi:
                duration_slots = sum(s.duration_slots or 1 for s in servizi)
                offsets = busy_slot_offsets(servizi)

    slots = await get_available_slots(
        db, collaborator_id, target_date, duration_slots, exclude_appointment_id,
        busy_offsets=offsets,
    )
    return [s.isoformat() for s in slots]
