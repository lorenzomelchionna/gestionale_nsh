from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from app.models.payment import PaymentMethod, PaymentType
from app.schemas.product import ProdottoVenduto
from app.services.vendite import totale_righe


class PaymentCreate(BaseModel):
    client_id: Optional[int] = None
    appointment_id: Optional[int] = None
    amount: float
    method: PaymentMethod
    type: PaymentType = PaymentType.service
    notes: Optional[str] = None
    cash_amount: Optional[float] = None
    card_amount: Optional[float] = None
    # Per chi entra solo a comprare (richiesta del 2026-10-09): i prodotti
    # venduti, scalati dal magazzino con le stesse regole dell'«Incassa»
    # di una visita. Vuoto = incasso scritto a mano, come prima.
    products: List[ProdottoVenduto] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_products(self) -> "PaymentCreate":
        """Con dei prodotti l'importo è la loro somma, non un numero a parte.

        Si controlla invece di ricalcolarlo per non cambiare in silenzio
        quello che è stato digitato: se non torna, è il browser ad aver
        sbagliato il conto, e un incasso diverso da quello mostrato non va
        registrato. E il tipo è «prodotto», o il cruscotto conterebbe la
        rivendita fra i servizi.
        """
        if not self.products:
            return self
        if self.type != PaymentType.product:
            raise ValueError("Un incasso con prodotti venduti è di tipo «prodotto»")
        totale = totale_righe(self.products)
        if totale <= 0:
            raise ValueError(
                "Prodotti a prezzo zero: un omaggio si registra come scarico dal magazzino"
            )
        if abs(totale - round(self.amount, 2)) > 0.01:
            raise ValueError(f"L'importo ({self.amount}) non corrisponde ai prodotti ({totale})")
        return self

    @model_validator(mode="after")
    def validate_split(self) -> "PaymentCreate":
        if self.method == PaymentMethod.mixed:
            if self.cash_amount is None or self.card_amount is None:
                raise ValueError("Per pagamento misto specificare cash_amount e card_amount")
            if self.cash_amount < 0 or self.card_amount < 0:
                raise ValueError("Gli importi devono essere positivi")
            total = round(self.cash_amount + self.card_amount, 2)
            if abs(total - round(self.amount, 2)) > 0.01:
                raise ValueError(
                    f"cash_amount + card_amount ({total}) deve corrispondere ad amount ({self.amount})"
                )
        else:
            # Non misto: ignora i campi split
            self.cash_amount = None
            self.card_amount = None
        return self


class PaymentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    client_id: Optional[int] = None
    appointment_id: Optional[int] = None
    amount: float
    method: PaymentMethod
    type: PaymentType
    date: datetime
    notes: Optional[str] = None
    cash_amount: Optional[float] = None
    card_amount: Optional[float] = None
