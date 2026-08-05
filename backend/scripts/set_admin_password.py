"""
Set a staff account's password.

The password is read from a hidden prompt, never from argv or an env var, so it
does not end up in shell history, process listings or CI logs.

Usage:
    DATABASE_URL=postgresql://... python scripts/set_admin_password.py [email]

Defaults to admin@newstylair.it when no email is given.
"""
import asyncio
import getpass
import os
import sys

import asyncpg

from app.utils.auth import hash_password_sync

MIN_LENGTH = 12


async def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL non impostata", file=sys.stderr)
        return 1
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    email = sys.argv[1] if len(sys.argv) > 1 else "admin@newstylair.it"

    password = getpass.getpass(f"Nuova password per {email}: ")
    if len(password) < MIN_LENGTH:
        print(f"Troppo corta: almeno {MIN_LENGTH} caratteri.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Ripeti la password: "):
        print("Le password non coincidono.", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(url)
    try:
        row = await conn.fetchrow(
            "UPDATE users SET password_hash = $2 WHERE email = $1 RETURNING id, role",
            email,
            hash_password_sync(password),
        )
    finally:
        await conn.close()

    if not row:
        print(f"Nessun utente con email {email}", file=sys.stderr)
        return 1
    print(f"✓ Password aggiornata per {email} (id={row['id']}, {row['role']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
