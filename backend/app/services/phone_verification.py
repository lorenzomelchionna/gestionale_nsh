"""
Proving that the WhatsApp number someone typed is one they hold.

Sibling of `email_verification.py`, one step later in registration and one
channel over — see that module for why the three properties (expiry, capped
guesses, hashed storage) all matter together; the code and its constants are
shared in `verification_codes.py`.

Without this, nothing stops someone from typing a stranger's number at
sign-up: that person would start receiving the salon's WhatsApp messages —
booking confirmations, reminders, someone else's appointment times — for a
client they have never met.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.client import ClientAccount
from app.services.verification_codes import CODE_LENGTH, CODE_TTL_MINUTES, MAX_ATTEMPTS, generate_code
from app.utils.auth import hash_password, verify_password

__all__ = [
    "CODE_LENGTH", "CODE_TTL_MINUTES", "MAX_ATTEMPTS", "generate_code",
    "issue_code", "VerificationError", "check_code", "is_pending",
]


async def issue_code(account: ClientAccount) -> str:
    """
    Attach a fresh code to `account` and return the plaintext to send.

    The plaintext is returned rather than stored: this is the only moment it
    exists, and the caller has to send it before it goes out of scope.
    """
    code = generate_code()
    account.phone_verification_code_hash = await hash_password(code)
    account.phone_verification_expires = datetime.now(timezone.utc) + timedelta(
        minutes=CODE_TTL_MINUTES
    )
    account.phone_verification_attempts = 0
    return code


class VerificationError(Exception):
    """Rejected attempt, carrying the reason to show the person."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


async def check_code(account: ClientAccount, code: str) -> None:
    """
    Consume one attempt against `account`, or raise with the reason.

    On success the code is cleared, so it cannot be replayed.
    """
    if account.phone_verified:
        raise VerificationError("Questo numero è già stato verificato")

    if not account.phone_verification_code_hash or not account.phone_verification_expires:
        raise VerificationError("Nessun codice da verificare. Richiedine uno nuovo.")

    if _expired(account.phone_verification_expires):
        raise VerificationError("Il codice è scaduto. Richiedine uno nuovo.")

    if account.phone_verification_attempts >= MAX_ATTEMPTS:
        raise VerificationError("Troppi tentativi. Richiedi un nuovo codice.")

    # Counted before the comparison: a request that dies mid-way must still
    # cost an attempt, or the budget can be sidestepped by disconnecting.
    account.phone_verification_attempts += 1

    if not await verify_password(code, account.phone_verification_code_hash):
        left = MAX_ATTEMPTS - account.phone_verification_attempts
        if left <= 0:
            raise VerificationError("Codice errato. Richiedi un nuovo codice.")
        raise VerificationError(f"Codice errato. Tentativi rimasti: {left}.")

    account.phone_verified = True
    account.phone_verification_code_hash = None
    account.phone_verification_expires = None
    account.phone_verification_attempts = 0


def _expired(moment: datetime) -> bool:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment < datetime.now(timezone.utc)


def is_pending(account: Optional[ClientAccount]) -> bool:
    """True when the address is proven but the number is not yet."""
    return account is not None and account.email_verified and not account.phone_verified
