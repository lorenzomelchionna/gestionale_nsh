"""Client-facing booking portal endpoints."""
from typing import Annotated, List
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.client import ClientAccount, Client
from app.models.service import Service
from app.models.collaborator import Collaborator
from app.models.appointment import Appointment, AppointmentService, AppointmentStatus, AppointmentOrigin
from app.models.booking_config import BookingConfig
from app.schemas.service import ServiceOut
from app.schemas.collaborator import CollaboratorOut, CollaboratorScheduleOut
from app.schemas.appointment import AppointmentOut, AppointmentOutWithNames, AppointmentCreate
from app.schemas.common import MessageResponse
from app.dependencies import get_current_client
from app.services.availability import get_available_slots

router = APIRouter(prefix="", tags=["Public Booking"])


# ── Public (no auth) ──────────────────────────────────────────────

@router.get("/services", response_model=List[ServiceOut])
async def public_services(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(Service).where(Service.is_active == True, Service.bookable_online == True)
    )
    return [ServiceOut.model_validate(s) for s in result.scalars().all()]


@router.get("/collaborators", response_model=List[CollaboratorOut])
async def public_collaborators(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(Collaborator)
        .options(selectinload(Collaborator.schedules), selectinload(Collaborator.services))
        .where(Collaborator.is_active == True, Collaborator.visible_online == True)
    )
    collabs = result.scalars().all()
    return [
        CollaboratorOut(
            id=c.id,
            first_name=c.first_name,
            last_name=c.last_name,
            phone=None,  # Don't expose phone publicly
            email=None,
            photo_url=c.photo_url,
            is_active=c.is_active,
            visible_online=c.visible_online,
            color=c.color,
            created_at=c.created_at,
            schedules=[CollaboratorScheduleOut.model_validate(s) for s in (c.schedules or [])],
            service_ids=[s.id for s in (c.services or [])],
        )
        for c in collabs
    ]


@router.get("/availability", response_model=List[str])
async def public_availability(
    db: Annotated[AsyncSession, Depends(get_db)],
    service_id: int = Query(...),
    collaborator_id: int = Query(...),
    target_date: date = Query(...),
):
    # Validate booking config
    cfg_result = await db.execute(select(BookingConfig).limit(1))
    cfg = cfg_result.scalar_one_or_none()
    if cfg and not cfg.is_enabled:
        raise HTTPException(status_code=403, detail="Prenotazione online disabilitata")

    # Validate max advance
    if cfg:
        max_date = date.today() + timedelta(days=cfg.max_advance_days)
        if target_date > max_date:
            raise HTTPException(status_code=400, detail="Data troppo lontana nel futuro")

    # Get service duration
    svc_result = await db.execute(select(Service).where(Service.id == service_id))
    service = svc_result.scalar_one_or_none()
    if not service or not service.bookable_online:
        raise HTTPException(status_code=404, detail="Servizio non trovato o non prenotabile online")

    slots = await get_available_slots(db, collaborator_id, target_date, service.duration_slots)
    return [s.isoformat() for s in slots]


# ── Authenticated client endpoints ────────────────────────────────

@router.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    payload: AppointmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    # Find the client linked to this account
    client_result = await db.execute(
        select(Client).where(Client.account_id == current_account.id)
    )
    client = client_result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=400, detail="Profilo cliente non trovato")

    # Validate booking config
    cfg_result = await db.execute(select(BookingConfig).limit(1))
    cfg = cfg_result.scalar_one_or_none()
    if cfg and not cfg.is_enabled:
        raise HTTPException(status_code=403, detail="Prenotazione online disabilitata")

    # Validate services
    services = []
    for sid in payload.service_ids:
        r = await db.execute(select(Service).where(Service.id == sid))
        svc = r.scalar_one_or_none()
        if not svc or not svc.bookable_online:
            raise HTTPException(status_code=400, detail=f"Servizio {sid} non prenotabile online")
        services.append(svc)

    appt = Appointment(
        client_id=client.id,
        collaborator_id=payload.collaborator_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        notes=payload.notes,
        status=AppointmentStatus.pending,  # Always pending from portal
        origin=AppointmentOrigin.online,
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
    await db.refresh(appt, ["appointment_services"])
    return AppointmentOut.model_validate(appt)


@router.get("/appointments", response_model=List[AppointmentOutWithNames])
async def my_appointments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    client_result = await db.execute(
        select(Client).where(Client.account_id == current_account.id)
    )
    client = client_result.scalar_one_or_none()
    if not client:
        return []

    result = await db.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.client),
            selectinload(Appointment.collaborator),
            selectinload(Appointment.appointment_services),
        )
        .where(Appointment.client_id == client.id)
        .order_by(Appointment.start_time.desc())
    )
    appointments = result.scalars().all()

    out = []
    for a in appointments:
        item = AppointmentOutWithNames.model_validate(a)
        item.client_name = f"{a.client.first_name} {a.client.last_name}" if a.client else ""
        item.collaborator_name = f"{a.collaborator.first_name} {a.collaborator.last_name}" if a.collaborator else ""
        item.total_price = sum(s.price_snapshot for s in a.appointment_services)
        out.append(item)
    return out


@router.post("/appointments/{appointment_id}/cancel", response_model=MessageResponse)
async def cancel_my_appointment(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    client_result = await db.execute(
        select(Client).where(Client.account_id == current_account.id)
    )
    client = client_result.scalar_one_or_none()

    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.client_id == (client.id if client else -1),
        )
    )
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")

    if appt.status in (AppointmentStatus.completed, AppointmentStatus.cancelled):
        raise HTTPException(status_code=400, detail="Impossibile cancellare questo appuntamento")

    # Check min cancel hours
    cfg_result = await db.execute(select(BookingConfig).limit(1))
    cfg = cfg_result.scalar_one_or_none()
    if cfg:
        min_notice = timedelta(hours=cfg.min_cancel_hours)
        if appt.start_time - datetime.now(timezone.utc) < min_notice:
            raise HTTPException(
                status_code=400,
                detail=f"Cancellazione non consentita con meno di {cfg.min_cancel_hours}h di preavviso"
            )

    appt.status = AppointmentStatus.cancelled
    return MessageResponse(message="Appuntamento cancellato")


@router.post("/appointments/{appointment_id}/accept-alternative", response_model=MessageResponse)
async def accept_alternative(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    client_result = await db.execute(select(Client).where(Client.account_id == current_account.id))
    client = client_result.scalar_one_or_none()
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.client_id == (client.id if client else -1),
        )
    )
    appt = result.scalar_one_or_none()
    if not appt or appt.status != AppointmentStatus.rescheduled:
        raise HTTPException(status_code=400, detail="Nessuna proposta alternativa attiva")

    appt.start_time = appt.alternative_time
    # Recalculate end_time (keep duration)
    duration = appt.end_time - appt.start_time
    appt.end_time = appt.alternative_time + duration
    appt.alternative_time = None
    appt.status = AppointmentStatus.confirmed
    return MessageResponse(message="Proposta accettata")


@router.post("/appointments/{appointment_id}/reject-alternative", response_model=MessageResponse)
async def reject_alternative(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    client_result = await db.execute(select(Client).where(Client.account_id == current_account.id))
    client = client_result.scalar_one_or_none()
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.client_id == (client.id if client else -1),
        )
    )
    appt = result.scalar_one_or_none()
    if not appt or appt.status != AppointmentStatus.rescheduled:
        raise HTTPException(status_code=400, detail="Nessuna proposta alternativa attiva")

    appt.status = AppointmentStatus.cancelled
    appt.alternative_time = None
    return MessageResponse(message="Proposta rifiutata")
