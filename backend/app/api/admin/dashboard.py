from typing import Annotated
from datetime import datetime, date, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, extract
from app.database import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.payment import Payment, PaymentMethod, PaymentType
from app.models.expense import Expense
from app.models.user import User
from app.dependencies import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    period: str = Query("today", regex="^(today|week|month|year)$"),
):
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59)
    elif period == "week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)
        end = now
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0)
        end = now
    else:  # year
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now

    # Payments in period
    pay_result = await db.execute(
        select(Payment).where(and_(Payment.date >= start, Payment.date <= end))
    )
    payments = pay_result.scalars().all()

    total_revenue = sum(float(p.amount) for p in payments)
    cash_revenue = sum(float(p.amount) for p in payments if p.method == PaymentMethod.cash)
    card_revenue = sum(float(p.amount) for p in payments if p.method == PaymentMethod.card)
    service_revenue = sum(float(p.amount) for p in payments if p.type == PaymentType.service)
    product_revenue = sum(float(p.amount) for p in payments if p.type == PaymentType.product)

    # Expenses in period
    exp_result = await db.execute(
        select(func.sum(Expense.amount)).where(
            and_(Expense.date >= start.date(), Expense.date <= end.date())
        )
    )
    total_expenses = float(exp_result.scalar_one() or 0)

    # Appointment counts
    appt_result = await db.execute(
        select(func.count()).select_from(Appointment).where(
            and_(
                Appointment.start_time >= start,
                Appointment.start_time <= end,
                Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.completed])
            )
        )
    )
    appointment_count = appt_result.scalar_one()

    # Pending count
    pending_result = await db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.status == AppointmentStatus.pending
        )
    )
    pending_count = pending_result.scalar_one()

    return {
        "period": period,
        "total_revenue": total_revenue,
        "cash_revenue": cash_revenue,
        "card_revenue": card_revenue,
        "service_revenue": service_revenue,
        "product_revenue": product_revenue,
        "total_expenses": total_expenses,
        "net_margin": total_revenue - total_expenses,
        "appointment_count": appointment_count,
        "pending_appointments": pending_count,
    }


@router.get("/revenue-chart")
async def revenue_chart(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int = Query(30, ge=7, le=365),
):
    """Daily revenue for the last N days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    result = await db.execute(
        select(
            func.date(Payment.date).label("day"),
            func.sum(Payment.amount).label("total"),
        )
        .where(and_(Payment.date >= start, Payment.date <= end))
        .group_by(func.date(Payment.date))
        .order_by(func.date(Payment.date))
    )
    rows = result.all()
    return [{"date": str(r.day), "total": float(r.total)} for r in rows]


@router.get("/yearly-chart")
async def yearly_chart(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    year: int = Query(default=None),
):
    """Monthly revenue, expenses and appointment count for a given year."""
    now = datetime.now(timezone.utc)
    target_year = year or now.year

    # Monthly revenue
    rev_result = await db.execute(
        select(
            extract("month", Payment.date).label("month"),
            func.sum(Payment.amount).label("revenue"),
        )
        .where(extract("year", Payment.date) == target_year)
        .group_by(extract("month", Payment.date))
        .order_by(extract("month", Payment.date))
    )
    rev_rows = {int(r.month): float(r.revenue) for r in rev_result.all()}

    # Monthly expenses
    exp_result = await db.execute(
        select(
            extract("month", Expense.date).label("month"),
            func.sum(Expense.amount).label("expenses"),
        )
        .where(extract("year", Expense.date) == target_year)
        .group_by(extract("month", Expense.date))
        .order_by(extract("month", Expense.date))
    )
    exp_rows = {int(r.month): float(r.expenses) for r in exp_result.all()}

    # Monthly appointments
    appt_result = await db.execute(
        select(
            extract("month", Appointment.start_time).label("month"),
            func.count().label("count"),
        )
        .where(
            and_(
                extract("year", Appointment.start_time) == target_year,
                Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.completed]),
            )
        )
        .group_by(extract("month", Appointment.start_time))
        .order_by(extract("month", Appointment.start_time))
    )
    appt_rows = {int(r.month): int(r.count) for r in appt_result.all()}

    MONTH_NAMES = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
                   "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

    return [
        {
            "month": MONTH_NAMES[m - 1],
            "month_num": m,
            "revenue": rev_rows.get(m, 0.0),
            "expenses": exp_rows.get(m, 0.0),
            "net_margin": rev_rows.get(m, 0.0) - exp_rows.get(m, 0.0),
            "appointments": appt_rows.get(m, 0),
        }
        for m in range(1, 13)
    ]
