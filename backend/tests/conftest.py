"""
Shared test fixtures.

Tests run against a real PostgreSQL database, not SQLite: the app relies on
dialect-specific behaviour (enums, JSON columns, `extract`) and a substituted
dialect would let bugs through that production would still hit.

Isolation strategy: one NullPool engine per test, schema truncated before each.
An earlier design shared a session-scoped engine, which deadlocked — a test
session left idle in a transaction blocked the next TRUNCATE, and the app's own
queries then queued behind that lock. Per-test engines cost a little startup
time and remove the whole class of problem.

Environment is configured before importing anything from `app`, because
`app.config` builds its Settings at import time.
"""
import os

# Must precede any `app.*` import.
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://nsh:nshpass@localhost:5433/nsh_test",
    ),
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-anywhere-else")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from datetime import time  # noqa: E402
from typing import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.booking_config import BookingConfig  # noqa: E402
from app.models.client import Client, ClientAccount  # noqa: E402
from app.models.collaborator import (  # noqa: E402
    Collaborator, CollaboratorSchedule, CollaboratorService,
)
from app.models.service import Service  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.utils.auth import hash_password  # noqa: E402

TEST_DATABASE_URL = os.environ["DATABASE_URL"]

ADMIN_PASSWORD = "admin-test-password"
COLLAB_PASSWORD = "collab-test-password"
CLIENT_PASSWORD = "client-test-password"

_schema_ready = False


async def _ensure_schema(engine: AsyncEngine) -> None:
    """Create the schema once per process."""
    global _schema_ready
    if _schema_ready:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    _schema_ready = True


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    await _ensure_schema(eng)
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    async with eng.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncIterator[AsyncSession]:
    """
    Session for test setup and assertions.

    Domain fixtures commit and never call `refresh()`: with
    `expire_on_commit=False` the ids are already populated, and a stray refresh
    would leave this session idle inside a transaction while the app is running.
    """
    # The context manager closes the session (discarding any open transaction);
    # an explicit rollback here would run after the connection is already gone.
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    """HTTP client wired to the app, with the DB dependency on the test database."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_celery(monkeypatch):
    """
    Neutralise the fire-and-forget Celery dispatch.

    The API only needs to enqueue; with no broker reachable the call would just
    log and continue, but stubbing it keeps tests fast and deterministic.
    """
    import app.api.admin.appointments as appointments_api

    monkeypatch.setattr(
        appointments_api, "_trigger_booking_confirmation", lambda appointment_id: None
    )


# ── Domain fixtures ───────────────────────────────────────────────


@pytest_asyncio.fixture
async def booking_config(db) -> BookingConfig:
    cfg = BookingConfig(
        is_enabled=True,
        min_advance_hours=2,
        max_advance_days=30,
        min_cancel_hours=24,
        slot_duration_minutes=30,
    )
    db.add(cfg)
    await db.commit()
    return cfg


@pytest_asyncio.fixture
async def admin_user(db) -> User:
    user = User(
        email="admin@nsh-test.it",
        password_hash=hash_password(ADMIN_PASSWORD),
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    return user


@pytest_asyncio.fixture
async def collaborator_user(db) -> User:
    user = User(
        email="collab@nsh-test.it",
        password_hash=hash_password(COLLAB_PASSWORD),
        role=UserRole.collaborator,
    )
    db.add(user)
    await db.commit()
    return user


@pytest_asyncio.fixture
async def service(db) -> Service:
    svc = Service(
        name="Taglio test",
        description="Servizio di prova",
        price=30.0,
        duration_slots=2,
        category="Taglio",
        bookable_online=True,
        is_active=True,
    )
    db.add(svc)
    await db.commit()
    return svc


@pytest_asyncio.fixture
async def collaborator(db, service) -> Collaborator:
    collab = Collaborator(
        first_name="Sofia",
        last_name="Test",
        phone="+393330000001",
        email="sofia@nsh-test.it",
        color="#C8A96E",
        visible_online=True,
        is_active=True,
    )
    db.add(collab)
    await db.flush()

    # Working Mon–Sat 09:00–19:00, closed Sunday.
    for day in range(6):
        db.add(CollaboratorSchedule(
            collaborator_id=collab.id, day_of_week=day,
            start_time=time(9, 0), end_time=time(19, 0), is_working=True,
        ))
    db.add(CollaboratorSchedule(
        collaborator_id=collab.id, day_of_week=6, is_working=False,
    ))
    db.add(CollaboratorService(collaborator_id=collab.id, service_id=service.id))

    await db.commit()
    return collab


@pytest_asyncio.fixture
async def unoffered_service(db) -> Service:
    """A bookable service the `collaborator` fixture does not perform."""
    svc = Service(
        name="Colore test",
        price=60.0,
        duration_slots=2,
        category="Colore",
        bookable_online=True,
        is_active=True,
    )
    db.add(svc)
    await db.commit()
    return svc


@pytest_asyncio.fixture
async def hidden_collaborator(db, service) -> Collaborator:
    """Performs the service, but is not published on the portal."""
    collab = Collaborator(
        first_name="Nascosta",
        last_name="Test",
        color="#888888",
        visible_online=False,
        is_active=True,
    )
    db.add(collab)
    await db.flush()
    for day in range(6):
        db.add(CollaboratorSchedule(
            collaborator_id=collab.id, day_of_week=day,
            start_time=time(9, 0), end_time=time(19, 0), is_working=True,
        ))
    db.add(CollaboratorService(collaborator_id=collab.id, service_id=service.id))
    await db.commit()
    return collab


@pytest_asyncio.fixture
async def client_account(db) -> ClientAccount:
    """A portal account with its linked Client record."""
    account = ClientAccount(
        email="cliente@nsh-test.it",
        password_hash=hash_password(CLIENT_PASSWORD),
        is_active=True,
    )
    db.add(account)
    await db.flush()
    db.add(Client(
        first_name="Giulia",
        last_name="Test",
        phone="+393330000002",
        email="cliente@nsh-test.it",
        account_id=account.id,
    ))
    await db.commit()
    return account


@pytest_asyncio.fixture
async def other_client(db) -> Client:
    """A second client with no portal account — used to prove cross-client isolation."""
    c = Client(
        first_name="Estranea",
        last_name="Test",
        phone="+393330000003",
        email="altra@nsh-test.it",
    )
    db.add(c)
    await db.commit()
    return c


# ── Token helpers ─────────────────────────────────────────────────


async def _login(http: AsyncClient, path: str, email: str, password: str) -> dict:
    resp = await http.post(path, json={"email": email, "password": password})
    assert resp.status_code == 200, f"login {email} failed: {resp.status_code} {resp.text}"
    return resp.json()


@pytest_asyncio.fixture
async def admin_tokens(client, admin_user) -> dict:
    return await _login(client, "/api/admin/auth/login", admin_user.email, ADMIN_PASSWORD)


@pytest_asyncio.fixture
async def collab_tokens(client, collaborator_user) -> dict:
    return await _login(client, "/api/admin/auth/login", collaborator_user.email, COLLAB_PASSWORD)


@pytest_asyncio.fixture
async def client_tokens(client, client_account) -> dict:
    return await _login(client, "/api/public/auth/login", client_account.email, CLIENT_PASSWORD)


def auth(tokens: dict) -> dict:
    """Authorization header from a token pair."""
    return {"Authorization": f"Bearer {tokens['access_token']}"}
