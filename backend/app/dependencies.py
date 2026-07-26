from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User, UserRole
from app.models.client import ClientAccount
from app.utils.auth import decode_token

bearer_scheme = HTTPBearer()

# Staff and client tokens are signed with the same key, and `sub` is an id from
# a different table in each case (users vs client_accounts). Without checking
# which audience a token was minted for, a client token whose account id happens
# to match a staff user id authenticates as that user — so every dependency
# below must assert the audience, not just the signature.
CLIENT_TOKEN_TYPE = "client"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None or payload.get("sub") is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
    # Reject client tokens: their `sub` indexes client_accounts, not users.
    if payload.get("type") == CLIENT_TOKEN_TYPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
    # Refresh tokens may only be exchanged at /auth/refresh, never used as access.
    if payload.get("refresh"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")

    user_id: int = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utente non trovato")
    return user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accesso riservato agli admin")
    return current_user


async def get_current_client(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientAccount:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None or payload.get("sub") is None or payload.get("type") != CLIENT_TOKEN_TYPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
    if payload.get("refresh"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")

    account_id: int = int(payload["sub"])
    result = await db.execute(select(ClientAccount).where(ClientAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None or not account.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account non trovato")
    return account
