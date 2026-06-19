from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def create_task_session_factory():
    """
    Build a throwaway engine + sessionmaker for a single Celery task run.

    Celery tasks spin up a fresh asyncio event loop per execution. The global
    `engine` pools connections bound to the loop that created them, so reusing
    it across runs raises "Event loop is closed" / "attached to a different
    loop". A NullPool engine opens (and closes) a connection within the current
    loop, avoiding cross-loop reuse. Caller must `await engine.dispose()`.
    """
    task_engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return task_engine, factory


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
