"""
Production bootstrap — create initial admin user and booking config.
Idempotent: safe to run multiple times. No drops, no demo data.
Usage: python bootstrap.py
"""
import asyncio
import os
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.booking_config import BookingConfig
from app.utils.auth import hash_password


async def bootstrap():
    admin_email = os.getenv("ADMIN_EMAIL", "admin@newstylair.it")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

    async with AsyncSessionLocal() as db:
        # Admin user
        result = await db.execute(select(User).where(User.email == admin_email))
        if result.scalar_one_or_none() is None:
            db.add(User(
                email=admin_email,
                password_hash=hash_password(admin_password),
                role=UserRole.admin,
            ))
            print(f"✓ Admin creato: {admin_email}")
        else:
            print(f"• Admin già esistente: {admin_email}")

        # Default BookingConfig
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

        await db.commit()
    print("Bootstrap completato.")


if __name__ == "__main__":
    asyncio.run(bootstrap())
