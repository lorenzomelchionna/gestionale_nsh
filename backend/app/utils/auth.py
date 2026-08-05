from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from fastapi.concurrency import run_in_threadpool
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password_sync(password: str) -> str:
    """bcrypt puro. **Solo fuori da un event loop**: script, seed, bootstrap.

    Bcrypt è lento di proposito — è quello che lo rende utile — e occupa la
    CPU per un paio di decimi di secondo. Chiamato dentro un handler async
    quel tempo non è "una richiesta lenta": è l'intero event loop fermo, cioè
    tutta l'API che non risponde a nessuno. Con più tentativi di login in
    fila il gestionale si pianta mentre in salone qualcuno sta lavorando.

    Dentro una richiesta si usano le due versioni `async` qui sotto.
    """
    return pwd_context.hash(password)


def verify_password_sync(plain: str, hashed: str) -> bool:
    """Vedi `hash_password_sync`: solo fuori da un event loop."""
    return pwd_context.verify(plain, hashed)


async def hash_password(password: str) -> str:
    """Le versioni che usano gli handler: bcrypt in un thread a parte.

    Portano il nome breve di proposito. Chi scrive un endpoint nuovo digita
    `hash_password` senza pensarci, e ottiene quella giusta; se dimentica
    l'`await` si ritrova una coroutine al posto dell'hash e se ne accorge
    subito, invece di rallentare in silenzio tutta l'applicazione.
    """
    return await run_in_threadpool(pwd_context.hash, password)


async def verify_password(plain: str, hashed: str) -> bool:
    return await run_in_threadpool(pwd_context.verify, plain, hashed)


def create_access_token(subject: Any, extra: dict | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(subject), "exp": expire, **(extra or {})}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: Any, extra: dict | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(subject), "exp": expire, "refresh": True, **(extra or {})}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
