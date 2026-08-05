from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.phone import to_e164


class ClientBase(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    birth_date: Optional[date] = None
    notes: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def normalise_phone(cls, value: Optional[str]) -> Optional[str]:
        """Store canonically so a hand-entered client and the same client
        registering online resolve to one record. See app/utils/phone.py."""
        return to_e164(value)


class ClientCreate(ClientBase):
    pass


class ClientUpdate(ClientBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ClientOut(ClientBase):
    model_config = {"from_attributes": True}

    id: int
    is_active: bool
    account_id: Optional[int] = None
    created_at: datetime


class MergeRequest(BaseModel):
    """Quale scheda far confluire in quale.

    La destinazione sta nell'URL, l'origine qui: la scheda che **resta** è
    quella indicata nel percorso, e la scelta la fa chi chiama, non
    un'euristica. Si potrebbe far vincere «la più vecchia» o «quella con più
    appuntamenti» — entrambe ragionevoli, entrambe ogni tanto sbagliate — ma
    la fusione non si annulla, quindi il codice esegue invece di indovinare.
    """
    source_id: int = Field(..., description="La scheda che verrà svuotata e disattivata")


class MergePreview(BaseModel):
    """Cosa comporterebbe la fusione, prima di farla.

    Non è una gentilezza verso l'interfaccia: è l'unico modo che ha chi preme
    il pulsante di sapere che sta spostando dodici appuntamenti e tre incassi
    e non zero. Senza, «unisci» è un pulsante che si preme e si spera.
    """
    source: ClientOut
    target: ClientOut
    moved: dict[str, int]
    filled_fields: list[str]
    notes_merged: bool
    account_moved: bool
    total_rows: int


# Dieci e non dodici come per lo staff: chi lavora in salone ha accesso a
# tutta l'anagrafica e alla cassa, una cliente solo ai propri appuntamenti,
# quindi la soglia segue quello che c'è dietro la porta. Prima non c'era
# nessun minimo lato server — il campo accettava `1` — e un limite scritto
# solo nel form del browser non è un limite: basta chiamare l'API.
MIN_CLIENT_PASSWORD = 10


class ClientRegister(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: EmailStr
    password: str = Field(min_length=MIN_CLIENT_PASSWORD)
    # Asked for at sign-up rather than left to be filled in later: the birthday
    # greeting only reaches people whose date is on file, and a field the form
    # never asks about stays empty.
    birth_date: date

    @field_validator("phone")
    @classmethod
    def normalise_phone(cls, value: str) -> str:
        """Normalised before registration looks for an existing client by phone,
        so the lookup compares the same shape that admin-entered records hold."""
        normalised = to_e164(value)
        if normalised is None:
            raise ValueError("Il numero di telefono è obbligatorio")
        return normalised

    @field_validator("birth_date")
    @classmethod
    def must_be_a_plausible_birthday(cls, value: date) -> date:
        """Catches the two typos a date field invites: the wrong year, and today."""
        today = date.today()
        if value >= today:
            raise ValueError("La data di nascita deve essere nel passato")
        if value < today.replace(year=today.year - 120):
            raise ValueError("Data di nascita non valida")
        return value


class ClientAccountOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    is_active: bool
    created_at: datetime


class ClientLoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerificationRequired(BaseModel):
    """Registration's answer: an account exists, but it has no session yet."""
    email: EmailStr
    verification_required: bool = True
    # False when the code could not be mailed. The account still exists and a
    # resend can recover it, but the caller must not be told to check an inbox
    # that will stay empty.
    email_sent: bool = True


class EmailVerification(BaseModel):
    email: EmailStr
    code: str


class ResendResult(BaseModel):
    """
    Deliberately the same message whatever the address, so the endpoint cannot
    be used to find out who is registered.

    `email_sent` is the one exception: it goes false only when a send genuinely
    failed, which does reveal that the address was pending. That is a fair
    trade — it only happens while our own mail is broken, and the alternative
    is telling someone to watch an inbox nothing was sent to.
    """
    message: str
    email_sent: bool = True


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str
    # Stesso minimo della registrazione: senza, il reset sarebbe la strada
    # per aggirarlo — si registra con una password lunga e la si accorcia
    # subito dopo.
    new_password: str = Field(min_length=MIN_CLIENT_PASSWORD)
