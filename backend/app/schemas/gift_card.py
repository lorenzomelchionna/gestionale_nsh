from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.gift_card import GiftCardStatus
from app.models.payment import PaymentMethod

# Un anno dalla vendita, che è la durata abituale di un buono regalo. Sta qui
# e non nel form: la data la calcola il server, così due operatori diversi non
# producono due scadenze diverse per la stessa cosa.
DEFAULT_VALIDITY_DAYS = 365

MIN_AMOUNT = 5
MAX_AMOUNT = 1000


class GiftCardCreate(BaseModel):
    """La vendita al banco.

    L'email del destinatario è obbligatoria perché è il senso della cosa: la
    gift card arriva a chi la riceve. Senza indirizzo resterebbe un credito
    che esiste solo nel gestionale, e chi lo ha ricevuto non saprebbe di
    averlo.
    """

    amount: float = Field(..., ge=MIN_AMOUNT, le=MAX_AMOUNT)
    recipient_name: str = Field(..., min_length=1, max_length=200)
    recipient_email: EmailStr
    message: Optional[str] = Field(None, max_length=1000)

    purchaser_client_id: Optional[int] = None
    purchaser_name: Optional[str] = Field(None, max_length=200)

    # Come ha pagato chi compra. Serve a registrare l'incasso in cassa: la
    # vendita di un buono è denaro che entra oggi.
    payment_method: PaymentMethod = PaymentMethod.cash

    validity_days: int = Field(DEFAULT_VALIDITY_DAYS, ge=30, le=1825)

    @field_validator("recipient_name", "purchaser_name", "message")
    @classmethod
    def niente_stringhe_di_spazi(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class GiftCardRedeem(BaseModel):
    """Un prelievo dal credito.

    L'importo si scrive a mano invece di svuotare la card: un buono da 50€ su
    un servizio da 30€ deve lasciarne 20, e un buono da 50€ su un servizio da
    70€ ne copre 50 e il resto si paga normalmente.
    """

    amount: float = Field(..., gt=0, le=MAX_AMOUNT)
    appointment_id: Optional[int] = None
    notes: Optional[str] = Field(None, max_length=500)


class GiftCardCancel(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


class GiftCardResend(BaseModel):
    """Corpo facoltativo del rinvio: se c'è un indirizzo, sostituisce il vecchio."""

    recipient_email: Optional[EmailStr] = None


class GiftCardRedemptionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    amount: float
    appointment_id: Optional[int] = None
    # «05/08/2026 · Laura Ricci». Composta qui invece di lasciare al frontend
    # un id da risolvere con una chiamata per riga: uno storico di riscatti
    # ne farebbe una a testa, e la scheda si aprirebbe a pezzi.
    appointment_label: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    @classmethod
    def from_redemption(cls, r) -> "GiftCardRedemptionOut":
        out = cls.model_validate(r, from_attributes=True)
        appt = getattr(r, "appointment", None)
        if appt is not None:
            quando = appt.start_time.strftime("%d/%m/%Y")
            chi = f"{appt.client.first_name} {appt.client.last_name}" if appt.client else ""
            out.appointment_label = f"{quando} · {chi}".strip(" ·")
        return out


class GiftCardOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    initial_amount: float
    balance: float
    recipient_name: str
    recipient_email: str
    message: Optional[str] = None
    purchaser_client_id: Optional[int] = None
    purchaser_name: Optional[str] = None
    expires_at: date
    payment_id: Optional[int] = None
    email_sent_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    created_at: datetime

    # Default e non campo obbligatorio: `status` non è una colonna, quindi la
    # validazione da ORM non lo troverebbe. Lo riempie `from_card`, che è il
    # solo modo previsto di costruire questa risposta.
    status: GiftCardStatus = GiftCardStatus.active
    redemptions: List[GiftCardRedemptionOut] = []

    @classmethod
    def from_card(cls, card) -> "GiftCardOut":
        """Proietta la card calcolandone lo stato.

        Passa da qui e non da `model_validate` diretto perché lo stato è una
        decisione presa su saldo, scadenza e annullamento insieme, e va presa
        in un posto solo.
        """
        out = cls.model_validate(card, from_attributes=True)
        out.status = card.compute_status()
        out.redemptions = [
            GiftCardRedemptionOut.from_redemption(r) for r in card.redemptions
        ]
        return out
