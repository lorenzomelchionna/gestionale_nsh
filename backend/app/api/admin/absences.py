from datetime import date
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.absence import Absence
from app.models.user import User
from app.schemas.absence import AbsenceCreate, AbsenceOut
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/absences", tags=["Absences"])


# Il calendario mostra una settimana alla volta: due mesi bastano e avanzano,
# e un tetto evita che qualcuno chieda dieci anni di assenze in una chiamata.
MAX_GIORNI_INTERVALLO = 62


@router.get("", response_model=List[AbsenceOut])
async def list_absences_in_range(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    """Le assenze di tutti i collaboratori che toccano l'intervallo.

    Per la griglia del calendario, che fino al 2026-09-29 le assenze non le
    caricava affatto: un permesso bloccava le prenotazioni online ma in
    agenda quell'ora sembrava libera. Tutto lo staff, come il calendario.
    """
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="La data di fine precede quella di inizio")
    if (end_date - start_date).days > MAX_GIORNI_INTERVALLO:
        raise HTTPException(status_code=400, detail="Intervallo troppo ampio")
    result = await db.execute(
        select(Absence)
        .where(Absence.start_date <= end_date, Absence.end_date >= start_date)
        .order_by(Absence.start_date, Absence.collaborator_id)
    )
    return [AbsenceOut.model_validate(a) for a in result.scalars().all()]


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
    current_user: Annotated[User, Depends(require_admin)],
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
    current_user: Annotated[User, Depends(require_admin)],
):
    result = await db.execute(select(Absence).where(Absence.id == absence_id))
    absence = result.scalar_one_or_none()
    if not absence:
        raise HTTPException(status_code=404, detail="Assenza non trovata")
    await db.delete(absence)
