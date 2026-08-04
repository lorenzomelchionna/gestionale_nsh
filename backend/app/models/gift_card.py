"""Buoni regalo: un credito prepagato che si spende in salone.

Due tabelle e non una. La card porta il saldo, che è il numero che serve al
banco; `gift_card_redemptions` porta la storia di come ci è arrivato. Il
saldo da solo direbbe «restano 20€» senza poter dire perché, e su una cosa
che è denaro di qualcun altro la domanda «dove sono finiti gli altri 30?»
va saputa rispondere.

Lo stato non è una colonna: si ricava da saldo, scadenza e annullamento.
Una colonna in più vorrebbe dire tenerla allineata a ogni riscatto, e il
giorno in cui si disallinea è il giorno in cui una card esaurita risulta
ancora spendibile.
"""
import enum
import secrets
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Niente 0/O né 1/I/L: il codice viene letto ad alta voce al telefono e
# ricopiato a mano da un'email, e quelle coppie si sbagliano sempre.
CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXY2346789"
CODE_BLOCKS = 3
CODE_BLOCK_LEN = 4


def generate_code() -> str:
    """Un codice tipo `NSH-A7K2-9QX4-MT3F`.

    Non è un identificativo progressivo: chi conosce un codice può presentarsi
    in salone e spendere quel credito, quindi indovinarne uno deve essere fuori
    portata. Dodici caratteri su un alfabeto di 27 sono circa 57 bit, cioè
    centomila miliardi di tentativi per averne uno — e i tentativi qui si fanno
    di persona, davanti a una cassiera.
    """
    blocchi = [
        "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_BLOCK_LEN))
        for _ in range(CODE_BLOCKS)
    ]
    return "NSH-" + "-".join(blocchi)


class GiftCardStatus(str, enum.Enum):
    """Stato ricavato, mai scritto a database."""

    active = "attiva"
    exhausted = "esaurita"
    expired = "scaduta"
    cancelled = "annullata"


class GiftCard(Base):
    __tablename__ = "gift_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    initial_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # Il saldo è ridondante rispetto ai riscatti, ed è voluto: è il numero che
    # si legge a ogni ricerca al banco, e ricalcolarlo da una somma a ogni
    # lettura significherebbe farlo anche mentre si decide se accettare il
    # buono. Viene scritto nella stessa transazione del riscatto, sotto lock
    # della riga; `tests/test_gift_cards.py` verifica che i due non divergano.
    balance: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Il destinatario è il punto della richiesta: l'email va a chi riceve il
    # regalo, non a chi lo compra. Testo libero e non una FK ai clienti —
    # si regala anche a chi in salone non è mai stato.
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Chi compra: collegato all'anagrafica se è una cliente conosciuta, il nome
    # e basta se è di passaggio.
    purchaser_client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    purchaser_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    expires_at: Mapped[date] = mapped_column(Date, nullable=False)

    # L'incasso della vendita. La gift card entra in cassa il giorno in cui si
    # vende, non il giorno in cui si usa: quel giorno i soldi sono davvero nel
    # cassetto. Al riscatto non nasce nessun pagamento, altrimenti gli stessi
    # euro verrebbero contati due volte.
    payment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Quando l'email è partita davvero. È l'unica parte della funzionalità che
    # il salone non può verificare da sé: senza questo campo, «gliel'hai
    # mandata?» non ha risposta.
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    redemptions: Mapped[List["GiftCardRedemption"]] = relationship(
        "GiftCardRedemption",
        back_populates="gift_card",
        cascade="all, delete-orphan",
        order_by="GiftCardRedemption.created_at",
    )
    purchaser: Mapped[Optional["Client"]] = relationship("Client")

    def compute_status(self, today: Optional[date] = None) -> GiftCardStatus:
        """Lo stato, nell'ordine in cui conta al banco.

        Si chiama `compute_status` e non `status` di proposito: lo schema di
        uscita espone un campo `status`, e un attributo con lo stesso nome
        finirebbe nella proiezione come metodo invece che come valore.

        L'annullamento vince su tutto: una card stornata non si spende nemmeno
        se ha saldo e non è scaduta. La scadenza viene prima dell'esaurimento
        perché a saldo zero le due sarebbero entrambe vere, e «esaurita» è
        quella che descrive cosa è successo davvero.
        """
        if self.cancelled_at is not None:
            return GiftCardStatus.cancelled
        if float(self.balance) <= 0:
            return GiftCardStatus.exhausted
        if self.expires_at < (today or date.today()):
            return GiftCardStatus.expired
        return GiftCardStatus.active

    def is_spendable(self, today: Optional[date] = None) -> bool:
        return self.compute_status(today) == GiftCardStatus.active


class GiftCardRedemption(Base):
    """Un prelievo dal credito. Righe che non si modificano e non si cancellano."""

    __tablename__ = "gift_card_redemptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    gift_card_id: Mapped[int] = mapped_column(
        ForeignKey("gift_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    gift_card: Mapped["GiftCard"] = relationship("GiftCard", back_populates="redemptions")
