from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.extra_day import CollaboratorExtraDay
from app.models.user import User
from app.schemas.extra_day import ExtraDayCreate, ExtraDayOut
from app.dependencies import get_current_user

router = APIRouter(prefix="/extra-days", tags=["ExtraDays"])


@router.get("/{collaborator_id}", response_model=List[ExtraDayOut])
async def list_extra_days(
    collaborator_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
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
    current_user: Annotated[User, Depends(get_current_user)],
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
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(CollaboratorExtraDay).where(CollaboratorExtraDay.id == extra_day_id)
    )
    extra = result.scalar_one_or_none()
    if not extra:
        raise HTTPException(status_code=404, detail="Giorno straordinario non trovato")
    await db.delete(extra)
