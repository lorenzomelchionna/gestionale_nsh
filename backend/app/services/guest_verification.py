"""
Proving the number of someone who books from the portal without an account.

Same code, same expiry, same guess budget as `phone_verification.py` — see
that module and `email_verification.py` for why each of the three matters.
What changes is where the code lives: there is no account to hang it on, so
it hangs on the number itself (`GuestPhoneCode`, one row per number).

The number is what the whole booking rests on. The salon confirms and
reminds on WhatsApp, and the record the booking lands on is found by that
number: without proof, anyone could book in a stranger's name and have the
salon message her about an appointment she never asked for.

One thing is new here: a cap on how often a number can be sent a code.
Registration gets away with the per-IP limit alone because it also costs an
email address; here the only input is someone's number, and each code is a
paid WhatsApp message landing on the phone of whoever owns it.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guest_phone_code import GuestPhoneCode
from app.services.verification_codes import CODE_TTL_MINUTES, MAX_ATTEMPTS, generate_code
from app.utils.auth import hash_password, verify_password

# Long enough that a double tap or an impatient "resend" is not a second
# message; short enough that someone whose code never arrived is not stuck.
RESEND_COOLDOWN = timedelta(seconds=60)
# A person books a few times a month. Five codes in a day on one number is
# already generous; beyond it, it is someone else doing the typing.
MAX_SENDS_PER_WINDOW = 5
SEND_WINDOW = timedelta(hours=24)


class CodeRefused(Exception):
    """No code sent this time, with the reason to show the person."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class VerificationError(Exception):
    """Rejected attempt, carrying the reason to show the person."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


async def _row(db: AsyncSession, phone: str) -> GuestPhoneCode:
    """The number's row, created if missing and locked for this transaction.

    Insert-then-lock rather than select-then-insert: two requests for a new
    number at the same moment would otherwise both find nothing, and the
    second would die on the unique index instead of waiting its turn.
    """
    await db.execute(
        insert(GuestPhoneCode)
        .values(phone=phone, attempts=0, sends_in_window=0)
        .on_conflict_do_nothing(index_elements=["phone"])
    )
    return (await db.execute(
        select(GuestPhoneCode).where(GuestPhoneCode.phone == phone).with_for_update()
    )).scalar_one()


async def issue_code(db: AsyncSession, phone: str) -> str:
    """
    Store a fresh code for `phone` and return the plaintext to send.

    Raises `CodeRefused` when the number has had a code too recently or too
    often. The plaintext is returned rather than stored: this is the only
    moment it exists, and the caller has to send it before it goes out of scope.
    """
    now = datetime.now(timezone.utc)
    row = await _row(db, phone)

    if row.last_sent_at and now - row.last_sent_at < RESEND_COOLDOWN:
        raise CodeRefused("Ti abbiamo appena mandato un codice. Aspetta un minuto prima di chiederne un altro.")

    if row.window_started_at is None or now - row.window_started_at >= SEND_WINDOW:
        row.window_started_at = now
        row.sends_in_window = 0
    if row.sends_in_window >= MAX_SENDS_PER_WINDOW:
        raise CodeRefused(
            "Troppi codici richiesti per questo numero. Riprova domani o contatta il salone."
        )

    code = generate_code()
    row.code_hash = await hash_password(code)
    row.expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
    row.attempts = 0
    row.last_sent_at = now
    row.sends_in_window += 1
    await db.flush()
    return code


async def check_code(db: AsyncSession, phone: str, code: str) -> None:
    """
    Consume one attempt against `phone`'s code, or raise with the reason.

    On success the code is cleared, so one code is one booking. The caller
    must commit before raising on failure, or the attempt is rolled back and
    the guess was free — same rule as the other two verification modules.
    """
    row = (await db.execute(
        select(GuestPhoneCode).where(GuestPhoneCode.phone == phone).with_for_update()
    )).scalar_one_or_none()

    if row is None or not row.code_hash or not row.expires_at:
        raise VerificationError("Nessun codice per questo numero. Richiedine uno.")

    if row.expires_at < datetime.now(timezone.utc):
        raise VerificationError("Il codice è scaduto. Richiedine uno nuovo.")

    if row.attempts >= MAX_ATTEMPTS:
        raise VerificationError("Troppi tentativi. Richiedi un nuovo codice.")

    # Counted before the comparison: a request that dies mid-way must still
    # cost an attempt, or the budget can be sidestepped by disconnecting.
    row.attempts += 1

    if not await verify_password(code, row.code_hash):
        left = MAX_ATTEMPTS - row.attempts
        if left <= 0:
            raise VerificationError("Codice errato. Richiedi un nuovo codice.")
        raise VerificationError(f"Codice errato. Tentativi rimasti: {left}.")

    row.code_hash = None
    row.expires_at = None
    row.attempts = 0
