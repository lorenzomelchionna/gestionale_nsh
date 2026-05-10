"""Admin endpoints for the waitlist."""
from typing import Annotated, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.waitlist import WaitlistEntry, WaitlistStatus
from app.models.client import Client
from app.models.collaborator import Collaborator
from app.models.service import Service
from app.schemas.waitlist import WaitlistCreate, WaitlistOut, WaitlistOutWithNames
from app.schemas.common import MessageResponse
from app.dependencies import require_admin

router = APIRouter(prefix="/waitlist", tags=["Waitlist"])


def _enrich(entry: WaitlistEntry) -> WaitlistOutWithNames:
    out = WaitlistOutWithNames.model_validate(entry)
    if entry.client:
        out.client_name = f"{entry.client.first_name} {entry.client.last_name}"
    if entry.service:
        out.service_name = entry.service.name
    if entry.collaborator:
        out.collaborator_name = f"{entry.collaborator.first_name} {entry.collaborator.last_name}"
    return out


@router.get("", response_model=List[WaitlistOutWithNames])
async def list_waitlist(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
    status_filter: Optional[WaitlistStatus] = Query(None, alias="status"),
):
    q = (
        select(WaitlistEntry)
        .options(
            selectinload(WaitlistEntry.client),
            selectinload(WaitlistEntry.service),
            selectinload(WaitlistEntry.collaborator),
        )
        .order_by(WaitlistEntry.created_at)
    )
    if status_filter:
        q = q.where(WaitlistEntry.status == status_filter)
    result = await db.execute(q)
    entries = result.scalars().all()
    return [_enrich(e) for e in entries]


@router.post("", response_model=WaitlistOutWithNames, status_code=status.HTTP_201_CREATED)
async def create_waitlist_entry(
    payload: WaitlistCreate,
    client_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Admin aggiunge un cliente alla lista d'attesa."""
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    service = await db.get(Service, payload.service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Servizio non trovato")

    if payload.collaborator_id:
        collab = await db.get(Collaborator, payload.collaborator_id)
        if not collab:
            raise HTTPException(status_code=404, detail="Collaboratore non trovato")

    entry = WaitlistEntry(
        client_id=client_id,
        service_id=payload.service_id,
        collaborator_id=payload.collaborator_id,
        preferred_date=payload.preferred_date,
        notes=payload.notes,
        status=WaitlistStatus.waiting,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry, ["client", "service", "collaborator"])
    return _enrich(entry)


@router.post("/{entry_id}/notify", response_model=WaitlistOutWithNames)
async def notify_client(
    entry_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
):
    """Segna l'iscrizione come 'notificata' (slot disponibile comunicato al cliente)."""
    result = await db.execute(
        select(WaitlistEntry)
        .options(
            selectinload(WaitlistEntry.client),
            selectinload(WaitlistEntry.service),
            selectinload(WaitlistEntry.collaborator),
        )
        .where(WaitlistEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Iscrizione non trovata")
    if entry.status != WaitlistStatus.waiting:
        raise HTTPException(status_code=400, detail="Iscrizione non in stato 'waiting'")

    entry.status = WaitlistStatus.notified
    entry.notified_at = datetime.now(timezone.utc)
    return _enrich(entry)


@router.patch("/{entry_id}/fulfil", response_model=WaitlistOutWithNames)
async def fulfil_entry(
    entry_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
):
    """Segna l'iscrizione come soddisfatta (cliente ha prenotato)."""
    result = await db.execute(
        select(WaitlistEntry)
        .options(
            selectinload(WaitlistEntry.client),
            selectinload(WaitlistEntry.service),
            selectinload(WaitlistEntry.collaborator),
        )
        .where(WaitlistEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Iscrizione non trovata")

    entry.status = WaitlistStatus.fulfilled
    return _enrich(entry)


@router.delete("/{entry_id}", response_model=MessageResponse)
async def delete_waitlist_entry(
    entry_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
):
    result = await db.execute(select(WaitlistEntry).where(WaitlistEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Iscrizione non trovata")
    await db.delete(entry)
    return MessageResponse(message="Iscrizione rimossa")
