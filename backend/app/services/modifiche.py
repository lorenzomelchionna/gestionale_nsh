"""Le richieste di modifica di un appuntamento confermato, fatte dalla cliente.

Richiesta del 2026-10-13, con le decisioni di Lorenzo: la cliente può cambiare
tutto — servizi, collaboratore, giorno e ora — ma è una **richiesta**. Finché
il salone non accetta, l'appuntamento confermato resta valido: se il salone
dice di no, la cliente non perde il posto che aveva.

La richiesta è un appuntamento a sé, «in attesa», che punta a quello che
sostituirebbe (`replaces_appointment_id`). Così passa da tutto quello che
esiste già per le richieste online: la pagina «In attesa», conferma, rifiuto,
proposta di un orario alternativo, il messaggio di conferma alla cliente.
Questo modulo tiene insieme i due capi:

- quando la richiesta diventa confermata, l'originale si annulla — nella
  stessa transazione, così non esistono mai due appuntamenti confermati per
  la stessa modifica né nessuno;
- quando l'originale finisce (annullato dalla cliente o dal salone), le sue
  richieste ancora aperte si annullano con lui: una modifica di un
  appuntamento che non c'è più non va approvata per sbaglio.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.booking_config import BookingConfig

APERTE = (AppointmentStatus.pending, AppointmentStatus.rescheduled)
FINITI = (AppointmentStatus.completed, AppointmentStatus.cancelled, AppointmentStatus.rejected)


async def scadenza_modifiche(db: AsyncSession, appt: Appointment) -> Optional[datetime]:
    """Fin quando la cliente può modificare o annullare da sola.

    Lo stesso preavviso che valeva già per annullare (`min_cancel_hours`,
    «preavviso minimo per cancellare» nelle impostazioni): sotto, telefona al
    salone. `None` se non c'è configurazione, cioè nessun limite.
    """
    cfg = (await db.execute(select(BookingConfig).limit(1))).scalar_one_or_none()
    if cfg is None:
        return None
    return appt.start_time - timedelta(hours=cfg.min_cancel_hours)


async def controlla_preavviso(db: AsyncSession, appt: Appointment, azione: str) -> None:
    limite = await scadenza_modifiche(db, appt)
    if limite is not None and datetime.now(timezone.utc) > limite:
        cfg = (await db.execute(select(BookingConfig).limit(1))).scalar_one()
        raise HTTPException(
            status_code=400,
            detail=(
                f"{azione} non consentita con meno di {cfg.min_cancel_hours}h di preavviso: "
                "chiama il salone."
            ),
        )


async def richieste_aperte(db: AsyncSession, originale_id: int) -> list[Appointment]:
    return list((await db.execute(
        select(Appointment).where(
            Appointment.replaces_appointment_id == originale_id,
            Appointment.status.in_(APERTE),
        )
    )).scalars())


async def annulla_richieste_aperte(db: AsyncSession, originale: Appointment) -> list[Appointment]:
    """Chiude le modifiche ancora in attesa di un appuntamento che finisce."""
    chiuse = await richieste_aperte(db, originale.id)
    for r in chiuse:
        r.status = AppointmentStatus.cancelled
        r.alternative_time = None
        r.rejection_reason = "L'appuntamento da modificare è stato annullato."
    return chiuse


async def applica_sostituzione(db: AsyncSession, nuovo: Appointment) -> Optional[Appointment]:
    """Al momento in cui una richiesta di modifica diventa confermata.

    L'originale si annulla; se nel frattempo è finito — concluso, annullato,
    rifiutato — la modifica non ha più niente da sostituire e non si conferma:
    meglio un 409 che un appuntamento nuovo nato da una visita già fatta.
    Riga bloccata: due conferme insieme non devono trovarla entrambe attiva.
    """
    if nuovo.replaces_appointment_id is None:
        return None
    originale = (await db.execute(
        select(Appointment)
        .where(Appointment.id == nuovo.replaces_appointment_id)
        .with_for_update()
    )).scalar_one_or_none()
    if originale is None or originale.status in FINITI:
        raise HTTPException(
            status_code=409,
            detail="L'appuntamento da modificare non è più attivo: questa modifica non si può confermare.",
        )
    originale.status = AppointmentStatus.cancelled
    originale.alternative_time = None
    originale.rejection_reason = "Spostato: sostituito dalla modifica confermata."
    return originale
