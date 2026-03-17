import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Enum, DateTime, Numeric, ForeignKey, func, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PaymentMethod(str, enum.Enum):
    cash = "contanti"
    card = "carta"
    mixed = "misto"


class PaymentType(str, enum.Enum):
    service = "servizio"
    product = "prodotto"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod), nullable=False)
    type: Mapped[PaymentType] = mapped_column(Enum(PaymentType), default=PaymentType.service, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="payments")
    appointment: Mapped[Optional["Appointment"]] = relationship("Appointment", back_populates="payments")
