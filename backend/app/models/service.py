from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    duration_slots: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # × 30 min
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    bookable_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    collaborators: Mapped[List["Collaborator"]] = relationship(
        "Collaborator", secondary="collaborator_services", back_populates="services"
    )
    appointment_services: Mapped[List["AppointmentService"]] = relationship(
        "AppointmentService", back_populates="service"
    )
