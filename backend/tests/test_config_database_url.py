"""`DATABASE_URL` come la dà Railway, senza driver.

Dal 2026-11-10 backend e worker la leggono come riferimento a quella del
servizio Postgres (`${{Postgres.DATABASE_URL}}`), così una password
rigenerata arriva da sola ai servizi. Quell'indirizzo comincia con
`postgresql://`: SQLAlchemy lo aprirebbe con psycopg2, che non c'è, e l'app
non partirebbe.
"""
import pytest

from app.config import Settings

URL = "utente:segreto@postgres.railway.internal:5432/railway"


@pytest.mark.parametrize("prefisso", ["postgresql://", "postgres://"])
def test_senza_driver_prende_asyncpg(monkeypatch, prefisso):
    monkeypatch.setenv("DATABASE_URL", prefisso + URL)
    assert Settings().DATABASE_URL == "postgresql+asyncpg://" + URL


def test_col_driver_resta_com_e(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://" + URL)
    assert Settings().DATABASE_URL == "postgresql+asyncpg://" + URL


@pytest.mark.parametrize("dentro", ["postgresql://", "postgres://"])
def test_solo_il_prefisso(monkeypatch, dentro):
    """Una password che contiene lo stesso prefisso non si tocca."""
    monkeypatch.setenv("DATABASE_URL", f"postgresql://u:x{dentro}y@h:5432/d")
    assert Settings().DATABASE_URL == f"postgresql+asyncpg://u:x{dentro}y@h:5432/d"
