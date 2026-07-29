from typing import Annotated
from datetime import datetime, timedelta, timezone
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models.client import Client, ClientAccount
from app.models.user import User
from app.schemas.client import (
    ClientRegister, ClientLoginRequest, PasswordResetRequest, PasswordReset,
    EmailVerification, ResendResult, VerificationRequired,
)
from app.schemas.common import TokenResponse, MessageResponse
from app.services.email_verification import (
    CODE_TTL_MINUTES, VerificationError, check_code, issue_code,
)
from app.utils.auth import hash_password, verify_password, create_access_token, create_refresh_token
from app.utils.email import send_verification_code_email

router = APIRouter(prefix="/auth", tags=["Client Auth"])


async def _send_code(db: AsyncSession, account: ClientAccount, first_name: str) -> bool:
    """
    Issue a fresh code and mail it. Returns whether the mail actually left.

    Delivery failure is not fatal — the code is stored, so a later resend can
    recover the account rather than losing it to a transient mail error. But it
    is reported: telling someone a code is on its way when the send failed
    leaves them waiting for an email that will never arrive.
    """
    code = issue_code(account)
    await db.flush()
    try:
        await send_verification_code_email(
            account.email, first_name, code, CODE_TTL_MINUTES
        )
        return True
    except Exception as e:
        print(f"[VERIFY] failed to send code to account={account.id}: {e}")
        return False


@router.post("/register", response_model=VerificationRequired, status_code=status.HTTP_201_CREATED)
async def register(payload: ClientRegister, db: Annotated[AsyncSession, Depends(get_db)]):
    existing = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == payload.email)
    )).scalar_one_or_none()

    if existing and existing.email_verified:
        raise HTTPException(status_code=400, detail="Email già registrata")

    # Staff and clients share one sign-in screen, so an address can only mean
    # one account. Salon staff who also want to book do so with another address.
    staff = await db.execute(select(User).where(User.email == payload.email))
    if staff.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Questa email è già usata dallo staff del salone. Usane un'altra.",
        )

    if existing:
        # An unverified account proves nothing about who owns the address, so it
        # must not be able to hold it hostage: whoever registers next takes it
        # over and gets the new code. Only the mailbox owner can finish.
        existing.password_hash = hash_password(payload.password)
        sent = await _send_code(db, existing, payload.first_name)
        return VerificationRequired(email=existing.email, email_sent=sent)

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

    account = ClientAccount(
        email=payload.email,
        password_hash=hash_password(payload.password),
        email_verified=False,
    )
    db.add(account)
    await db.flush()

    if client:
        # Link existing client to this account. Only blanks are filled in: the
        # salon's own record wins over what someone types at sign-up.
        client.account_id = account.id
        if not client.email:
            client.email = payload.email
        if not client.birth_date:
            client.birth_date = payload.birth_date
    else:
        # Create new client record
        client = Client(
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            email=payload.email,
            birth_date=payload.birth_date,
            account_id=account.id,
        )
        db.add(client)

    sent = await _send_code(db, account, payload.first_name)
    return VerificationRequired(email=account.email, email_sent=sent)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(payload: EmailVerification, db: Annotated[AsyncSession, Depends(get_db)]):
    """Exchange the emailed code for a session. This is where the account starts."""
    account = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == payload.email)
    )).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=400, detail="Codice o indirizzo non validi")

    try:
        check_code(account, payload.code)
    except VerificationError as e:
        # Committed, not flushed: get_db rolls back on any exception, so a
        # flush here would be undone by the raise below and every wrong guess
        # would be free. The attempt budget only exists if this survives.
        await db.commit()
        raise HTTPException(status_code=400, detail=e.detail)

    await db.flush()
    access = create_access_token(account.id, {"type": "client"})
    refresh = create_refresh_token(account.id, {"type": "client"})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/resend-code", response_model=ResendResult)
async def resend_code(payload: PasswordResetRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Issue a new code, replacing any outstanding one."""
    account = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == payload.email)
    )).scalar_one_or_none()

    sent = True
    if account and not account.email_verified:
        client = (await db.execute(
            select(Client).where(Client.account_id == account.id)
        )).scalar_one_or_none()
        sent = await _send_code(db, account, client.first_name if client else "")

    # The message is the same for every address; only a genuine send failure
    # changes the answer. See ResendResult for why that trade is worth making.
    return ResendResult(
        message="Se l'indirizzo è in attesa di verifica, riceverai un nuovo codice",
        email_sent=sent,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: ClientLoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(ClientAccount).where(ClientAccount.email == payload.email))
    account = result.scalar_one_or_none()
    if not account or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not account.is_active:
        raise HTTPException(status_code=403, detail="Account disabilitato")
    if not account.email_verified:
        # Distinct from bad credentials on purpose: the password was right, and
        # the caller needs to be sent to the code screen rather than told to
        # try again. Only reachable by someone who already knows the password.
        raise HTTPException(
            status_code=403,
            detail="Indirizzo email non ancora verificato. Inserisci il codice che ti abbiamo inviato.",
        )

    access = create_access_token(account.id, {"type": "client"})
    refresh = create_refresh_token(account.id, {"type": "client"})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: PasswordResetRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    from app.config import settings
    from app.utils.notifications import notify_password_reset

    result = await db.execute(select(ClientAccount).where(ClientAccount.email == payload.email))
    account = result.scalar_one_or_none()
    if account:
        token = secrets.token_urlsafe(32)
        account.reset_token = token
        account.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=2)
        await db.flush()
        # Build the reset URL pointing to the public booking portal
        reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/booking/reset-password?token={token}"
        try:
            await notify_password_reset(db, account, reset_url)
        except Exception as e:
            print(f"[NOTIFY:reset] failed to dispatch: {e}")
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
