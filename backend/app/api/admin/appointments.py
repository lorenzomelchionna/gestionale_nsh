from typing import Annotated, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.database import get_db
from app.models.appointment import (
    Appointment, AppointmentService, AppointmentStatus, AppointmentOrigin,
    appointment_detail_loads,
)
from app.models.service import Service
from app.models.client import Client
from app.models.collaborator import Collaborator
from app.models.user import User
from app.schemas.appointment import (
    AppointmentComplete, AppointmentCreate, AppointmentUpdate, AppointmentOut,
    AppointmentOutWithNames, AppointmentReject, AppointmentReschedule,
)
from app.schemas.common import PaginatedResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _trigger_booking_confirmation(appointment_id: int):
    """Fire-and-forget dual-channel (email + WA) confirmation."""
    try:
        from app.tasks.reminders import send_booking_confirmation_task
        send_booking_confirmation_task.delay(appointment_id)
    except Exception as e:
        print(f"[NOTIFY] Could not queue confirmation for appointment {appointment_id}: {e}")


async def _load_appointment(db: AsyncSession, appointment_id: int) -> Appointment:
    result = await db.execute(
        select(Appointment)
        .options(*appointment_detail_loads())
        .where(Appointment.id == appointment_id)
    )
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")
    return a


_enrich = AppointmentOutWithNames.from_appointment


@router.get("", response_model=PaginatedResponse[AppointmentOutWithNames])
async def list_appointments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    collaborator_id: Optional[int] = Query(None),
    client_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    order: str = Query("asc", pattern="^(asc|desc)$"),
):
    """L'elenco degli appuntamenti, con i filtri per trovarne uno.

    L'ordine è un parametro e non una costante perché le due schermate che
    leggono da qui vogliono il contrario l'una dell'altra: il calendario legge
    una giornata dall'inizio alla fine, l'elenco storico parte da ieri e va
    all'indietro. Il default resta `asc`, che è quello che il calendario si
    aspettava già prima che questo parametro esistesse.
    """
    q = select(Appointment).options(*appointment_detail_loads())
    if date_from:
        q = q.where(Appointment.start_time >= date_from)
    if date_to:
        q = q.where(Appointment.start_time <= date_to)
    if collaborator_id:
        q = q.where(Appointment.collaborator_id == collaborator_id)
    if client_id:
        q = q.where(Appointment.client_id == client_id)
    if status_filter:
        q = q.where(Appointment.status == status_filter)
    if search:
        # Nome, cognome o telefono: al banco si cerca con quello che si ha in
        # mano, che è una delle tre cose e non si sa mai quale.
        like = f"%{search.strip()}%"
        q = q.join(Appointment.client).where(or_(
            Client.first_name.ilike(like),
            Client.last_name.ilike(like),
            Client.phone.ilike(like),
            (Client.first_name + " " + Client.last_name).ilike(like),
        ))

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    ordering = (
        Appointment.start_time.desc() if order == "desc" else Appointment.start_time.asc()
    )
    result = await db.execute(q.order_by(ordering).offset((page - 1) * page_size).limit(page_size))
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
        .options(*appointment_detail_loads())
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
    # Committed before the hand-off, not after: the worker reads the
    # appointment from its own transaction, so an id queued while this one is
    # still open points at a row it cannot see — and the client's confirmation
    # is dropped in silence.
    await db.commit()
    _trigger_booking_confirmation(appt.id)

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
    # The row already exists here, so the worker would find it — but with the
    # old status. Committing first also means a request that fails afterwards
    # cannot leave the client holding a confirmation for an appointment that
    # was rolled back.
    await db.commit()
    _trigger_booking_confirmation(appointment_id)
    return _enrich(await _load_appointment(db, appointment_id))


@router.post("/{appointment_id}/cancel", response_model=AppointmentOutWithNames)
async def cancel_appointment(
    appointment_id: int,
    payload: AppointmentReject,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    a = await _load_appointment(db, appointment_id)
    if a.status in (AppointmentStatus.completed, AppointmentStatus.cancelled, AppointmentStatus.rejected):
        raise HTTPException(status_code=400, detail="Appuntamento già terminato")
    a.status = AppointmentStatus.cancelled
    a.rejection_reason = payload.reason
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
    payload: Optional[AppointmentComplete] = None,
):
    """Chiude una visita, con la sua nota se c'è.

    Il corpo è facoltativo: «segna completato» senza scrivere niente deve
    restare un clic solo, che è come lo si usa quando il salone è pieno.
    """
    a = await _load_appointment(db, appointment_id)
    if a.status != AppointmentStatus.confirmed:
        raise HTTPException(status_code=400, detail="Solo gli appuntamenti confermati possono essere completati")
    a.status = AppointmentStatus.completed
    if payload is not None and payload.visit_notes is not None:
        nota = payload.visit_notes.strip()
        # Una stringa vuota qui vuol dire «non ho scritto niente», non
        # «cancella quello che c'era»: la nota si svuota dal PUT, di proposito.
        if nota:
            a.visit_notes = nota
    await db.flush()
    return _enrich(await _load_appointment(db, appointment_id))
