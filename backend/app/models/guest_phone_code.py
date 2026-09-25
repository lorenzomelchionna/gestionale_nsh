from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GuestPhoneCode(Base):
    """Il codice WhatsApp di chi prenota dal portale senza account.

    Stessa forma dei campi `phone_verification_*` su `ClientAccount`, ma
    appesa al numero invece che a un account, perché qui un account non
    c'è: una riga per numero, riscritta a ogni nuovo codice.

    Le ultime tre colonne servono al tetto sui rinvii. Mandare un codice
    costa un messaggio WhatsApp e arriva sul telefono di chi il numero lo
    possiede davvero: senza un limite per numero, chiunque potrebbe
    tempestare di codici il telefono di un'altra persona, a spese del salone.
    """
    __tablename__ = "guest_phone_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)

    code_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    window_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sends_in_window: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
