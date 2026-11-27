"""Il file `.ics` di un appuntamento, dal pulsante «Calendario del telefono
o del computer» della mail di conferma.

Pubblico, senza login: la cliente lo apre dalla mail, magari su un telefono
dove il portale non l'ha mai aperto. Protetto dalla firma nel link
(`utils/calendario.firma`): senza quella, 404 come per un appuntamento che
non esiste, così non si scopre nemmeno quali id esistono.

Dentro solo servizio, data, ora e salone.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.appointment import Appointment, AppointmentService, AppointmentStatus
from app.utils import calendario

router = APIRouter(prefix="/calendario", tags=["Public Calendar"])

ANNULLATI = (AppointmentStatus.cancelled, AppointmentStatus.rejected)


async def _appuntamento(db: AsyncSession, appointment_id: int, f: str | None) -> Appointment:
    if not calendario.firma_valida(appointment_id, f):
        raise HTTPException(status_code=404, detail="Link non valido.")
    a = (await db.execute(
        select(Appointment)
        .options(selectinload(Appointment.appointment_services).selectinload(AppointmentService.service))
        .where(Appointment.id == appointment_id)
    )).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Link non valido.")
    if a.status in ANNULLATI:
        raise HTTPException(status_code=410, detail="Questo appuntamento è stato annullato.")
    return a


@router.get("/{appointment_id}/appuntamento.ics")
async def file_ics(
    appointment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    f: Annotated[str | None, Query(max_length=64)] = None,
):
    """Il file, `inline`: Safari su iPhone e Mac lo apre e propone
    «Aggiungi»; altrove si scarica e lo apre l'app del calendario."""
    a = await _appuntamento(db, appointment_id, f)
    return Response(
        content=calendario.file_ics(a),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="appuntamento.ics"',
            "Cache-Control": "no-store",
        },
    )
