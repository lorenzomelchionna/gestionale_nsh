"""Prenotare dal portale senza account.

Nome, cognome, numero e un codice WhatsApp: le stesse cose che il salone
chiede a chi prenota al telefono, più la prova che il numero è suo. Nessuna
password, nessuna email, nessuna sessione — ogni prenotazione porta il suo
codice, e il codice vale una prenotazione sola.

Senza account non c'è un'area personale: per disdire o spostare si contatta
il salone, come per chi prenota a voce. Chi si registra più tardi con lo
stesso nome e lo stesso numero ritrova queste prenotazioni nel suo account —
vedi `_collega_per_telefono` in `auth.py`.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public.booking import (
    controlla_richieste_in_attesa, registra_prenotazione, valida_prenotazione,
)
from app.database import get_db
from app.logging_config import maschera_telefono
from app.models.booking_config import BookingConfig
from app.models.client import Client
from app.rate_limit import limiter
from app.schemas.appointment import PortalAppointmentOut
from app.schemas.guest import GuestBooking, GuestCodeRequest, GuestCodeSent, GuestIdentity
from app.services import guest_verification
from app.services.chat import collega_conversazione
from app.utils.nomi import chiave_nome
from app.utils.whatsapp import send_verification_code_whatsapp

router = APIRouter(prefix="/guest", tags=["Public Booking"])

log = logging.getLogger("nsh.portale")


async def _scheda_per(db: AsyncSession, chi: GuestIdentity) -> Client:
    """La scheda su cui far cadere la prenotazione, creata se non c'è.

    Il numero è già stato dimostrato col codice, quindi cercare per numero è
    sicuro. Il nome serve lo stesso: madre e figlia col fisso di casa hanno
    lo stesso numero e due schede, e la prenotazione della figlia non deve
    finire nello storico della madre.

    Fra più schede che combaciano vince quella con un account — è la persona
    che si è registrata, e così la prenotazione compare nella sua area —
    poi la più vecchia, che è quella con lo storico.
    """
    chiave = chiave_nome(chi.first_name, chi.last_name)
    stesso_numero = (await db.execute(
        select(Client).where(
            Client.phone == chi.phone,
            Client.is_active == True,  # noqa: E712 — confronto SQL
        )
    )).scalars().all()
    sue = [c for c in stesso_numero if chiave_nome(c.first_name, c.last_name) == chiave]
    if sue:
        return min(sue, key=lambda c: (c.account_id is None, c.id))

    scheda = Client(first_name=chi.first_name, last_name=chi.last_name, phone=chi.phone)
    db.add(scheda)
    await db.flush()
    await collega_conversazione(db, scheda)
    log.info("scheda creata da prenotazione senza account", extra={"id_scheda": scheda.id})
    return scheda


async def _prenotazioni_aperte(db: AsyncSession) -> None:
    cfg = (await db.execute(select(BookingConfig).limit(1))).scalar_one_or_none()
    if cfg and not cfg.is_enabled:
        raise HTTPException(status_code=403, detail="Prenotazione online disabilitata")


@router.post("/code", response_model=GuestCodeSent)
@limiter.limit("5/hour")
async def request_code(
    request: Request, payload: GuestCodeRequest, db: Annotated[AsyncSession, Depends(get_db)]
):
    """Manda su WhatsApp il codice che la prenotazione chiederà."""
    # Con le prenotazioni chiuse un codice non serve a niente, e costa un
    # messaggio.
    await _prenotazioni_aperte(db)

    try:
        code = await guest_verification.issue_code(db, payload.phone)
    except guest_verification.CodeRefused as e:
        raise HTTPException(status_code=429, detail=e.detail)
    # Salvato prima di partire: un codice arrivato sul telefono ma perso da un
    # commit fallito dopo sarebbe un codice che non funziona mai.
    await db.commit()

    try:
        await send_verification_code_whatsapp(payload.phone, code)
    except Exception:
        log.exception(
            "invio del codice per prenotazione senza account fallito",
            extra={"telefono": maschera_telefono(payload.phone)},
        )
        return GuestCodeSent(whatsapp_sent=False)
    return GuestCodeSent(whatsapp_sent=True)


@router.post("/appointments", response_model=PortalAppointmentOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def book_as_guest(
    request: Request, payload: GuestBooking, db: Annotated[AsyncSession, Depends(get_db)]
):
    # Prima l'orario, poi il codice: un orario appena preso da un'altra non
    # deve costare il codice, che resta buono per scegliere il successivo.
    services, start, end = await valida_prenotazione(
        db, payload.collaborator_id, payload.start_time, payload.service_ids,
    )

    try:
        await guest_verification.check_code(db, payload.phone, payload.code)
    except guest_verification.VerificationError as e:
        # Committed, not flushed: get_db rolls back on any exception, so the
        # attempt would be undone by the raise below and every guess free.
        await db.commit()
        log.warning(
            "codice di prenotazione senza account rifiutato",
            extra={"telefono": maschera_telefono(payload.phone)},
        )
        raise HTTPException(status_code=400, detail=e.detail)

    # Da qui in poi un errore annulla tutto, codice compreso: una richiesta
    # rifiutata per troppe prenotazioni in attesa non deve bruciarlo.
    client = await _scheda_per(db, payload)
    await controlla_richieste_in_attesa(db, client)
    return await registra_prenotazione(
        db, client, payload.collaborator_id, services, start, end, payload.notes,
    )
