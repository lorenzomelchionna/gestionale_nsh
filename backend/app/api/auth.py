"""
One door for everyone.

Staff and clients live in different tables and carry different tokens, but they
sign in from the same screen, so the resolution has to happen here rather than
by asking the person which kind of account they have.

The token this returns decides what the bearer can reach: a client token is
marked `type: client` and is rejected on staff routes by `get_current_user`.
That marking is the whole boundary — an unmarked client token would be
indistinguishable from a staff one, which is exactly the escalation this
codebase already had once.
"""
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.client import ClientAccount
from app.models.user import User
from app.schemas.common import TokenResponse
from app.schemas.user import UserLogin
from app.utils.auth import create_access_token, create_refresh_token, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])

CLIENT_TOKEN_TYPE = "client"


class SignInResponse(TokenResponse):
    """A token plus what it is, so the caller knows where to send the person."""
    audience: Literal["staff", "client"]
    role: Optional[str] = None


@router.post("/login", response_model=SignInResponse)
async def login(payload: UserLogin, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Sign in as staff or as a client, whichever the address belongs to.

    Staff is tried first. Registration refuses an address already used by staff
    (and vice versa) so the two can no longer overlap, but rows written before
    that guard existed still could, and the salon's own account has to win.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user and verify_password(payload.password, user.password_hash):
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account disabilitato"
            )
        return SignInResponse(
            access_token=create_access_token(user.id, {"role": user.role}),
            refresh_token=create_refresh_token(user.id, {"role": user.role}),
            audience="staff",
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
        )

    account_result = await db.execute(
        select(ClientAccount).where(ClientAccount.email == payload.email)
    )
    account = account_result.scalar_one_or_none()
    if account and verify_password(payload.password, account.password_hash):
        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account disabilitato"
            )
        if not account.email_verified:
            # The portal's own login refuses these; this screen has to agree, or
            # it becomes the way around email verification.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Indirizzo email non ancora verificato. Inserisci il codice che ti abbiamo inviato.",
            )
        return SignInResponse(
            # `type` is what keeps this token off the staff routes.
            access_token=create_access_token(account.id, {"type": CLIENT_TOKEN_TYPE}),
            refresh_token=create_refresh_token(account.id, {"type": CLIENT_TOKEN_TYPE}),
            audience="client",
        )

    # Deliberately identical whether the address is unknown or the password is
    # wrong, so the response cannot be used to find out who has an account.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenziali non valide"
    )
