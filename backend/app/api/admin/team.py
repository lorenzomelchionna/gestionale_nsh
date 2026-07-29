"""
Staff logins.

Until now accounts could only be created by the seed script or by hand on the
database. This lets the admin manage them from the app, and lets anyone change
their own password without a manual intervention.

Two invariants are enforced here, because breaking either one locks the salon
out of its own management area:
  - the last active admin cannot be deactivated or demoted;
  - nobody can deactivate or demote themselves.
"""
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.client import ClientAccount
from app.models.collaborator import Collaborator
from app.models.user import User, UserRole
from app.schemas.user import (
    PasswordChange, PasswordReset, UserCreate, UserUpdate, UserWithCollaborator,
)
from app.utils.auth import hash_password, verify_password

router = APIRouter(prefix="/team", tags=["Team"])


async def _decorate(db: AsyncSession, user: User) -> UserWithCollaborator:
    """Attach the calendar profile this login belongs to, if any."""
    out = UserWithCollaborator.model_validate(user)
    collab = (await db.execute(
        select(Collaborator).where(Collaborator.user_id == user.id)
    )).scalar_one_or_none()
    if collab:
        out.collaborator_id = collab.id
        out.collaborator_name = f"{collab.first_name} {collab.last_name}".strip()
    return out


async def _count_active_admins(db: AsyncSession, excluding: Optional[int] = None) -> int:
    q = select(func.count()).select_from(User).where(
        User.role == UserRole.admin, User.is_active == True  # noqa: E712
    )
    if excluding is not None:
        q = q.where(User.id != excluding)
    return (await db.execute(q)).scalar_one()


async def _load(db: AsyncSession, user_id: int) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return user


@router.get("", response_model=List[UserWithCollaborator])
async def list_team(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return [await _decorate(db, u) for u in users]


@router.post("", response_model=UserWithCollaborator, status_code=status.HTTP_201_CREATED)
async def create_member(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    existing = (await db.execute(
        select(User).where(User.email == payload.email)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email già usata da un altro account")

    # Staff and clients sign in from the same screen, so one address cannot
    # mean two accounts — the login would have to guess which one was meant.
    portal_account = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == payload.email)
    )).scalar_one_or_none()
    if portal_account:
        raise HTTPException(
            status_code=400,
            detail="Email già usata da un account cliente del portale prenotazioni",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.flush()

    if payload.collaborator_id is not None:
        collab = (await db.execute(
            select(Collaborator).where(Collaborator.id == payload.collaborator_id)
        )).scalar_one_or_none()
        if not collab:
            raise HTTPException(status_code=400, detail="Collaboratore non trovato")
        if collab.user_id is not None and collab.user_id != user.id:
            raise HTTPException(
                status_code=400, detail="Questo collaboratore ha già un accesso collegato"
            )
        collab.user_id = user.id

    await db.flush()
    return await _decorate(db, user)


@router.put("/{user_id}", response_model=UserWithCollaborator)
async def update_member(
    user_id: int,
    payload: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    user = await _load(db, user_id)
    data = payload.model_dump(exclude_unset=True)

    if user.id == current_user.id:
        if data.get("is_active") is False:
            raise HTTPException(
                status_code=400, detail="Non puoi disattivare il tuo stesso accesso"
            )
        if data.get("role") == UserRole.collaborator:
            raise HTTPException(
                status_code=400, detail="Non puoi togliere a te stesso i permessi di admin"
            )

    # Losing the last admin would leave nobody able to manage the salon.
    losing_admin = (
        user.role == UserRole.admin
        and (data.get("is_active") is False or data.get("role") == UserRole.collaborator)
    )
    if losing_admin and await _count_active_admins(db, excluding=user.id) == 0:
        raise HTTPException(
            status_code=400, detail="Deve restare almeno un amministratore attivo"
        )

    if "email" in data and data["email"] != user.email:
        clash = (await db.execute(
            select(User).where(User.email == data["email"], User.id != user.id)
        )).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=400, detail="Email già usata da un altro account")

    for field, value in data.items():
        setattr(user, field, value)
    await db.flush()
    return await _decorate(db, user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: int,
    payload: PasswordReset,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Admin sets someone else's password, e.g. after they forget it."""
    user = await _load(db, user_id)
    user.password_hash = hash_password(payload.new_password)
    await db.flush()


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_own_password(
    payload: PasswordChange,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Any staff member changes their own password.

    Guarded by the current password so a walk-up on an unlocked screen cannot
    silently take the account over.
    """
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Password attuale non corretta")
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=400, detail="La nuova password deve essere diversa da quella attuale"
        )
    current_user.password_hash = hash_password(payload.new_password)
    await db.flush()
