from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.booking_config import BookingConfig
from app.models.user import User
from app.schemas.booking_config import BookingConfigUpdate, BookingConfigOut
from app.dependencies import get_current_user

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/booking", response_model=BookingConfigOut)
async def get_booking_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(BookingConfig).limit(1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = BookingConfig()
        db.add(cfg)
        await db.flush()
        await db.refresh(cfg)
    return BookingConfigOut.model_validate(cfg)


@router.put("/booking", response_model=BookingConfigOut)
async def update_booking_config(
    payload: BookingConfigUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(BookingConfig).limit(1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = BookingConfig()
        db.add(cfg)
        await db.flush()

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(cfg, field, value)
    await db.flush()
    return BookingConfigOut.model_validate(cfg)
