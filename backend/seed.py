"""
Seed script – populates DB with realistic demo data.
Usage: python seed.py
"""
import asyncio
from datetime import datetime, date, time, timedelta, timezone
from app.database import AsyncSessionLocal, engine, Base
from app.models.user import User, UserRole
from app.models.client import Client, ClientAccount
from app.models.collaborator import Collaborator, CollaboratorSchedule, CollaboratorService
from app.models.service import Service
from app.models.appointment import Appointment, AppointmentService, AppointmentStatus, AppointmentOrigin
from app.models.product import Product, ProductMovement, MovementType
from app.models.payment import Payment, PaymentMethod, PaymentType
from app.models.expense import Expense
from app.models.booking_config import BookingConfig
from app.utils.auth import hash_password


async def seed():
    # Create all tables (dev only – use Alembic in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # ── BookingConfig ──────────────────────────────────────────
        cfg = BookingConfig(
            is_enabled=True,
            min_advance_hours=2,
            max_advance_days=30,
            min_cancel_hours=24,
            slot_duration_minutes=30,
        )
        db.add(cfg)

        # ── Admin user ─────────────────────────────────────────────
        admin = User(
            email="admin@newstylair.it",
            password_hash=hash_password("admin123"),
            role=UserRole.admin,
        )
        db.add(admin)

        # ── Services ───────────────────────────────────────────────
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
            s = Service(name=name, description=desc, price=price, duration_slots=slots, category=cat, bookable_online=online)
            db.add(s)
            services.append(s)

        # ── Collaborators ──────────────────────────────────────────
        collab_data = [
            ("Sofia", "Rossi", "+39 347 1234567", "sofia@newstylair.it", "#C8A96E", True),
            ("Marco", "Bianchi", "+39 347 7654321", "marco@newstylair.it", "#8BA888", True),
            ("Elena", "Ferretti", "+39 347 9988776", "elena@newstylair.it", "#A8B8C8", True),
        ]
        collaborators = []
        for fn, ln, phone, email, color, online in collab_data:
            c = Collaborator(
                first_name=fn, last_name=ln, phone=phone, email=email,
                color=color, visible_online=online, is_active=True
            )
            db.add(c)
            collaborators.append(c)

        await db.flush()

        # ── User for Sofia ─────────────────────────────────────────
        sofia_user = User(
            email="sofia@newstylair.it",
            password_hash=hash_password("sofia123"),
            role=UserRole.collaborator,
        )
        db.add(sofia_user)
        await db.flush()
        collaborators[0].user_id = sofia_user.id

        # ── Schedules (Mon–Sat 9:00–19:00, Sun off) ───────────────
        for collab in collaborators:
            for day in range(6):  # Mon–Sat
                db.add(CollaboratorSchedule(
                    collaborator_id=collab.id,
                    day_of_week=day,
                    start_time=time(9, 0),
                    end_time=time(19, 0),
                    is_working=True,
                ))
            db.add(CollaboratorSchedule(
                collaborator_id=collab.id,
                day_of_week=6,
                is_working=False,
            ))

        # ── Assign services to collaborators ───────────────────────
        # Sofia: all services
        for s in services:
            db.add(CollaboratorService(collaborator_id=collaborators[0].id, service_id=s.id))
        # Marco: taglio, piega, permanente
        for s in services[:2] + [services[4], services[6]]:
            db.add(CollaboratorService(collaborator_id=collaborators[1].id, service_id=s.id))
        # Elena: colore, trattamenti, styling
        for s in services[2:6] + [services[7]]:
            db.add(CollaboratorService(collaborator_id=collaborators[2].id, service_id=s.id))

        # ── Clients ────────────────────────────────────────────────
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
            ("Paolo", "Colombo", "+39 334 3333333", "paolo.colombo@email.it", date(1970, 7, 4)),
            ("Davide", "Russo", "+39 334 4444444", None, date(1996, 3, 16)),
            ("Matteo", "Bruno", "+39 334 5555555", "matteo.bruno@email.it", date(1989, 8, 9)),
        ]
        clients = []
        for fn, ln, phone, email, bday in clients_data:
            c = Client(
                first_name=fn, last_name=ln, phone=phone, email=email,
                birth_date=bday
            )
            db.add(c)
            clients.append(c)

        await db.flush()

        # ── Online account for first client ────────────────────────
        account = ClientAccount(
            email="giulia.marino@email.it",
            password_hash=hash_password("giulia123"),
            is_active=True,
        )
        db.add(account)
        await db.flush()
        clients[0].account_id = account.id

        # ── Past appointments ──────────────────────────────────────
        now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
        appts = []

        past_appts = [
            # (client_idx, collab_idx, days_ago, hour, service_idx, status)
            (0, 0, 14, 10, 0, AppointmentStatus.completed),
            (1, 2, 13, 11, 2, AppointmentStatus.completed),
            (2, 1, 12, 14, 1, AppointmentStatus.completed),
            (3, 0, 10, 9,  3, AppointmentStatus.completed),
            (4, 2, 9,  15, 4, AppointmentStatus.completed),
            (5, 1, 8,  10, 1, AppointmentStatus.completed),
            (6, 0, 7,  11, 5, AppointmentStatus.completed),
            (7, 2, 6,  14, 2, AppointmentStatus.completed),
            (8, 0, 5,  9,  0, AppointmentStatus.completed),
            (9, 1, 4,  16, 1, AppointmentStatus.completed),
            (10, 0, 3, 10, 1, AppointmentStatus.completed),
            (11, 2, 2, 11, 4, AppointmentStatus.completed),
        ]

        for ci, colli, days_ago, hour, si, appt_status in past_appts:
            start = (now - timedelta(days=days_ago)).replace(hour=hour, minute=0)
            svc = services[si]
            end = start + timedelta(minutes=svc.duration_slots * 30)
            a = Appointment(
                client_id=clients[ci].id,
                collaborator_id=collaborators[colli].id,
                start_time=start,
                end_time=end,
                status=appt_status,
                origin=AppointmentOrigin.salon,
                reminder_sent=True,
            )
            db.add(a)
            appts.append((a, svc))

        await db.flush()

        for a, svc in appts:
            db.add(AppointmentService(
                appointment_id=a.id,
                service_id=svc.id,
                price_snapshot=float(svc.price),
            ))
            if a.status == AppointmentStatus.completed:
                db.add(Payment(
                    client_id=a.client_id,
                    appointment_id=a.id,
                    amount=svc.price,
                    method=PaymentMethod.cash if a.id % 2 == 0 else PaymentMethod.card,
                    type=PaymentType.service,
                    date=a.end_time,
                ))

        # ── Future appointments ────────────────────────────────────
        future_appts = [
            (0, 0, 1, 10, 0, AppointmentStatus.confirmed, AppointmentOrigin.salon),
            (1, 2, 1, 14, 3, AppointmentStatus.confirmed, AppointmentOrigin.salon),
            (2, 1, 2, 11, 1, AppointmentStatus.confirmed, AppointmentOrigin.online),
            (3, 0, 2, 15, 5, AppointmentStatus.pending,   AppointmentOrigin.online),
            (4, 2, 3, 9,  4, AppointmentStatus.confirmed, AppointmentOrigin.salon),
            (5, 1, 3, 16, 1, AppointmentStatus.pending,   AppointmentOrigin.online),
        ]

        for ci, colli, days_ahead, hour, si, appt_status, origin in future_appts:
            start = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=0)
            svc = services[si]
            end = start + timedelta(minutes=svc.duration_slots * 30)
            a = Appointment(
                client_id=clients[ci].id,
                collaborator_id=collaborators[colli].id,
                start_time=start,
                end_time=end,
                status=appt_status,
                origin=origin,
            )
            db.add(a)
            await db.flush()
            db.add(AppointmentService(
                appointment_id=a.id,
                service_id=svc.id,
                price_snapshot=float(svc.price),
            ))

        # ── Products ───────────────────────────────────────────────
        products_data = [
            ("Shampoo Professionale Argan", "Shampoo nutriente all'olio di argan", 8.50, 22.00, "Shampoo", 15, 3),
            ("Maschera Ristrutturante", "Maschera per capelli danneggiati", 12.00, 28.00, "Trattamenti", 8, 2),
            ("Siero Anticrespo", "Siero fluido per capelli ribelli", 10.00, 25.00, "Styling", 12, 3),
            ("Lacca Fissante Forte", "Lacca a lunga tenuta", 5.00, 14.00, "Styling", 20, 5),
            ("Olio Nutriente", "Olio multi-uso per capelli e punte", 15.00, 35.00, "Trattamenti", 6, 2),
        ]
        for name, desc, pp, sp, cat, qty, minq in products_data:
            p = Product(
                name=name, description=desc, purchase_price=pp, sale_price=sp,
                category=cat, quantity=qty, min_quantity=minq
            )
            db.add(p)

        # ── Expenses ───────────────────────────────────────────────
        expenses_data = [
            ("Affitto salone", 1200.00, "Affitto", date.today().replace(day=1)),
            ("Forniture tinte", 350.00, "Forniture", date.today() - timedelta(days=5)),
            ("Utenza elettrica", 180.00, "Utenze", date.today() - timedelta(days=10)),
            ("Prodotti per rivendita", 420.00, "Acquisto prodotti", date.today() - timedelta(days=3)),
        ]
        for desc, amount, cat, exp_date in expenses_data:
            db.add(Expense(description=desc, amount=amount, category=cat, date=exp_date))

        await db.commit()
        print("✓ Seed completato con successo!")
        print("  Admin: admin@newstylair.it / admin123")
        print("  Sofia (collaboratrice): sofia@newstylair.it / sofia123")
        print("  Giulia (cliente online): giulia.marino@email.it / giulia123")


if __name__ == "__main__":
    asyncio.run(seed())
