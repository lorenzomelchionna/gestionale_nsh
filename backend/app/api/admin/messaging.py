"""Admin messaging: send custom messages to filtered subsets of clients."""
from typing import Optional, Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.client import Client
from app.models.appointment import Appointment
from app.models.product import ProductMovement, MovementType

router = APIRouter(prefix="/messaging", tags=["messaging"])


# ── Schemas ───────────────────────────────────────────────────────

FilterType = Literal["all", "product_buyers", "inactive", "birthday_month"]


class MessageFilter(BaseModel):
    type: FilterType = "all"
    product_id: Optional[int] = None       # used when type == "product_buyers"
    inactive_days: Optional[int] = None    # used when type == "inactive"
    birthday_month: Optional[int] = None   # 1-12, used when type == "birthday_month"


class SendMessageRequest(BaseModel):
    subject: str
    body: str
    filter: MessageFilter = MessageFilter()


class RecipientOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]


class PreviewResponse(BaseModel):
    count: int
    recipients: list[RecipientOut]


class SendResponse(BaseModel):
    sent: int
    skipped: int    # clients without email (stub: would use SMS/WhatsApp)
    errors: int


# ── Helpers ───────────────────────────────────────────────────────

async def _resolve_recipients(db: AsyncSession, f: MessageFilter) -> list[Client]:
    """Return the list of active clients matching the given filter."""
    base = select(Client).where(Client.is_active == True)

    if f.type == "all":
        result = await db.execute(base)
        return list(result.scalars().all())

    if f.type == "product_buyers":
        if not f.product_id:
            return []
        # Clients who have a sale movement for product_id (via appointment)
        subq = (
            select(Appointment.client_id)
            .join(ProductMovement, ProductMovement.appointment_id == Appointment.id)
            .where(
                and_(
                    ProductMovement.product_id == f.product_id,
                    ProductMovement.type == MovementType.sale,
                    Appointment.client_id.isnot(None),
                )
            )
            .distinct()
        )
        result = await db.execute(
            base.where(Client.id.in_(subq))
        )
        return list(result.scalars().all())

    if f.type == "inactive":
        days = f.inactive_days or 90
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        # Clients whose last appointment is older than cutoff (or have none)
        active_ids_subq = (
            select(Appointment.client_id)
            .where(Appointment.start_time >= cutoff)
            .distinct()
        )
        result = await db.execute(
            base.where(Client.id.not_in(active_ids_subq))
        )
        return list(result.scalars().all())

    if f.type == "birthday_month":
        month = f.birthday_month
        if not month or month < 1 or month > 12:
            return []
        result = await db.execute(
            base.where(
                and_(
                    Client.birth_date.isnot(None),
                    extract("month", Client.birth_date) == month,
                )
            )
        )
        return list(result.scalars().all())

    return []


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/preview", response_model=PreviewResponse)
async def preview_message(
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Return the list of clients who would receive this message."""
    clients = await _resolve_recipients(db, payload.filter)
    return PreviewResponse(
        count=len(clients),
        recipients=[
            RecipientOut(
                id=c.id,
                first_name=c.first_name,
                last_name=c.last_name,
                email=c.email,
                phone=c.phone,
            )
            for c in clients
        ],
    )


@router.post("/send", response_model=SendResponse)
async def send_message(
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Send a custom message to all clients matching the filter."""
    from app.utils.email import send_custom_message

    clients = await _resolve_recipients(db, payload.filter)
    sent = skipped = errors = 0

    for client in clients:
        if not client.email:
            # TODO: fallback to SMS/WhatsApp when a provider is configured
            skipped += 1
            continue
        try:
            await send_custom_message(client, payload.subject, payload.body)
            sent += 1
        except Exception as e:
            print(f"[MESSAGING] Error sending to client {client.id}: {e}")
            errors += 1

    return SendResponse(sent=sent, skipped=skipped, errors=errors)
