import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Enum, DateTime, Text, ForeignKey, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload
from app.database import Base


class AppointmentStatus(str, enum.Enum):
    pending = "pending"          # Online booking waiting for salon confirmation
    confirmed = "confirmed"      # Confirmed by salon
    rejected = "rejected"        # Rejected by salon
    rescheduled = "rescheduled"  # Salon proposed alternative time
    completed = "completed"      # Service done
    cancelled = "cancelled"      # Cancelled by client or salon


class AppointmentOrigin(str, enum.Enum):
    salon = "salon"    # Created by admin/collaborator
    online = "online"  # Created by client via portal


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("collaborators.id", ondelete="RESTRICT"), nullable=False
    )

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.confirmed, nullable=False
    )
    origin: Mapped[AppointmentOrigin] = mapped_column(
        Enum(AppointmentOrigin), default=AppointmentOrigin.salon, nullable=False
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Post-visit notes
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alternative_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whatsapp_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    client: Mapped["Client"] = relationship("Client", back_populates="appointments")
    collaborator: Mapped["Collaborator"] = relationship("Collaborator", back_populates="appointments")
    appointment_services: Mapped[List["AppointmentService"]] = relationship(
        "AppointmentService", back_populates="appointment", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="appointment")


class AppointmentService(Base):
    """Services included in an appointment (many-to-many with snapshot price)."""
    __tablename__ = "appointment_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    price_snapshot: Mapped[float] = mapped_column(nullable=False)  # Price at time of booking

    appointment: Mapped["Appointment"] = relationship("Appointment", back_populates="appointment_services")
    service: Mapped["Service"] = relationship("Service", back_populates="appointment_services")


def appointment_detail_loads():
    """Everything `AppointmentOutWithNames.from_appointment` reads, in one place.

    The projection walks client, collaborator and the service behind each booked
    line; a query that eager-loads less either raises MissingGreenlet under
    asyncio or quietly answers with an empty field. Keeping the pair together
    means adding a relationship to the projection is one edit here, and every
    endpoint that returns an appointment picks it up.

    A function and not a module constant: `selectinload` inspects the mapper,
    which configures the whole registry, and at import time of this module the
    later models are not defined yet — `Client.communications` would fail to
    resolve. Called from inside a request, everything is mapped.
    """
    return (
        selectinload(Appointment.client),
        selectinload(Appointment.collaborator),
        selectinload(Appointment.appointment_services).selectinload(AppointmentService.service),
    )
