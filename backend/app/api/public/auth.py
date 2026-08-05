from typing import Annotated
from datetime import datetime, timedelta, timezone
import secrets
from fastapi import Request, APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from app.database import get_db
from app.rate_limit import limiter
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
    code = await issue_code(account)
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
@limiter.limit("5/hour")
async def register(
    request: Request, payload: ClientRegister, db: Annotated[AsyncSession, Depends(get_db)]
):
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
        existing.password_hash = await hash_password(payload.password)
        sent = await _send_code(db, existing, payload.first_name)
        return VerificationRequired(email=existing.email, email_sent=sent)

    account = ClientAccount(
        email=payload.email,
        password_hash=await hash_password(payload.password),
        email_verified=False,
    )
    db.add(account)
    await db.flush()

    # No record the salon already holds is touched here, and that is the whole
    # point. Attaching an account to an existing client is a claim about who
    # someone is, and at this moment nothing has been proven: the address has
    # not been confirmed yet and the phone number was never checked at all.
    #
    # This used to match `phone OR email` and overwrite `account_id` on the
    # spot. Knowing a client's mobile number — which in a neighbourhood salon
    # is the least secret thing there is — was therefore enough to be handed
    # her appointment history, and enough to detach her from her own record
    # without even reading the confirmation email.
    #
    # So sign-up only ever creates its own row. Folding it into the salon's
    # record happens in verify-email, once the address has been proven.
    db.add(Client(
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        email=payload.email,
        birth_date=payload.birth_date,
        account_id=account.id,
    ))

    sent = await _send_code(db, account, payload.first_name)
    return VerificationRequired(email=account.email, email_sent=sent)


async def _adopt_salon_record(db: AsyncSession, account: ClientAccount) -> None:
    """Fold the sign-up row into the salon's own record, if they are the same person.

    Runs only after the code has been entered, so the address is the one fact
    about this person that has actually been established — which is why it is
    the only thing matched on. A phone number is not proof: anyone can type
    someone else's, and doing so is what used to hand over a stranger's history.

    Only an unclaimed record is adopted. Two people can legitimately share a
    number or an old address — a couple, a mother and daughter — and whoever
    registers second must not inherit the first one's appointments.

    Matching is exact, including case, because addresses are stored as typed
    (see the note on case sensitivity in TODO_notifiche.md). A salon record
    spelled `Mario.Rossi@…` against a sign-up as `mario.rossi@…` therefore
    stays a separate row: a duplicate to merge by hand, not a wrong merge.
    """
    from app.models.appointment import Appointment

    stub = (await db.execute(
        select(Client).where(Client.account_id == account.id)
    )).scalar_one_or_none()
    if stub is None:
        return

    salon_record = (await db.execute(
        select(Client)
        .where(Client.email == account.email, Client.account_id.is_(None))
        .order_by(Client.id)
        .limit(1)
    )).scalar_one_or_none()
    if salon_record is None:
        return

    # The salon's row is the one that survives: it carries the appointment
    # history, the notes and whatever else was recorded in person.
    salon_record.account_id = account.id
    if not salon_record.phone:
        salon_record.phone = stub.phone
    if not salon_record.birth_date:
        salon_record.birth_date = stub.birth_date

    stub.account_id = None
    await db.flush()

    # Normally the sign-up row is minutes old and empty, so it just goes. But
    # someone can register, ignore the email for a week, and verify later — and
    # in the meantime the salon may have booked against that row, having seen it
    # in the client list. Then deleting it would take a real appointment with
    # it, and two rows the salon can merge deliberately beats one that silently
    # lost something.
    booked = (await db.execute(
        select(func.count()).select_from(Appointment).where(Appointment.client_id == stub.id)
    )).scalar_one()
    if booked == 0:
        await db.delete(stub)


@router.post("/verify-email", response_model=TokenResponse)
@limiter.limit("10/minute")
async def verify_email(
    request: Request, payload: EmailVerification, db: Annotated[AsyncSession, Depends(get_db)]
):
    """Exchange the emailed code for a session. This is where the account starts."""
    account = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == payload.email)
    )).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=400, detail="Codice o indirizzo non validi")

    try:
        await check_code(account, payload.code)
    except VerificationError as e:
        # Committed, not flushed: get_db rolls back on any exception, so a
        # flush here would be undone by the raise below and every wrong guess
        # would be free. The attempt budget only exists if this survives.
        await db.commit()
        raise HTTPException(status_code=400, detail=e.detail)

    # The address is proven from here on, which is the only moment at which it
    # is safe to attach this account to a record the salon already had.
    await _adopt_salon_record(db, account)

    await db.flush()
    access = create_access_token(account.id, {"type": "client"})
    refresh = create_refresh_token(account.id, {"type": "client"})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/resend-code", response_model=ResendResult)
@limiter.limit("3/hour")
async def resend_code(
    request: Request, payload: PasswordResetRequest, db: Annotated[AsyncSession, Depends(get_db)]
):
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
@limiter.limit("10/minute")
async def login(
    request: Request, payload: ClientLoginRequest, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(ClientAccount).where(ClientAccount.email == payload.email))
    account = result.scalar_one_or_none()
    if not account or not await verify_password(payload.password, account.password_hash):
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
@limiter.limit("3/hour")
async def forgot_password(
    request: Request, payload: PasswordResetRequest, db: Annotated[AsyncSession, Depends(get_db)]
):
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
@limiter.limit("10/minute")
async def reset_password(
    request: Request, payload: PasswordReset, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(ClientAccount).where(ClientAccount.reset_token == payload.token)
    )
    account = result.scalar_one_or_none()
    if not account or not account.reset_token_expires:
        raise HTTPException(status_code=400, detail="Token non valido")
    if account.reset_token_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token scaduto")

    account.password_hash = await hash_password(payload.new_password)
    account.reset_token = None
    account.reset_token_expires = None
    return MessageResponse(message="Password aggiornata con successo")
