"""Client-facing booking portal endpoints."""
from typing import Annotated, List
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.database import get_db
from app.models.client import ClientAccount, Client
from app.models.service import Service
from app.models.collaborator import Collaborator
from app.models.appointment import (
    Appointment, AppointmentService, AppointmentStatus, AppointmentOrigin,
    appointment_detail_loads,
)
from app.models.booking_config import BookingConfig
from app.models.waitlist import WaitlistEntry, WaitlistStatus
from app.schemas.service import ServiceOut
from app.schemas.collaborator import CollaboratorOut, CollaboratorScheduleOut
from app.schemas.appointment import AppointmentCreate, PortalAppointmentOut
from app.schemas.waitlist import WaitlistCreate, WaitlistOut
from app.schemas.common import MessageResponse
from app.dependencies import get_current_client
from app.services.availability import busy_slot_offsets, get_available_slots

router = APIRouter(prefix="", tags=["Public Booking"])

# One request per visible month is the point of the calendar endpoint; a wider
# span would run a slot computation per day for no one's benefit.
MAX_CALENDAR_DAYS = 62

# A client with this many requests still waiting is either indecisive or a
# script. The salon answers within the day, so a real person never stacks up
# four unanswered requests; a flood, on the other hand, is only interesting to
# the attacker if it can reach the whole calendar.
MAX_PENDING_PER_CLIENT = 3


class DayAvailability(BaseModel):
    """Free slots on one day — 0 means closed, fully booked or out of window."""
    date: date
    slots: int


def _trigger_new_booking_alert(appointment_id: int):
    """Fire-and-forget staff alert for a booking made from the portal.

    Queueing must never sink the booking itself: the client did nothing wrong
    if Redis is unreachable, and the request is safely in the database by the
    time we get here — worst case the salon finds it under "In attesa", which
    is exactly the situation before this alert existed.
    """
    try:
        from app.tasks.reminders import notify_new_booking
        notify_new_booking.delay(appointment_id)
    except Exception as e:
        print(f"[NOTIFY] Could not queue staff alert for appointment {appointment_id}: {e}")


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


async def _bookable_collaborator(
    db: AsyncSession, collaborator_id: int, service_ids: List[int]
) -> Collaborator:
    """
    Load a collaborator the portal may book, or raise.

    The booking flow only ever offers collaborators that are active, visible
    online and perform the chosen service, but that filtering happens in the
    browser. A request that did not come through it — a stale tab, a retried
    call, anything hand-made — would otherwise book a colour with someone who
    does not do colour, and the salon would find it in the calendar.
    """
    result = await db.execute(
        select(Collaborator)
        .options(selectinload(Collaborator.services))
        .where(
            Collaborator.id == collaborator_id,
            Collaborator.is_active == True,  # noqa: E712 — SQL boolean, not Python
            Collaborator.visible_online == True,  # noqa: E712
        )
    )
    collab = result.scalar_one_or_none()
    if not collab:
        raise HTTPException(
            status_code=404,
            detail="Collaboratore non disponibile per le prenotazioni online",
        )

    offered = {s.id for s in (collab.services or [])}
    if not all(sid in offered for sid in service_ids):
        raise HTTPException(
            status_code=400,
            detail="Il collaboratore selezionato non esegue il servizio richiesto",
        )
    return collab


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

    await _bookable_collaborator(db, collaborator_id, [service_id])

    slots = await get_available_slots(
        db, collaborator_id, target_date, service.duration_slots,
        busy_offsets=busy_slot_offsets([service]),
    )
    return [s.isoformat() for s in slots]


@router.get("/availability/calendar", response_model=List[DayAvailability])
async def public_availability_calendar(
    db: Annotated[AsyncSession, Depends(get_db)],
    service_id: int = Query(...),
    collaborator_id: int = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    """
    How many slots each day of a range holds.

    The calendar needs to grey out full and closed days before the client picks
    one. Asking day by day would be a request per cell, so the whole visible
    month comes back at once.
    """
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="Intervallo di date non valido")
    if (end_date - start_date).days > MAX_CALENDAR_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Intervallo troppo ampio (massimo {MAX_CALENDAR_DAYS} giorni)",
        )

    cfg_result = await db.execute(select(BookingConfig).limit(1))
    cfg = cfg_result.scalar_one_or_none()
    if cfg and not cfg.is_enabled:
        raise HTTPException(status_code=403, detail="Prenotazione online disabilitata")

    svc_result = await db.execute(select(Service).where(Service.id == service_id))
    service = svc_result.scalar_one_or_none()
    if not service or not service.bookable_online:
        raise HTTPException(status_code=404, detail="Servizio non trovato o non prenotabile online")

    await _bookable_collaborator(db, collaborator_id, [service_id])

    today = date.today()
    # Booking windows are enforced per-day here rather than by clipping the
    # range, so the calendar can still render those days as unavailable instead
    # of the month appearing to end early.
    min_day = today
    max_day = today + timedelta(days=cfg.max_advance_days) if cfg else None

    out: List[DayAvailability] = []
    day = start_date
    while day <= end_date:
        if day < min_day or (max_day and day > max_day):
            out.append(DayAvailability(date=day, slots=0))
        else:
            slots = await get_available_slots(
                db, collaborator_id, day, service.duration_slots,
                busy_offsets=busy_slot_offsets([service]),
            )
            out.append(DayAvailability(date=day, slots=len(slots)))
        day += timedelta(days=1)
    return out


# ── Authenticated client endpoints ────────────────────────────────

@router.post("/appointments", response_model=PortalAppointmentOut, status_code=status.HTTP_201_CREATED)
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

    await _bookable_collaborator(db, payload.collaborator_id, payload.service_ids)

    # The times are the one part of the payload the browser computes for itself,
    # so until here nothing had ever checked them. Without this block a client
    # could book outside working hours, in the past, on top of someone else, or
    # 00:00–23:59 on every collaborator for the next two months — and since a
    # `pending` request already holds its slot, that last one empties the whole
    # public calendar until the salon deletes the rows by hand.
    start = payload.start_time
    start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start.astimezone(timezone.utc)

    if cfg:
        max_date = date.today() + timedelta(days=cfg.max_advance_days)
        if start.date() > max_date:
            raise HTTPException(status_code=400, detail="Data troppo lontana nel futuro")

    # Same figure the availability endpoints use, summed because a booking may
    # carry several services ("taglio + barba" is two blocks, not one).
    duration_slots = sum(svc.duration_slots for svc in services)
    slots = await get_available_slots(
        db, payload.collaborator_id, start.date(), duration_slots,
        busy_offsets=busy_slot_offsets(services),
    )
    if start not in slots:
        # Covers every rule get_available_slots already knows: working hours,
        # absences, minimum notice, and slots taken by someone else. Answering
        # with one message keeps us from telling a stranger which of those it
        # was, i.e. from describing the salon's diary to whoever asks.
        raise HTTPException(
            status_code=409,
            detail="Questo orario non è più disponibile. Scegline un altro.",
        )

    # Derived, never accepted: end_time from the browser is what let a booking
    # claim a whole day.
    slot_minutes = cfg.slot_duration_minutes if cfg else 30
    end = start + timedelta(minutes=duration_slots * slot_minutes)

    pending_count = (await db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.client_id == client.id,
            Appointment.status == AppointmentStatus.pending,
        )
    )).scalar_one()
    if pending_count >= MAX_PENDING_PER_CLIENT:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Hai già {MAX_PENDING_PER_CLIENT} richieste in attesa di conferma. "
                "Attendi la risposta del salone prima di prenotare ancora."
            ),
        )

    appt = Appointment(
        client_id=client.id,
        collaborator_id=payload.collaborator_id,
        start_time=start,
        end_time=end,
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

    # The client's confirmation is not sent here: the booking is `pending` and
    # only the salon can promise a slot, so that message fires from the admin
    # confirm endpoint. What has to leave now is the other direction — telling
    # the salon a stranger is waiting for an answer.
    await db.commit()
    _trigger_new_booking_alert(appt.id)

    # Rileggere invece di proiettare `appt`: la risposta ora include il nome
    # del collaboratore e quelli dei servizi, che sono relazioni non caricate
    # su questa istanza — e dopo il commit un accesso pigro sotto asyncio non
    # è una query in più, è un MissingGreenlet.
    reloaded = await db.execute(
        select(Appointment)
        .options(*appointment_detail_loads())
        .where(Appointment.id == appt.id)
    )
    return PortalAppointmentOut.from_appointment(reloaded.scalar_one())


@router.get("/appointments", response_model=List[PortalAppointmentOut])
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
        .options(*appointment_detail_loads())
        .where(Appointment.client_id == client.id)
        .order_by(Appointment.start_time.desc())
    )
    appointments = result.scalars().all()
    return [PortalAppointmentOut.from_appointment(a) for a in appointments]


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


@router.post("/waitlist", response_model=WaitlistOut, status_code=status.HTTP_201_CREATED)
async def join_waitlist(
    payload: WaitlistCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    """Cliente autenticato si iscrive alla lista d'attesa."""
    client_result = await db.execute(select(Client).where(Client.account_id == current_account.id))
    client = client_result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=400, detail="Profilo cliente non trovato")

    service = await db.get(Service, payload.service_id)
    if not service or not service.bookable_online:
        raise HTTPException(status_code=404, detail="Servizio non trovato o non prenotabile online")

    if payload.collaborator_id:
        collab = await db.get(Collaborator, payload.collaborator_id)
        if not collab or not collab.is_active:
            raise HTTPException(status_code=404, detail="Collaboratore non trovato")

    # Evita duplicati attivi per stesso cliente+servizio
    existing = await db.execute(
        select(WaitlistEntry).where(
            WaitlistEntry.client_id == client.id,
            WaitlistEntry.service_id == payload.service_id,
            WaitlistEntry.status.in_([WaitlistStatus.waiting, WaitlistStatus.notified]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Sei già in lista d'attesa per questo servizio")

    entry = WaitlistEntry(
        client_id=client.id,
        service_id=payload.service_id,
        collaborator_id=payload.collaborator_id,
        preferred_date=payload.preferred_date,
        notes=payload.notes,
        status=WaitlistStatus.waiting,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return WaitlistOut.model_validate(entry)


@router.get("/waitlist", response_model=List[WaitlistOut])
async def my_waitlist(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    """Cliente vede le proprie iscrizioni alla lista d'attesa."""
    client_result = await db.execute(select(Client).where(Client.account_id == current_account.id))
    client = client_result.scalar_one_or_none()
    if not client:
        return []

    result = await db.execute(
        select(WaitlistEntry)
        .where(WaitlistEntry.client_id == client.id)
        .order_by(WaitlistEntry.created_at.desc())
    )
    return [WaitlistOut.model_validate(e) for e in result.scalars().all()]


@router.delete("/waitlist/{entry_id}", response_model=MessageResponse)
async def leave_waitlist(
    entry_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    """Cliente rimuove la propria iscrizione dalla lista d'attesa."""
    client_result = await db.execute(select(Client).where(Client.account_id == current_account.id))
    client = client_result.scalar_one_or_none()

    result = await db.execute(
        select(WaitlistEntry).where(
            WaitlistEntry.id == entry_id,
            WaitlistEntry.client_id == (client.id if client else -1),
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Iscrizione non trovata")
    if entry.status == WaitlistStatus.fulfilled:
        raise HTTPException(status_code=400, detail="Iscrizione già soddisfatta")

    entry.status = WaitlistStatus.cancelled
    return MessageResponse(message="Rimosso dalla lista d'attesa")


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
