from typing import Annotated, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.payment import Payment
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentOut
from app.schemas.common import PaginatedResponse
from app.dependencies import require_admin
from app.utils.tempo import istante_da_ingresso

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get("", response_model=PaginatedResponse[PaymentOut])
async def list_payments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    q = select(Payment)
    # Stesso confine di `admin/appointments.py`: `date_from`/`date_to`
    # arrivano da `CashPage.tsx` come mezzanotte a Roma senza fuso, e letti
    # com'sono contro `Payment.date` (un istante) finivano interpretati nel
    # fuso del processo — UTC su Railway.
    if date_from:
        q = q.where(Payment.date >= istante_da_ingresso(date_from))
    if date_to:
        q = q.where(Payment.date <= istante_da_ingresso(date_to))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(q.order_by(Payment.date.desc()).offset((page - 1) * page_size).limit(page_size))
    return PaginatedResponse(
        items=[PaymentOut.model_validate(p) for p in result.scalars().all()],
        total=total, page=page, page_size=page_size, pages=-(-total // page_size),
    )


@router.post("", response_model=PaymentOut, status_code=201)
async def create_payment(
    payload: PaymentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    payment = Payment(**payload.model_dump())
    db.add(payment)
    await db.flush()
    await db.refresh(payment)
    return PaymentOut.model_validate(payment)
