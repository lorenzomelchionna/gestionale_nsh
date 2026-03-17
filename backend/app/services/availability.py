"""
Slot availability logic.

A "slot" = slot_duration_minutes (default 30 min) block of time.
A service with duration_slots=2 occupies 2 consecutive slots = 60 min.
"""
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.collaborator import Collaborator, CollaboratorSchedule
from app.models.absence import Absence
from app.models.appointment import Appointment, AppointmentStatus
from app.models.booking_config import BookingConfig


async def get_available_slots(
    db: AsyncSession,
    collaborator_id: int,
    target_date: date,
    duration_slots: int,
    exclude_appointment_id: Optional[int] = None,
) -> List[datetime]:
    """Return list of available start datetimes for a given date and duration."""

    # 1. Load booking config
    cfg_result = await db.execute(select(BookingConfig).limit(1))
    cfg = cfg_result.scalar_one_or_none()
    slot_minutes = cfg.slot_duration_minutes if cfg else 30
    min_advance_hours = cfg.min_advance_hours if cfg else 2

    # 2. Load collaborator schedule for that weekday (Mon=0)
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

    # 3. Check absences
    absence_result = await db.execute(
        select(Absence).where(
            and_(
                Absence.collaborator_id == collaborator_id,
                Absence.start_date <= target_date,
                Absence.end_date >= target_date,
            )
        )
    )
    if absence_result.scalar_one_or_none():
        return []  # On leave

    # 4. Load confirmed appointments for that day
    day_start = datetime.combine(target_date, time.min).replace(tzinfo=timezone.utc)
    day_end = datetime.combine(target_date, time.max).replace(tzinfo=timezone.utc)
    appt_result = await db.execute(
        select(Appointment).where(
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

    # Build set of booked slot starts (as minutes from midnight)
    booked_minutes: set[int] = set()
    for a in booked:
        start_min = a.start_time.hour * 60 + a.start_time.minute
        end_min = a.end_time.hour * 60 + a.end_time.minute
        cur = start_min
        while cur < end_min:
            booked_minutes.add(cur)
            cur += slot_minutes

    # 5. Generate all possible start slots within working hours
    work_start = schedule.start_time.hour * 60 + schedule.start_time.minute
    work_end = schedule.end_time.hour * 60 + schedule.end_time.minute
    now_utc = datetime.now(timezone.utc)
    min_advance_minutes = min_advance_hours * 60

    available: List[datetime] = []
    slot_start = work_start
    while slot_start + duration_slots * slot_minutes <= work_end:
        # Check all required consecutive slots are free
        all_free = all(
            (slot_start + i * slot_minutes) not in booked_minutes
            for i in range(duration_slots)
        )
        if all_free:
            slot_dt = datetime.combine(target_date, time(slot_start // 60, slot_start % 60), tzinfo=timezone.utc)
            # Respect min advance
            if (slot_dt - now_utc).total_seconds() / 60 >= min_advance_minutes:
                available.append(slot_dt)
        slot_start += slot_minutes

    return available
