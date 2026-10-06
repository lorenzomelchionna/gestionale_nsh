from datetime import date
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.extra_day import CollaboratorExtraDay
from app.models.user import User
from app.schemas.extra_day import ExtraDayCreate, ExtraDayOut
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/extra-days", tags=["ExtraDays"])

# Come per le assenze: il calendario chiede una settimana alla volta.
MAX_GIORNI_INTERVALLO = 62


@router.get("", response_model=List[ExtraDayOut])
async def list_extra_days_in_range(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    """I giorni straordinari di tutti i collaboratori nell'intervallo.

    Per la griglia del calendario, che fino al 2026-10-06 non li caricava: un
    sabato dalle 07:30 valeva per il portale, che le 07:30 le offriva, ma in
    agenda la griglia partiva comunque alle 08:00 — l'ora non si vedeva e non
    si poteva prenotare. Tutto lo staff, come il calendario.
    """
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="La data di fine precede quella di inizio")
    if (end_date - start_date).days > MAX_GIORNI_INTERVALLO:
        raise HTTPException(status_code=400, detail="Intervallo troppo ampio")
    result = await db.execute(
        select(CollaboratorExtraDay)
        .where(CollaboratorExtraDay.date >= start_date, CollaboratorExtraDay.date <= end_date)
        .order_by(CollaboratorExtraDay.date, CollaboratorExtraDay.start_time)
    )
    return [ExtraDayOut.model_validate(e) for e in result.scalars().all()]


@router.get("/{collaborator_id}", response_model=List[ExtraDayOut])
async def list_extra_days(
    collaborator_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    result = await db.execute(
        select(CollaboratorExtraDay)
        .where(CollaboratorExtraDay.collaborator_id == collaborator_id)
        .order_by(CollaboratorExtraDay.date)
    )
    return [ExtraDayOut.model_validate(e) for e in result.scalars().all()]


@router.post("", response_model=ExtraDayOut, status_code=status.HTTP_201_CREATED)
async def create_extra_day(
    payload: ExtraDayCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    extra = CollaboratorExtraDay(**payload.model_dump())
    db.add(extra)
    await db.flush()
    await db.refresh(extra)
    return ExtraDayOut.model_validate(extra)


@router.delete("/{extra_day_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_extra_day(
    extra_day_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    result = await db.execute(
        select(CollaboratorExtraDay).where(CollaboratorExtraDay.id == extra_day_id)
    )
    extra = result.scalar_one_or_none()
    if not extra:
        raise HTTPException(status_code=404, detail="Giorno straordinario non trovato")
    await db.delete(extra)
