"""
Proving that the address someone typed is one they can read.

Without this, anyone could register under another person's email: they would
receive the salon's appointment mail, and the real owner would find their
address already taken. The code closes both.

Three properties do the work, and all three matter together:
  - it expires, so a code read over a shoulder or left in an old inbox dies;
  - guesses are counted, because six digits fall in a second otherwise;
  - it is stored hashed, so the database alone does not hand out sessions.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.client import ClientAccount
from app.utils.auth import hash_password, verify_password

CODE_LENGTH = 6
CODE_TTL_MINUTES = 15
# Six digits is a million possibilities; five tries keeps a blind guess at
# roughly one in two hundred thousand, and a wrong code is cheap to resend.
MAX_ATTEMPTS = 5


def generate_code() -> str:
    """A zero-padded numeric code, from a generator meant for secrets."""
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def issue_code(account: ClientAccount) -> str:
    """
    Attach a fresh code to `account` and return the plaintext to email.

    The plaintext is returned rather than stored: this is the only moment it
    exists, and the caller has to send it before it goes out of scope.
    """
    code = generate_code()
    account.verification_code_hash = hash_password(code)
    account.verification_expires = datetime.now(timezone.utc) + timedelta(
        minutes=CODE_TTL_MINUTES
    )
    account.verification_attempts = 0
    return code


class VerificationError(Exception):
    """Rejected attempt, carrying the reason to show the person."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def check_code(account: ClientAccount, code: str) -> None:
    """
    Consume one attempt against `account`, or raise with the reason.

    On success the code is cleared, so it cannot be replayed.
    """
    if account.email_verified:
        raise VerificationError("Questo indirizzo è già stato verificato")

    if not account.verification_code_hash or not account.verification_expires:
        raise VerificationError("Nessun codice da verificare. Richiedine uno nuovo.")

    if _expired(account.verification_expires):
        raise VerificationError("Il codice è scaduto. Richiedine uno nuovo.")

    if account.verification_attempts >= MAX_ATTEMPTS:
        raise VerificationError("Troppi tentativi. Richiedi un nuovo codice.")

    # Counted before the comparison: a request that dies mid-way must still
    # cost an attempt, or the budget can be sidestepped by disconnecting.
    account.verification_attempts += 1

    if not verify_password(code, account.verification_code_hash):
        left = MAX_ATTEMPTS - account.verification_attempts
        if left <= 0:
            raise VerificationError("Codice errato. Richiedi un nuovo codice.")
        raise VerificationError(f"Codice errato. Tentativi rimasti: {left}.")

    account.email_verified = True
    account.verification_code_hash = None
    account.verification_expires = None
    account.verification_attempts = 0


def _expired(moment: datetime) -> bool:
    # Rows written before timezone handling settled can come back naive; treat
    # those as UTC rather than raising on the comparison.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment < datetime.now(timezone.utc)


def is_pending(account: Optional[ClientAccount]) -> bool:
    """True when an account exists but has not proved its address yet."""
    return account is not None and not account.email_verified
