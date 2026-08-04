"""
Slot availability logic.

A "slot" = slot_duration_minutes (default 30 min) block of time.
A service with duration_slots=2 occupies 2 consecutive slots = 60 min.
"""
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.models.collaborator import Collaborator, CollaboratorSchedule
from app.models.absence import Absence
from app.models.extra_day import CollaboratorExtraDay
from app.models.appointment import Appointment, AppointmentService, AppointmentStatus
from app.models.booking_config import BookingConfig


def busy_slot_offsets(services: Sequence) -> List[int]:
    """Gli slot, contati dall'inizio dell'appuntamento, in cui il collaboratore
    è davvero occupato.

    Serve per il tempo di posa: durante la posa di una tinta la cliente è in
    salone ma il collaboratore no, quindi quello slot può ospitare qualcun
    altro. Senza questo, un colore da due ore toglie due ore di agenda anche
    se il lavoro vero è un'ora.

    I servizi di un appuntamento si susseguono, quindi si accumula uno dopo
    l'altro. Un servizio senza posa occupa tutti i suoi slot: è il caso
    normale, ed è per questo che aggiungere il campo non ha cambiato niente
    per i servizi che c'erano già.
    """
    offsets: List[int] = []
    cursor = 0
    for svc in services:
        total = svc.duration_slots or 1
        posa = getattr(svc, "processing_slots", 0) or 0
        before = getattr(svc, "slots_before_processing", 0) or 0

        if posa <= 0 or before + posa >= total:
            # Nessuna posa, o una posa che non lascerebbe lavoro dopo di sé —
            # in quel caso non è una posa, è un appuntamento più corto.
            offsets.extend(range(cursor, cursor + total))
        else:
            offsets.extend(range(cursor, cursor + before))
            offsets.extend(range(cursor + before + posa, cursor + total))
        cursor += total
    return offsets


async def get_available_slots(
    db: AsyncSession,
    collaborator_id: int,
    target_date: date,
    duration_slots: int,
    exclude_appointment_id: Optional[int] = None,
    busy_offsets: Optional[Sequence[int]] = None,
) -> List[datetime]:
    """Gli orari di inizio disponibili per una data e una durata.

    `duration_slots` è la durata totale (quanto dura per la cliente).
    `busy_offsets` dice quali di quegli slot impegnano il collaboratore: se
    non viene passato valgono tutti, cioè il comportamento di sempre.
    """

    # 1. Load booking config
    cfg_result = await db.execute(select(BookingConfig).limit(1))
    cfg = cfg_result.scalar_one_or_none()
    slot_minutes = cfg.slot_duration_minutes if cfg else 30
    min_advance_hours = cfg.min_advance_hours if cfg else 2

    # 2. Check for an extra (extraordinary) work day first
    extra_result = await db.execute(
        select(CollaboratorExtraDay).where(
            and_(
                CollaboratorExtraDay.collaborator_id == collaborator_id,
                CollaboratorExtraDay.date == target_date,
            )
        )
    )
    extra_day = extra_result.scalar_one_or_none()

    if extra_day:
        work_start_time = extra_day.start_time
        work_end_time = extra_day.end_time
    else:
        # Load collaborator schedule for that weekday (Mon=0)
        weekday = target_date.weekday()
        sched_result = await db.execute(
            select(CollaboratorSchedule).where(
                and_(
                    CollaboratorSchedule.collaborator_id == collaborator_id,
                    CollaboratorSchedule.day_of_week == weekday,
                    CollaboratorSchedule.is_working == True,
                )
            )
        )
        schedule = sched_result.scalar_one_or_none()
        if not schedule or not schedule.start_time or not schedule.end_time:
            return []  # Not working that day
        work_start_time = schedule.start_time
        work_end_time = schedule.end_time

    # 3. Assenze. `scalars().all()` e non `scalar_one_or_none()`: con i permessi
    #    a ore più assenze possono coprire lo stesso giorno (una mattina di
    #    permesso dentro una settimana di ferie), e la vecchia forma avrebbe
    #    sollevato invece di rispondere.
    absence_result = await db.execute(
        select(Absence).where(
            and_(
                Absence.collaborator_id == collaborator_id,
                Absence.start_date <= target_date,
                Absence.end_date >= target_date,
            )
        )
    )
    absences = absence_result.scalars().all()

    # Un unico insieme di minuti occupati, alimentato sia dai permessi a ore
    # sia dagli appuntamenti: per chi cerca uno slot libero le due cose sono
    # lo stesso ostacolo.
    booked_minutes: set[int] = set()
    for ab in absences:
        if ab.start_time is None or ab.end_time is None:
            return []  # Giornata intera: non resta niente da calcolare.
        cur = ab.start_time.hour * 60 + ab.start_time.minute
        fine = ab.end_time.hour * 60 + ab.end_time.minute
        while cur < fine:
            booked_minutes.add(cur)
            cur += slot_minutes

    # 4. Appuntamenti del giorno. I servizi servono per sapere quali slot
    #    impegnano davvero il collaboratore e quali sono posa.
    day_start = datetime.combine(target_date, time.min).replace(tzinfo=timezone.utc)
    day_end = datetime.combine(target_date, time.max).replace(tzinfo=timezone.utc)
    appt_result = await db.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.appointment_services)
            .selectinload(AppointmentService.service)
        )
        .where(
            and_(
                Appointment.collaborator_id == collaborator_id,
                Appointment.start_time >= day_start,
                Appointment.start_time <= day_end,
                Appointment.status.in_([
                    AppointmentStatus.confirmed,
                    AppointmentStatus.pending,
                    AppointmentStatus.rescheduled,
                ]),
                Appointment.id != exclude_appointment_id if exclude_appointment_id else True,
            )
        )
    )
    booked = appt_result.scalars().all()

    for a in booked:
        start_min = a.start_time.hour * 60 + a.start_time.minute
        end_min = a.end_time.hour * 60 + a.end_time.minute
        span_minutes = end_min - start_min

        servizi = [s.service for s in a.appointment_services if s.service is not None]
        # Il pattern descrive questo appuntamento solo se la somma dei suoi
        # servizi copre esattamente la fascia prenotata. Un appuntamento
        # allungato a mano dall'agenda, o senza servizi collegati, non
        # corrisponde più: lì si torna a occupare tutto, che è la scelta
        # prudente — meglio un buco non sfruttato che due clienti sovrapposte.
        durata_servizi = sum(s.duration_slots or 1 for s in servizi) * slot_minutes
        if servizi and durata_servizi == span_minutes:
            for off in busy_slot_offsets(servizi):
                booked_minutes.add(start_min + off * slot_minutes)
        else:
            cur = start_min
            while cur < end_min:
                booked_minutes.add(cur)
                cur += slot_minutes

    # 5. Generate all possible start slots within working hours
    work_start = work_start_time.hour * 60 + work_start_time.minute
    work_end = work_end_time.hour * 60 + work_end_time.minute
    now_utc = datetime.now(timezone.utc)
    min_advance_minutes = min_advance_hours * 60

    # Quali slot del nuovo appuntamento impegnano il collaboratore. Di default
    # tutti; con una posa, solo quelli di lavoro — così un altro appuntamento
    # può incastrarsi proprio nel buco.
    needed = list(busy_offsets) if busy_offsets is not None else list(range(duration_slots))

    available: List[datetime] = []
    slot_start = work_start
    while slot_start + duration_slots * slot_minutes <= work_end:
        all_free = all(
            (slot_start + i * slot_minutes) not in booked_minutes
            for i in needed
        )
        if all_free:
            slot_dt = datetime.combine(target_date, time(slot_start // 60, slot_start % 60), tzinfo=timezone.utc)
            # Respect min advance
            if (slot_dt - now_utc).total_seconds() / 60 >= min_advance_minutes:
                available.append(slot_dt)
        slot_start += slot_minutes

    return available
