"""
Disable the seeded demo logins (staff + client portal).

The demo credentials are documented in the repository, so any environment that
is reachable from the internet must not keep them usable. This deactivates the
accounts rather than deleting them: `is_active=False` is enough to make both
the login endpoints and the auth dependencies reject them, and it leaves the
linked Collaborator/Client records — and their appointment history — intact.

Reversible: set is_active back to true to re-enable an account.

Usage:
    DATABASE_URL=postgresql://... python scripts/disable_demo_logins.py
"""
import asyncio
import os
import sys

import asyncpg

# Seeded accounts whose passwords are published in the repo.
DEMO_STAFF_EMAILS = ["sofia@newstylair.it"]
DEMO_CLIENT_EMAILS = ["giulia.marino@email.it"]


async def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL non impostata", file=sys.stderr)
        return 1
    # asyncpg speaks plain postgres URLs, not SQLAlchemy's +asyncpg dialect form.
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(url)
    try:
        for email in DEMO_STAFF_EMAILS:
            row = await conn.fetchrow(
                "UPDATE users SET is_active = false WHERE email = $1 RETURNING id, role",
                email,
            )
            if row:
                print(f"✓ staff  {email} → disattivato (id={row['id']}, {row['role']})")
            else:
                print(f"• staff  {email} → non trovato")

        for email in DEMO_CLIENT_EMAILS:
            row = await conn.fetchrow(
                "UPDATE client_accounts SET is_active = false WHERE email = $1 RETURNING id",
                email,
            )
            if row:
                print(f"✓ client {email} → disattivato (id={row['id']})")
            else:
                print(f"• client {email} → non trovato")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
