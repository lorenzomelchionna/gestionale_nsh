"""Client-facing booking portal endpoints."""
from typing import Annotated, List, Optional
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPAuthorizationCredentials
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
from app.dependencies import bearer_facoltativo, get_current_client, get_client_facoltativo
from app.services import modifiche
from app.utils.tempo import istante, oggi_salone
from app.services.availability import CHIUSURA_PORTALE, busy_slot_offsets, get_available_slots

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


async def _cliente_del_portale(db: AsyncSession, account: ClientAccount) -> Client | None:
    """La scheda cliente dietro un account del portale già autenticato.

    `Client.is_active == True` non è ridondante col controllo che
    `get_current_client` fa già su `ClientAccount.is_active`: sono due
    interruttori diversi. «Elimina cliente» dal pannello admin spegne solo
    questo — l'account resta attivo, il login resta valido — perché è così
    che il salone segnala «questa persona non è più cliente» senza toccare
    l'accesso, pensato per gli altri motivi per cui un account si disattiva.
    Senza questo controllo, ogni endpoint del portale che passa da qui
    tratterebbe una scheda disattivata come se non lo fosse: prenotare,
    cancellare, iscriversi alla lista d'attesa, tutto ancora aperto a chi il
    salone ha già tolto di mezzo.
    """
    result = await db.execute(
        select(Client).where(
            Client.account_id == account.id,
            Client.is_active == True,  # noqa: E712 — confronto SQL, non booleano Python
        )
    )
    return result.scalar_one_or_none()


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


def _trigger_change_alert(appointment_id: int):
    """Come l'avviso di una prenotazione nuova, per una richiesta di modifica."""
    try:
        from app.tasks.reminders import notify_change_request
        notify_change_request.delay(appointment_id)
    except Exception as e:
        print(f"[NOTIFY] Could not queue change alert for appointment {appointment_id}: {e}")


def _trigger_cancellation_alert(appointment_id: int, tipo: str):
    """Avvisa il salone che la cliente ha annullato (o ritirato una richiesta).

    Prima del 2026-10-13 l'annullamento dal portale non avvisava nessuno: l'ora
    si liberava in calendario e basta, e il salone se ne accorgeva vedendola
    vuota.
    """
    try:
        from app.tasks.reminders import notify_client_cancellation
        notify_client_cancellation.delay(appointment_id, tipo)
    except Exception as e:
        print(f"[NOTIFY] Could not queue cancellation alert for appointment {appointment_id}: {e}")


async def _da_sostituire(
    db: AsyncSession, credenziali, appointment_id: Optional[int],
) -> Optional[int]:
    """L'appuntamento da non contare come occupato, mentre la cliente lo sposta.

    Senza, chi ha le 10:00 con Marco non potrebbe spostarsi alle 10:30 con
    Marco: il suo stesso appuntamento risulterebbe d'intralcio. Ma gli orari
    liberi sono pubblici, e «togli l'appuntamento #N dal conto» detto da
    chiunque descriverebbe l'agenda del salone a chi prova i numeri: vale solo
    con la sessione della cliente a cui appartiene. Senza sessione valida è un
    401 — che il portale rinnova da solo — non un'esclusione ignorata in
    silenzio.
    """
    if appointment_id is None:
        return None
    account = await get_client_facoltativo(credenziali, db, obbligatorio=True)
    client = await _cliente_del_portale(db, account)
    appt = (await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.client_id == (client.id if client else -1),
            Appointment.status == AppointmentStatus.confirmed,
        )
    )).scalar_one_or_none()
    if appt is None:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")
    return appt.id


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
        .order_by(Collaborator.position, Collaborator.id)
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


async def _servizi_richiesti(
    db: AsyncSession, service_id: Optional[int], service_ids: Optional[List[int]]
) -> List[Service]:
    """The services to compute availability for, in the order given.

    `service_ids` for several services in one appointment; `service_id` for
    one, the older form, still accepted from pages already open in browsers.
    Order is not cosmetic: services run one after the other and their
    processing time depends on which comes first, so this must be the order
    the booking will receive — `book_appointment` loads them the same way.
    """
    ids = service_ids or ([service_id] if service_id is not None else [])
    if not ids:
        raise HTTPException(status_code=422, detail="Indica almeno un servizio")
    trovati = {
        s.id: s
        for s in (await db.execute(select(Service).where(Service.id.in_(ids)))).scalars()
    }
    servizi = []
    for sid in ids:
        s = trovati.get(sid)
        if not s or not s.bookable_online:
            raise HTTPException(
                status_code=404, detail="Servizio non trovato o non prenotabile online"
            )
        servizi.append(s)
    return servizi


@router.get("/availability", response_model=List[str])
async def public_availability(
    db: Annotated[AsyncSession, Depends(get_db)],
    collaborator_id: int = Query(...),
    target_date: date = Query(...),
    service_id: Optional[int] = Query(None),
    service_ids: Optional[List[int]] = Query(None),
    sostituisce: Optional[int] = Query(None),
    credenziali: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_facoltativo)] = None,
):
    # Validate booking config
    cfg_result = await db.execute(select(BookingConfig).limit(1))
    cfg = cfg_result.scalar_one_or_none()
    if cfg and not cfg.is_enabled:
        raise HTTPException(status_code=403, detail="Prenotazione online disabilitata")

    # Validate max advance
    if cfg:
        max_date = oggi_salone() + timedelta(days=cfg.max_advance_days)
        if target_date > max_date:
            raise HTTPException(status_code=400, detail="Data troppo lontana nel futuro")

    services = await _servizi_richiesti(db, service_id, service_ids)
    await _bookable_collaborator(db, collaborator_id, [s.id for s in services])

    escluso = await _da_sostituire(db, credenziali, sostituisce)
    slots = await get_available_slots(
        db, collaborator_id, target_date, sum(s.duration_slots for s in services),
        exclude_appointment_id=escluso,
        busy_offsets=busy_slot_offsets(services), chiusura=CHIUSURA_PORTALE,
    )
    return [s.isoformat() for s in slots]


@router.get("/availability/calendar", response_model=List[DayAvailability])
async def public_availability_calendar(
    db: Annotated[AsyncSession, Depends(get_db)],
    collaborator_id: int = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    service_id: Optional[int] = Query(None),
    service_ids: Optional[List[int]] = Query(None),
    sostituisce: Optional[int] = Query(None),
    credenziali: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_facoltativo)] = None,
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

    services = await _servizi_richiesti(db, service_id, service_ids)
    await _bookable_collaborator(db, collaborator_id, [s.id for s in services])
    durata = sum(s.duration_slots for s in services)
    posa = busy_slot_offsets(services)
    escluso = await _da_sostituire(db, credenziali, sostituisce)

    # La data del salone: `date.today()` è quella del processo, che su
    # Railway è UTC, quindi fra mezzanotte e le due risponderebbe «ieri».
    today = oggi_salone()
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
                db, collaborator_id, day, durata, busy_offsets=posa,
                chiusura=CHIUSURA_PORTALE, exclude_appointment_id=escluso,
            )
            out.append(DayAvailability(date=day, slots=len(slots)))
        day += timedelta(days=1)
    return out


# ── Authenticated client endpoints ────────────────────────────────

async def valida_prenotazione(
    db: AsyncSession,
    collaborator_id: int,
    start_time: datetime,
    service_ids: List[int],
    exclude_appointment_id: Optional[int] = None,
) -> tuple[list[Service], datetime, datetime]:
    """Tutto quello che una prenotazione dal portale deve rispettare, prima di
    sapere chi la fa: servizi, collaboratore, orario libero.

    Separata dalla scrittura perché chi prenota senza account ha un codice da
    spendere, e il codice si spende solo se l'orario regge: altrimenti un
    orario appena preso da un'altra cliente brucerebbe anche il codice, e
    toccherebbe chiederne un altro per scegliere l'orario successivo.

    Restituisce i servizi, l'inizio in UTC e la fine calcolata qui.
    """
    # Validate booking config
    cfg_result = await db.execute(select(BookingConfig).limit(1))
    cfg = cfg_result.scalar_one_or_none()
    if cfg and not cfg.is_enabled:
        raise HTTPException(status_code=403, detail="Prenotazione online disabilitata")

    # Validate services
    services = []
    for sid in service_ids:
        r = await db.execute(select(Service).where(Service.id == sid))
        svc = r.scalar_one_or_none()
        if not svc or not svc.bookable_online:
            raise HTTPException(status_code=400, detail=f"Servizio {sid} non prenotabile online")
        services.append(svc)

    await _bookable_collaborator(db, collaborator_id, service_ids)

    # The times are the one part of the payload the browser computes for itself,
    # so until here nothing had ever checked them. Without this block a client
    # could book outside working hours, in the past, on top of someone else, or
    # 00:00–23:59 on every collaborator for the next two months — and since a
    # `pending` request already holds its slot, that last one empties the whole
    # public calendar until the salon deletes the rows by hand.
    start = start_time
    # Un valore senza fuso è l'ora di orologio di chi l'ha scritto, e chi
    # scrive qui è il salone: va letto come ora del salone, non come UTC.
    # Leggerlo come UTC lo spostava una o due ore avanti, e il confronto con
    # gli slot più sotto lo rifiutava senza dire perché.
    start = (
        istante(start.date(), start.time()) if start.tzinfo is None
        else start.astimezone(timezone.utc)
    )

    if cfg:
        max_date = oggi_salone() + timedelta(days=cfg.max_advance_days)
        if start.date() > max_date:
            raise HTTPException(status_code=400, detail="Data troppo lontana nel futuro")

    # Same figure the availability endpoints use, summed because a booking may
    # carry several services ("taglio + barba" is two blocks, not one).
    duration_slots = sum(svc.duration_slots for svc in services)
    # Lo stesso tetto delle 19 dell'elenco degli orari: altrimenti la fascia
    # che il portale non mostra resterebbe prenotabile con una chiamata a mano.
    slots = await get_available_slots(
        db, collaborator_id, start.date(), duration_slots,
        exclude_appointment_id=exclude_appointment_id,
        busy_offsets=busy_slot_offsets(services), chiusura=CHIUSURA_PORTALE,
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
    return services, start, end


async def controlla_richieste_in_attesa(db: AsyncSession, client: Client) -> None:
    """Il tetto alle richieste ancora senza risposta, per scheda."""
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


async def registra_prenotazione(
    db: AsyncSession,
    client: Client,
    collaborator_id: int,
    services: list[Service],
    start: datetime,
    end: datetime,
    notes: Optional[str],
    sostituisce: Optional[Appointment] = None,
) -> PortalAppointmentOut:
    """Scrive la richiesta già validata, avvisa il salone, la restituisce.

    Con `sostituisce` è una richiesta di modifica di quell'appuntamento: stessa
    richiesta «in attesa», avviso diverso al salone.
    """
    appt = Appointment(
        replaces_appointment_id=sostituisce.id if sostituisce else None,
        client_id=client.id,
        collaborator_id=collaborator_id,
        start_time=start,
        end_time=end,
        notes=notes,
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
    if sostituisce is not None:
        _trigger_change_alert(appt.id)
    else:
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


@router.post("/appointments", response_model=PortalAppointmentOut, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    payload: AppointmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    client = await _cliente_del_portale(db, current_account)
    if not client:
        raise HTTPException(status_code=400, detail="Profilo cliente non trovato")

    services, start, end = await valida_prenotazione(
        db, payload.collaborator_id, payload.start_time, payload.service_ids,
    )
    await controlla_richieste_in_attesa(db, client)
    return await registra_prenotazione(
        db, client, payload.collaborator_id, services, start, end, payload.notes,
    )


@router.get("/appointments", response_model=List[PortalAppointmentOut])
async def my_appointments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    client = await _cliente_del_portale(db, current_account)
    if not client:
        return []

    result = await db.execute(
        select(Appointment)
        .options(*appointment_detail_loads())
        .where(Appointment.client_id == client.id)
        .order_by(Appointment.start_time.desc())
    )
    appointments = result.scalars().all()
    out = []
    for a in appointments:
        p = PortalAppointmentOut.from_appointment(a)
        p.change_deadline = await modifiche.scadenza_modifiche(db, a)
        out.append(p)
    return out


@router.post(
    "/appointments/{appointment_id}/change",
    response_model=PortalAppointmentOut, status_code=status.HTTP_201_CREATED,
)
async def request_change(
    appointment_id: int,
    payload: AppointmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    """Chiede di modificare un appuntamento confermato: servizi, collaboratore,
    giorno, ora — anche tutto insieme.

    È una richiesta «in attesa» come una prenotazione nuova, e l'originale
    resta confermato finché il salone non accetta (vedi `services/modifiche`).
    Stesso preavviso dell'annullamento. Una sola modifica aperta per
    appuntamento: due richieste parallele sullo stesso posto, accettate
    entrambe, lascerebbero la cliente con due appuntamenti.
    """
    client = await _cliente_del_portale(db, current_account)
    if not client:
        raise HTTPException(status_code=400, detail="Profilo cliente non trovato")
    # Bloccato: due richieste insieme non devono vedere entrambe «nessuna
    # modifica aperta».
    vecchio = (await db.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id, Appointment.client_id == client.id)
        .with_for_update()
    )).scalar_one_or_none()
    if vecchio is None:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")
    if vecchio.status != AppointmentStatus.confirmed:
        raise HTTPException(status_code=400, detail="Si può modificare solo un appuntamento confermato")
    await modifiche.controlla_preavviso(db, vecchio, "Modifica")
    if await modifiche.richieste_aperte(db, vecchio.id):
        raise HTTPException(
            status_code=409,
            detail=(
                "Hai già chiesto di modificare questo appuntamento: aspetta la risposta "
                "del salone, oppure ritira la richiesta."
            ),
        )

    services, start, end = await valida_prenotazione(
        db, payload.collaborator_id, payload.start_time, payload.service_ids,
        exclude_appointment_id=vecchio.id,
    )
    vecchi_servizi = [s.service_id for s in (await db.execute(
        select(AppointmentService)
        .where(AppointmentService.appointment_id == vecchio.id)
        .order_by(AppointmentService.id)
    )).scalars()]
    if (
        start == vecchio.start_time and payload.collaborator_id == vecchio.collaborator_id
        and [s.id for s in services] == vecchi_servizi
    ):
        raise HTTPException(status_code=400, detail="La modifica è uguale all'appuntamento attuale")
    await controlla_richieste_in_attesa(db, client)
    return await registra_prenotazione(
        db, client, payload.collaborator_id, services, start, end, payload.notes,
        sostituisce=vecchio,
    )


@router.post("/appointments/{appointment_id}/cancel", response_model=MessageResponse)
async def cancel_my_appointment(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    client = await _cliente_del_portale(db, current_account)

    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.client_id == (client.id if client else -1),
        )
    )
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")

    if appt.status in modifiche.FINITI:
        raise HTTPException(status_code=400, detail="Impossibile cancellare questo appuntamento")

    await modifiche.controlla_preavviso(db, appt, "Cancellazione")

    # Deciso prima di cambiare lo stato: dopo, sono tutti «annullati».
    tipo = (
        "modifica" if appt.replaces_appointment_id
        else "confermato" if appt.status == AppointmentStatus.confirmed
        else "richiesta"
    )
    appt.status = AppointmentStatus.cancelled
    appt.alternative_time = None
    # Annullato l'appuntamento, le sue modifiche in attesa non hanno più
    # niente da sostituire.
    await modifiche.annulla_richieste_aperte(db, appt)
    # Prima il commit, poi l'avviso: il worker legge dalla sua transazione.
    await db.commit()
    _trigger_cancellation_alert(appt.id, tipo)
    return MessageResponse(message="Appuntamento cancellato")


@router.post("/appointments/{appointment_id}/accept-alternative", response_model=MessageResponse)
async def accept_alternative(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    client = await _cliente_del_portale(db, current_account)
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.client_id == (client.id if client else -1),
        )
    )
    appt = result.scalar_one_or_none()
    if not appt or appt.status != AppointmentStatus.rescheduled:
        raise HTTPException(status_code=400, detail="Nessuna proposta alternativa attiva")

    # La durata va letta *prima* di spostare `start_time`: calcolarla dopo
    # (fine vecchia − inizio nuovo) riportava sempre alla vecchia fine,
    # qualunque fosse il nuovo inizio — un'ora alle 12 spostata alle 15
    # finiva comunque alle 13, cioè con durata negativa.
    duration = appt.end_time - appt.start_time
    appt.start_time = appt.alternative_time
    appt.end_time = appt.alternative_time + duration
    appt.alternative_time = None
    appt.status = AppointmentStatus.confirmed
    # Una modifica a cui il salone ha proposto un altro orario: accettandolo,
    # la modifica è confermata e l'originale va annullato come per la conferma.
    await modifiche.applica_sostituzione(db, appt)
    return MessageResponse(message="Proposta accettata")


@router.post("/waitlist", response_model=WaitlistOut, status_code=status.HTTP_201_CREATED)
async def join_waitlist(
    payload: WaitlistCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_account: Annotated[ClientAccount, Depends(get_current_client)],
):
    """Cliente autenticato si iscrive alla lista d'attesa."""
    client = await _cliente_del_portale(db, current_account)
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
    client = await _cliente_del_portale(db, current_account)
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
    client = await _cliente_del_portale(db, current_account)

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
    client = await _cliente_del_portale(db, current_account)
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
