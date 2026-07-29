"""
Rewrite stored client phone numbers to E.164.

New and edited clients are normalised by the schema validator, but rows written
before that existed keep whatever was typed. Those rows are the ones that split
into a duplicate when the same person registers online, and that WhatsApp
cannot match to a conversation, so they need rewriting once.

Reports what it would change and exits without touching anything unless --apply
is given. Numbers that are already canonical are left alone, so re-running is
harmless.

Usage:
    DATABASE_URL=postgresql://... python scripts/normalise_client_phones.py
    DATABASE_URL=postgresql://... python scripts/normalise_client_phones.py --apply
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

# Running a file inside scripts/ puts scripts/ on the path, not the backend
# root, so the shared rule has to be made importable rather than copied here —
# a second implementation would drift from the one the API applies.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.phone import InvalidPhoneNumber, to_e164  # noqa: E402


async def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL non impostata", file=sys.stderr)
        return 1
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    apply_changes = "--apply" in sys.argv

    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT id, first_name, last_name, phone FROM clients "
            "WHERE phone IS NOT NULL AND phone <> '' ORDER BY id"
        )

        changes: list[tuple[int, str, str]] = []
        unusable: list[tuple[int, str, str]] = []

        for row in rows:
            name = f"{row['first_name']} {row['last_name']}"
            try:
                normalised = to_e164(row["phone"])
            except InvalidPhoneNumber:
                unusable.append((row["id"], name, row["phone"]))
                continue
            if normalised and normalised != row["phone"]:
                changes.append((row["id"], name, normalised))

        print(f"Clienti con telefono: {len(rows)}")
        print(f"Da normalizzare:      {len(changes)}")
        print(f"Non interpretabili:   {len(unusable)}")

        for cid, name, new in changes:
            old = next(r["phone"] for r in rows if r["id"] == cid)
            print(f"  #{cid:<4} {name:<28} {old!r} → {new!r}")

        # Left untouched on purpose: a human has to decide what these were meant
        # to be, and guessing would attach a real client to a wrong number.
        for cid, name, raw in unusable:
            print(f"  ⚠  #{cid:<4} {name:<28} {raw!r} — da correggere a mano")

        if not changes:
            print("\nNiente da fare.")
            return 0

        if not apply_changes:
            print("\nDry run. Rilancia con --apply per scrivere.")
            return 0

        async with conn.transaction():
            for cid, _, new in changes:
                await conn.execute(
                    "UPDATE clients SET phone = $2 WHERE id = $1", cid, new
                )
        print(f"\n{len(changes)} numeri aggiornati.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
