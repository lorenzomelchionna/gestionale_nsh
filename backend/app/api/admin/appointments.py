from typing import Annotated, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.appointment import Appointment, AppointmentService, AppointmentStatus, AppointmentOrigin
from app.models.service import Service
from app.models.client import Client
from app.models.collaborator import Collaborator
from app.models.user import User
from app.schemas.appointment import (
    AppointmentCreate, AppointmentUpdate, AppointmentOut,
    AppointmentOutWithNames, AppointmentReject, AppointmentReschedule,
)
from app.schemas.common import PaginatedResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/appointments", tags=["Appointments"])


async def _load_appointment(db: AsyncSession, appointment_id: int) -> Appointment:
    result = await db.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.client),
            selectinload(Appointment.collaborator),
            selectinload(Appointment.appointment_services),
        )
        .where(Appointment.id == appointment_id)
    )
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")
    return a


def _enrich(a: Appointment) -> AppointmentOutWithNames:
    out = AppointmentOutWithNames.model_validate(a)
    out.client_name = f"{a.client.first_name} {a.client.last_name}" if a.client else ""
    out.collaborator_name = f"{a.collaborator.first_name} {a.collaborator.last_name}" if a.collaborator else ""
    out.total_price = sum(s.price_snapshot for s in a.appointment_services)
    return out


@router.get("", response_model=PaginatedResponse[AppointmentOutWithNames])
async def list_appointments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    collaborator_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    q = select(Appointment).options(
        selectinload(Appointment.client),
        selectinload(Appointment.collaborator),
        selectinload(Appointment.appointment_services),
    )
    if date_from:
        q = q.where(Appointment.start_time >= date_from)
    if date_to:
        q = q.where(Appointment.start_time <= date_to)
    if collaborator_id:
        q = q.where(Appointment.collaborator_id == collaborator_id)
    if status_filter:
        q = q.where(Appointment.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(q.order_by(Appointment.start_time).offset((page - 1) * page_size).limit(page_size))
    return PaginatedResponse(
        items=[_enrich(a) for a in result.scalars().all()],
        total=total, page=page, page_size=page_size, pages=-(-total // page_size),
    )


@router.get("/pending", response_model=List[AppointmentOutWithNames])
async def list_pending(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.client),
            selectinload(Appointment.collaborator),
            selectinload(Appointment.appointment_services),
        )
        .where(Appointment.status == AppointmentStatus.pending)
        .order_by(Appointment.created_at)
    )
    return [_enrich(a) for a in result.scalars().all()]


@router.post("", response_model=AppointmentOutWithNames, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    # Validate services exist
    services = []
    for sid in payload.service_ids:
        r = await db.execute(select(Service).where(Service.id == sid))
        svc = r.scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=400, detail=f"Servizio {sid} non trovato")
        services.append(svc)

    appt = Appointment(
        client_id=payload.client_id,
        collaborator_id=payload.collaborator_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        notes=payload.notes,
        status=AppointmentStatus.confirmed,
        origin=payload.origin,
    )
    db.add(appt)
    await db.flush()

    for svc in services:
        db.add(AppointmentService(
            appointment_id=appt.id,
            service_id=svc.id,
            price_snapshot=float(svc.price),
        ))
    await db.flush()

    return _enrich(await _load_appointment(db, appt.id))


@router.get("/{appointment_id}", response_model=AppointmentOutWithNames)
async def get_appointment(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return _enrich(await _load_appointment(db, appointment_id))


@router.put("/{appointment_id}", response_model=AppointmentOutWithNames)
async def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    a = await _load_appointment(db, appointment_id)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"service_ids"}).items():
        setattr(a, field, value)

    if payload.service_ids is not None:
        for s in a.appointment_services:
            await db.delete(s)
        await db.flush()
        for sid in payload.service_ids:
            r = await db.execute(select(Service).where(Service.id == sid))
            svc = r.scalar_one_or_none()
            if svc:
                db.add(AppointmentService(
                    appointment_id=a.id,
                    service_id=svc.id,
                    price_snapshot=float(svc.price),
                ))
    await db.flush()
    return _enrich(await _load_appointment(db, appointment_id))


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    a = await _load_appointment(db, appointment_id)
    a.status = AppointmentStatus.cancelled


@router.post("/{appointment_id}/confirm", response_model=AppointmentOutWithNames)
async def confirm_appointment(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    a = await _load_appointment(db, appointment_id)
    if a.status != AppointmentStatus.pending:
        raise HTTPException(status_code=400, detail="Solo gli appuntamenti 'in attesa' possono essere confermati")
    a.status = AppointmentStatus.confirmed
    await db.flush()
    return _enrich(await _load_appointment(db, appointment_id))


@router.post("/{appointment_id}/reject", response_model=AppointmentOutWithNames)
async def reject_appointment(
    appointment_id: int,
    payload: AppointmentReject,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    a = await _load_appointment(db, appointment_id)
    if a.status not in (AppointmentStatus.pending, AppointmentStatus.confirmed):
        raise HTTPException(status_code=400, detail="Stato non valido per il rifiuto")
    a.status = AppointmentStatus.rejected
    a.rejection_reason = payload.reason
    await db.flush()
    return _enrich(await _load_appointment(db, appointment_id))


@router.post("/{appointment_id}/reschedule", response_model=AppointmentOutWithNames)
async def reschedule_appointment(
    appointment_id: int,
    payload: AppointmentReschedule,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    a = await _load_appointment(db, appointment_id)
    a.status = AppointmentStatus.rescheduled
    a.alternative_time = payload.alternative_time
    await db.flush()
    return _enrich(await _load_appointment(db, appointment_id))


@router.post("/{appointment_id}/complete", response_model=AppointmentOutWithNames)
async def complete_appointment(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    a = await _load_appointment(db, appointment_id)
    if a.status != AppointmentStatus.confirmed:
        raise HTTPException(status_code=400, detail="Solo gli appuntamenti confermati possono essere completati")
    a.status = AppointmentStatus.completed
    await db.flush()
    return _enrich(await _load_appointment(db, appointment_id))
