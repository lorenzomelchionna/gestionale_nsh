import logging
from typing import Annotated
from fastapi import Request, APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.audit import (
    LOGIN_BLOCCATO, TOKEN_RIFIUTATO, evento, login_fallito, login_riuscito,
)
from app.database import get_db
from app.logging_config import maschera_email
from app.rate_limit import limiter
from app.models.user import User
from app.schemas.user import UserLogin, UserOut
from app.schemas.common import TokenResponse, MessageResponse
from app.utils.auth import verify_password, create_access_token, create_refresh_token, decode_token
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request, payload: UserLogin, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not await verify_password(payload.password, user.password_hash):
        login_fallito(
            email=payload.email,
            motivo="password_errata" if user else "account_inesistente",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenziali non valide")
    if not user.is_active:
        evento(
            LOGIN_BLOCCATO, tipo="staff", id_account=user.id,
            email=maschera_email(user.email), motivo="account_disattivato",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabilitato")

    login_riuscito(tipo="staff", id_account=user.id, email=user.email)
    access = create_access_token(user.id, {"role": user.role})
    refresh = create_refresh_token(user.id, {"role": user.role})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: dict, db: Annotated[AsyncSession, Depends(get_db)]):
    token = payload.get("refresh_token", "")
    data = decode_token(token)
    if not data or not data.get("refresh"):
        evento(TOKEN_RIFIUTATO, motivo="refresh_non_valido", punto="scambio_refresh")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token non valido")
    # A client refresh token carries an id from client_accounts; without this
    # check it would be exchanged here for a genuine staff access token.
    if data.get("type") == "client":
        # Un refresh cliente scambiato qui darebbe un access token *staff*
        # buono: è la stessa escalation di sempre, con un giro in più. Se
        # compare nei log non è un incidente, è un tentativo.
        evento(
            TOKEN_RIFIUTATO, logging.WARNING,
            motivo="refresh_cliente_su_scambio_staff", punto="scambio_refresh",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token non valido")

    result = await db.execute(select(User).where(User.id == int(data["sub"])))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        evento(TOKEN_RIFIUTATO, motivo="utente_assente_o_disattivato", punto="scambio_refresh")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utente non trovato")

    access = create_access_token(user.id, {"role": user.role})
    refresh = create_refresh_token(user.id, {"role": user.role})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.get("/me", response_model=UserOut)
async def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
