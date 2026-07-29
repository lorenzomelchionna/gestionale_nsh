"""
Phone numbers are stored in E.164 (`+39…`) so that one person is one record.

Two places match a client by phone and both compare plain strings: online
registration linking a new account to a client the salon already knows, and
inbound WhatsApp working out who wrote. "333 287 6794" and "+39 333 287 6794"
are the same person but not the same string, so a client entered by hand would
silently split into a second record with its own history.

Normalising on the way in — rather than at every comparison — keeps the stored
value canonical, which is also the format Twilio requires to deliver anything.
"""
from typing import Optional

DEFAULT_COUNTRY_CODE = "39"  # Italy

# Loose sanity bound: the shortest Italian numbers are 9 digits, so 6 rejects
# obvious typos ("333") without second-guessing foreign formats.
MIN_DIGITS = 6


class InvalidPhoneNumber(ValueError):
    """Raised for input that carries no usable digits."""


def to_e164(raw: Optional[str], country_code: str = DEFAULT_COUNTRY_CODE) -> Optional[str]:
    """
    Return `raw` as an E.164 number, or None when no number was given.

    Blank input means "no phone on file" and is allowed. Input that looks like
    an attempt at a number but cannot be one raises, so a typo surfaces as a
    validation error instead of being stored in a shape nothing can match.
    """
    if raw is None:
        return None

    text = raw.strip()
    if not text:
        return None

    # Only a leading + carries meaning; any others are formatting noise.
    explicit_plus = text.startswith("+")
    digits = "".join(ch for ch in text if ch.isdigit())

    if not digits or len(digits) < MIN_DIGITS:
        raise InvalidPhoneNumber(
            f"Numero di telefono non valido: {raw!r}. "
            "Usa il formato +39 333 1234567 oppure 333 1234567."
        )

    if explicit_plus:
        return "+" + digits

    # 0039… — the dialling prefix spelled out.
    if digits.startswith("00"):
        return "+" + digits[2:]

    # A leading 39 is ambiguous: it is the country code on +39 333…, but also
    # the start of the mobile prefix 393…. Italian numbers run to 10 digits, so
    # anything longer that starts with 39 already carries the country code.
    if digits.startswith(country_code) and len(digits) > 10:
        return "+" + digits

    return "+" + country_code + digits
