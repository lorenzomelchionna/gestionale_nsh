from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.absence import Absence
from app.models.user import User
from app.schemas.absence import AbsenceCreate, AbsenceOut
from app.dependencies import get_current_user

router = APIRouter(prefix="/absences", tags=["Absences"])


@router.get("/{collaborator_id}", response_model=List[AbsenceOut])
async def list_absences(
    collaborator_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Absence).where(Absence.collaborator_id == collaborator_id).order_by(Absence.start_date)
    )
    return [AbsenceOut.model_validate(a) for a in result.scalars().all()]


@router.post("", response_model=AbsenceOut, status_code=status.HTTP_201_CREATED)
async def create_absence(
    payload: AbsenceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    absence = Absence(**payload.model_dump())
    db.add(absence)
    await db.flush()
    await db.refresh(absence)
    return AbsenceOut.model_validate(absence)


@router.delete("/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_absence(
    absence_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Absence).where(Absence.id == absence_id))
    absence = result.scalar_one_or_none()
    if not absence:
        raise HTTPException(status_code=404, detail="Assenza non trovata")
    await db.delete(absence)
