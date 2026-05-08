"""
Production bootstrap — create initial admin user and booking config.
Idempotent: safe to run multiple times. No drops.

Set SEED_DEMO=true to also populate demo data (services, collaborators,
clients, appointments, products, expenses) ONCE. Idempotent: skips if
data already exists. Remove the env var after first successful run.

Usage: python bootstrap.py
"""
import asyncio
import os
from datetime import datetime, date, time, timedelta, timezone
from sqlalchemy import select, func
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.booking_config import BookingConfig
from app.models.service import Service
from app.models.collaborator import Collaborator, CollaboratorSchedule, CollaboratorService
from app.models.client import Client, ClientAccount
from app.models.appointment import Appointment, AppointmentService, AppointmentStatus, AppointmentOrigin
from app.models.product import Product
from app.models.payment import Payment, PaymentMethod, PaymentType
from app.models.expense import Expense
from app.utils.auth import hash_password


async def ensure_admin(db, email, password):
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none() is None:
        db.add(User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.admin,
        ))
        print(f"✓ Admin creato: {email}")
    else:
        print(f"• Admin già esistente: {email}")


async def ensure_booking_config(db):
    result = await db.execute(select(BookingConfig))
    if result.scalar_one_or_none() is None:
        db.add(BookingConfig(
            is_enabled=True,
            min_advance_hours=2,
            max_advance_days=30,
            min_cancel_hours=24,
            slot_duration_minutes=30,
        ))
        print("✓ BookingConfig creata")
    else:
        print("• BookingConfig già esistente")


async def seed_demo(db):
    # Skip se ci sono già servizi
    count = await db.scalar(select(func.count()).select_from(Service))
    if count and count > 0:
        print(f"• Demo data già presente ({count} servizi) — skip")
        return

    print("→ Popolamento demo data...")

    # Services
    services_data = [
        ("Taglio donna", "Taglio e piega", 35.0, 2, "Taglio", True),
        ("Taglio uomo", "Taglio classico o moderno", 20.0, 1, "Taglio", True),
        ("Colore base", "Colorazione uniforme", 55.0, 4, "Colore", True),
        ("Colore con mèches", "Mèches e schiariture", 75.0, 6, "Colore", True),
        ("Piega", "Asciugatura e messa in piega", 20.0, 1, "Styling", True),
        ("Trattamento cheratina", "Lisciatura semipermanente", 120.0, 6, "Trattamenti", True),
        ("Permanente", "Ricci permanenti", 70.0, 5, "Trattamenti", False),
        ("Colore specialistico", "Balayage, ombre o colori creativi", 95.0, 8, "Colore", False),
    ]
    services = []
    for name, desc, price, slots, cat, online in services_data:
        s = Service(name=name, description=desc, price=price,
                    duration_slots=slots, category=cat, bookable_online=online)
        db.add(s)
        services.append(s)

    # Collaborators
    collab_data = [
        ("Sofia", "Rossi", "+39 347 1234567", "sofia@newstylair.it", "#C8A96E", True),
        ("Marco", "Bianchi", "+39 347 7654321", "marco@newstylair.it", "#8BA888", True),
        ("Elena", "Ferretti", "+39 347 9988776", "elena@newstylair.it", "#A8B8C8", True),
    ]
    collaborators = []
    for fn, ln, phone, email, color, online in collab_data:
        c = Collaborator(first_name=fn, last_name=ln, phone=phone, email=email,
                         color=color, visible_online=online, is_active=True)
        db.add(c)
        collaborators.append(c)
    await db.flush()

    # Sofia user
    sofia_user = User(
        email="sofia@newstylair.it",
        password_hash=hash_password("sofia123"),
        role=UserRole.collaborator,
    )
    db.add(sofia_user)
    await db.flush()
    collaborators[0].user_id = sofia_user.id

    # Schedules Mon–Sat 9–19
    for collab in collaborators:
        for day in range(6):
            db.add(CollaboratorSchedule(
                collaborator_id=collab.id, day_of_week=day,
                start_time=time(9, 0), end_time=time(19, 0), is_working=True,
            ))
        db.add(CollaboratorSchedule(
            collaborator_id=collab.id, day_of_week=6, is_working=False,
        ))

    # Service assignments
    for s in services:
        db.add(CollaboratorService(collaborator_id=collaborators[0].id, service_id=s.id))
    for s in services[:2] + [services[4], services[6]]:
        db.add(CollaboratorService(collaborator_id=collaborators[1].id, service_id=s.id))
    for s in services[2:6] + [services[7]]:
        db.add(CollaboratorService(collaborator_id=collaborators[2].id, service_id=s.id))

    # Clients
    clients_data = [
        ("Giulia", "Marino", "+39 333 1111111", "giulia.marino@email.it", date(1990, 5, 14)),
        ("Francesca", "Conti", "+39 333 2222222", "francesca.conti@email.it", date(1985, 8, 22)),
        ("Laura", "Ricci", "+39 333 3333333", None, date(1995, 3, 7)),
        ("Martina", "De Luca", "+39 333 4444444", "martina.deluca@email.it", date(1988, 11, 30)),
        ("Sara", "Esposito", "+39 333 5555555", None, date(1992, 7, 18)),
        ("Valentina", "Greco", "+39 333 6666666", "valentina.greco@email.it", date(1983, 1, 25)),
        ("Anna", "Lombardi", "+39 333 7777777", "anna.lombardi@email.it", date(1975, 9, 12)),
        ("Chiara", "Moretti", "+39 333 8888888", None, date(1998, 4, 3)),
        ("Alessia", "Barbieri", "+39 333 9999999", "alessia.barbieri@email.it", date(1991, 6, 27)),
        ("Roberta", "Fontana", "+39 333 0000000", None, date(1980, 12, 15)),
        ("Luca", "Ferrari", "+39 334 1111111", "luca.ferrari@email.it", date(1987, 2, 8)),
        ("Andrea", "Romano", "+39 334 2222222", None, date(1993, 10, 21)),
    ]
    clients = []
    for fn, ln, phone, email, bday in clients_data:
        c = Client(first_name=fn, last_name=ln, phone=phone, email=email, birth_date=bday)
        db.add(c)
        clients.append(c)
    await db.flush()

    # Online account for Giulia
    account = ClientAccount(
        email="giulia.marino@email.it",
        password_hash=hash_password("giulia123"),
        is_active=True,
    )
    db.add(account)
    await db.flush()
    clients[0].account_id = account.id

    # Past appointments
    now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    past = [
        (0, 0, 14, 10, 0), (1, 2, 13, 11, 2), (2, 1, 12, 14, 1),
        (3, 0, 10, 9, 3),  (4, 2, 9, 15, 4),  (5, 1, 8, 10, 1),
        (6, 0, 7, 11, 5),  (7, 2, 6, 14, 2),  (8, 0, 5, 9, 0),
        (9, 1, 4, 16, 1),  (10, 0, 3, 10, 1), (11, 2, 2, 11, 4),
    ]
    appts = []
    for ci, colli, days_ago, hour, si in past:
        start = (now - timedelta(days=days_ago)).replace(hour=hour, minute=0)
        svc = services[si]
        end = start + timedelta(minutes=svc.duration_slots * 30)
        a = Appointment(
            client_id=clients[ci].id, collaborator_id=collaborators[colli].id,
            start_time=start, end_time=end,
            status=AppointmentStatus.completed,
            origin=AppointmentOrigin.salon, reminder_sent=True,
        )
        db.add(a)
        appts.append((a, svc))
    await db.flush()
    for a, svc in appts:
        db.add(AppointmentService(
            appointment_id=a.id, service_id=svc.id, price_snapshot=float(svc.price),
        ))
        db.add(Payment(
            client_id=a.client_id, appointment_id=a.id,
            amount=svc.price,
            method=PaymentMethod.cash if a.id % 2 == 0 else PaymentMethod.card,
            type=PaymentType.service, date=a.end_time,
        ))

    # Future appointments
    future = [
        (0, 0, 1, 10, 0, AppointmentStatus.confirmed, AppointmentOrigin.salon),
        (1, 2, 1, 14, 3, AppointmentStatus.confirmed, AppointmentOrigin.salon),
        (2, 1, 2, 11, 1, AppointmentStatus.confirmed, AppointmentOrigin.online),
        (3, 0, 2, 15, 5, AppointmentStatus.pending,   AppointmentOrigin.online),
        (4, 2, 3, 9, 4,  AppointmentStatus.confirmed, AppointmentOrigin.salon),
        (5, 1, 3, 16, 1, AppointmentStatus.pending,   AppointmentOrigin.online),
    ]
    for ci, colli, days_ahead, hour, si, st, origin in future:
        start = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=0)
        svc = services[si]
        end = start + timedelta(minutes=svc.duration_slots * 30)
        a = Appointment(
            client_id=clients[ci].id, collaborator_id=collaborators[colli].id,
            start_time=start, end_time=end, status=st, origin=origin,
        )
        db.add(a)
        await db.flush()
        db.add(AppointmentService(
            appointment_id=a.id, service_id=svc.id, price_snapshot=float(svc.price),
        ))

    # Products
    products_data = [
        ("Shampoo Professionale Argan", "Shampoo nutriente all'olio di argan", 8.50, 22.00, "Shampoo", 15, 3),
        ("Maschera Ristrutturante", "Maschera per capelli danneggiati", 12.00, 28.00, "Trattamenti", 8, 2),
        ("Siero Anticrespo", "Siero fluido per capelli ribelli", 10.00, 25.00, "Styling", 12, 3),
        ("Lacca Fissante Forte", "Lacca a lunga tenuta", 5.00, 14.00, "Styling", 20, 5),
        ("Olio Nutriente", "Olio multi-uso per capelli e punte", 15.00, 35.00, "Trattamenti", 6, 2),
    ]
    for name, desc, pp, sp, cat, qty, minq in products_data:
        db.add(Product(
            name=name, description=desc, purchase_price=pp, sale_price=sp,
            category=cat, quantity=qty, min_quantity=minq,
        ))

    # Expenses
    expenses_data = [
        ("Affitto salone", 1200.00, "Affitto", date.today().replace(day=1)),
        ("Forniture tinte", 350.00, "Forniture", date.today() - timedelta(days=5)),
        ("Utenza elettrica", 180.00, "Utenze", date.today() - timedelta(days=10)),
        ("Prodotti per rivendita", 420.00, "Acquisto prodotti", date.today() - timedelta(days=3)),
    ]
    for desc, amount, cat, exp_date in expenses_data:
        db.add(Expense(description=desc, amount=amount, category=cat, date=exp_date))

    print("✓ Demo data popolato")


async def bootstrap():
    admin_email = os.getenv("ADMIN_EMAIL", "admin@newstylair.it")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    seed_flag = os.getenv("SEED_DEMO", "").lower() in ("true", "1", "yes")

    async with AsyncSessionLocal() as db:
        await ensure_admin(db, admin_email, admin_password)
        await ensure_booking_config(db)
        if seed_flag:
            await seed_demo(db)
        await db.commit()
    print("Bootstrap completato.")


if __name__ == "__main__":
    asyncio.run(bootstrap())
