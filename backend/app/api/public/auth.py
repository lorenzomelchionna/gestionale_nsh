from typing import Annotated
from datetime import datetime, timedelta, timezone
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models.client import Client, ClientAccount
from app.schemas.client import ClientRegister, ClientLoginRequest, PasswordResetRequest, PasswordReset
from app.schemas.common import TokenResponse, MessageResponse
from app.utils.auth import hash_password, verify_password, create_access_token, create_refresh_token

router = APIRouter(prefix="/auth", tags=["Client Auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: ClientRegister, db: Annotated[AsyncSession, Depends(get_db)]):
    # Check email not already used
    existing = await db.execute(select(ClientAccount).where(ClientAccount.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email già registrata")

    # Try to link to existing client (match phone or email)
    client_result = await db.execute(
        select(Client).where(
            or_(
                Client.phone == payload.phone,
                Client.email == payload.email,
            )
        ).limit(1)
    )
    client = client_result.scalar_one_or_none()

    # Create account
    account = ClientAccount(
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(account)
    await db.flush()

    if client:
        # Link existing client to this account
        client.account_id = account.id
        if not client.email:
            client.email = payload.email
    else:
        # Create new client record
        client = Client(
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            email=payload.email,
            account_id=account.id,
        )
        db.add(client)

    await db.flush()

    access = create_access_token(account.id, {"type": "client"})
    refresh = create_refresh_token(account.id, {"type": "client"})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenResponse)
async def login(payload: ClientLoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(ClientAccount).where(ClientAccount.email == payload.email))
    account = result.scalar_one_or_none()
    if not account or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not account.is_active:
        raise HTTPException(status_code=403, detail="Account disabilitato")

    access = create_access_token(account.id, {"type": "client"})
    refresh = create_refresh_token(account.id, {"type": "client"})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: PasswordResetRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(ClientAccount).where(ClientAccount.email == payload.email))
    account = result.scalar_one_or_none()
    if account:
        token = secrets.token_urlsafe(32)
        account.reset_token = token
        account.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=2)
        await db.flush()
        # TODO: send email with token
    return MessageResponse(message="Se l'email è registrata, riceverai le istruzioni per il reset")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: PasswordReset, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(ClientAccount).where(ClientAccount.reset_token == payload.token)
    )
    account = result.scalar_one_or_none()
    if not account or not account.reset_token_expires:
        raise HTTPException(status_code=400, detail="Token non valido")
    if account.reset_token_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token scaduto")

    account.password_hash = hash_password(payload.new_password)
    account.reset_token = None
    account.reset_token_expires = None
    return MessageResponse(message="Password aggiornata con successo")
