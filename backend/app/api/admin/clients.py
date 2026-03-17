from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.client import Client
from app.models.appointment import Appointment
from app.models.user import User
from app.schemas.client import ClientCreate, ClientUpdate, ClientOut
from app.schemas.appointment import AppointmentOutWithNames
from app.schemas.common import PaginatedResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get("", response_model=PaginatedResponse[ClientOut])
async def list_clients(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
):
    q = select(Client).where(Client.is_active == True)
    if search:
        term = f"%{search}%"
        q = q.where(
            or_(
                Client.first_name.ilike(term),
                Client.last_name.ilike(term),
                Client.phone.ilike(term),
                Client.email.ilike(term),
            )
        )

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    return PaginatedResponse(
        items=[ClientOut.model_validate(c) for c in result.scalars().all()],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size),
    )


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    client = Client(**payload.model_dump())
    db.add(client)
    await db.flush()
    await db.refresh(client)
    return ClientOut.model_validate(client)


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    return ClientOut.model_validate(client)


@router.put("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: int,
    payload: ClientUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await db.flush()
    return ClientOut.model_validate(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    client.is_active = False


@router.get("/{client_id}/appointments", response_model=List[AppointmentOutWithNames])
async def get_client_appointments(
    client_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.client),
            selectinload(Appointment.collaborator),
            selectinload(Appointment.appointment_services),
        )
        .where(Appointment.client_id == client_id)
        .order_by(Appointment.start_time.desc())
    )
    appointments = result.scalars().all()
    return [_enrich(a) for a in appointments]


def _enrich(a: Appointment) -> AppointmentOutWithNames:
    base = AppointmentOutWithNames.model_validate(a)
    base.client_name = f"{a.client.first_name} {a.client.last_name}" if a.client else ""
    base.collaborator_name = f"{a.collaborator.first_name} {a.collaborator.last_name}" if a.collaborator else ""
    base.total_price = sum(s.price_snapshot for s in a.appointment_services)
    return base
