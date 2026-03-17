from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.collaborator import Collaborator, CollaboratorSchedule, CollaboratorService
from app.models.service import Service
from app.models.user import User
from app.schemas.collaborator import (
    CollaboratorCreate, CollaboratorUpdate, CollaboratorOut,
    CollaboratorScheduleBase, CollaboratorScheduleOut,
)
from app.schemas.common import PaginatedResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/collaborators", tags=["Collaborators"])


def _build_out(collab: Collaborator) -> CollaboratorOut:
    return CollaboratorOut(
        id=collab.id,
        first_name=collab.first_name,
        last_name=collab.last_name,
        phone=collab.phone,
        email=collab.email,
        photo_url=collab.photo_url,
        is_active=collab.is_active,
        visible_online=collab.visible_online,
        color=collab.color,
        created_at=collab.created_at,
        schedules=[CollaboratorScheduleOut.model_validate(s) for s in (collab.schedules or [])],
        service_ids=[s.id for s in (collab.services or [])],
    )


@router.get("", response_model=PaginatedResponse[CollaboratorOut])
async def list_collaborators(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False),
):
    q = select(Collaborator).options(
        selectinload(Collaborator.schedules),
        selectinload(Collaborator.services),
    )
    if active_only:
        q = q.where(Collaborator.is_active == True)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    collaborators = result.scalars().all()

    return PaginatedResponse(
        items=[_build_out(c) for c in collaborators],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size),
    )


@router.post("", response_model=CollaboratorOut, status_code=status.HTTP_201_CREATED)
async def create_collaborator(
    payload: CollaboratorCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    collab = Collaborator(**payload.model_dump())
    db.add(collab)
    await db.flush()
    await db.refresh(collab, ["schedules", "services"])
    return _build_out(collab)


@router.get("/{collaborator_id}", response_model=CollaboratorOut)
async def get_collaborator(
    collaborator_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Collaborator)
        .options(selectinload(Collaborator.schedules), selectinload(Collaborator.services))
        .where(Collaborator.id == collaborator_id)
    )
    collab = result.scalar_one_or_none()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaboratore non trovato")
    return _build_out(collab)


@router.put("/{collaborator_id}", response_model=CollaboratorOut)
async def update_collaborator(
    collaborator_id: int,
    payload: CollaboratorUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Collaborator)
        .options(selectinload(Collaborator.schedules), selectinload(Collaborator.services))
        .where(Collaborator.id == collaborator_id)
    )
    collab = result.scalar_one_or_none()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaboratore non trovato")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(collab, field, value)
    await db.flush()
    return _build_out(collab)


@router.delete("/{collaborator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collaborator(
    collaborator_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Collaborator).where(Collaborator.id == collaborator_id))
    collab = result.scalar_one_or_none()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaboratore non trovato")
    collab.is_active = False  # Soft delete


@router.put("/{collaborator_id}/schedule", response_model=List[CollaboratorScheduleOut])
async def update_schedule(
    collaborator_id: int,
    schedules: List[CollaboratorScheduleBase],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Collaborator).where(Collaborator.id == collaborator_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Collaboratore non trovato")

    # Replace all schedules
    existing = await db.execute(
        select(CollaboratorSchedule).where(CollaboratorSchedule.collaborator_id == collaborator_id)
    )
    for s in existing.scalars().all():
        await db.delete(s)

    new_schedules = [
        CollaboratorSchedule(collaborator_id=collaborator_id, **s.model_dump())
        for s in schedules
    ]
    db.add_all(new_schedules)
    await db.flush()
    return [CollaboratorScheduleOut.model_validate(s) for s in new_schedules]


@router.put("/{collaborator_id}/services", response_model=CollaboratorOut)
async def update_services(
    collaborator_id: int,
    service_ids: List[int],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Collaborator)
        .options(selectinload(Collaborator.schedules), selectinload(Collaborator.services))
        .where(Collaborator.id == collaborator_id)
    )
    collab = result.scalar_one_or_none()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaboratore non trovato")

    # Replace many-to-many
    await db.execute(
        CollaboratorService.__table__.delete().where(
            CollaboratorService.collaborator_id == collaborator_id
        )
    )
    for sid in service_ids:
        db.add(CollaboratorService(collaborator_id=collaborator_id, service_id=sid))
    await db.flush()
    await db.refresh(collab, ["services"])
    return _build_out(collab)
