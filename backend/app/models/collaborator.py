from datetime import datetime, time
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Time, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CollaboratorService(Base):
    """Many-to-many: which services a collaborator can perform."""
    __tablename__ = "collaborator_services"

    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("collaborators.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    )


class Collaborator(Base):
    __tablename__ = "collaborators"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visible_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#C8A96E", nullable=False)

    # Optional link to a User account
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    schedules: Mapped[List["CollaboratorSchedule"]] = relationship(
        "CollaboratorSchedule", back_populates="collaborator", cascade="all, delete-orphan"
    )
    absences: Mapped[List["Absence"]] = relationship(
        "Absence", back_populates="collaborator", cascade="all, delete-orphan"
    )
    extra_days: Mapped[List["CollaboratorExtraDay"]] = relationship(
        "CollaboratorExtraDay", back_populates="collaborator", cascade="all, delete-orphan"
    )
    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment", back_populates="collaborator"
    )
    services: Mapped[List["Service"]] = relationship(
        "Service", secondary="collaborator_services", back_populates="collaborators"
    )


class CollaboratorSchedule(Base):
    """Weekly working hours for a collaborator."""
    __tablename__ = "collaborator_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("collaborators.id", ondelete="CASCADE"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon … 6=Sun
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    is_working: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    collaborator: Mapped["Collaborator"] = relationship("Collaborator", back_populates="schedules")
