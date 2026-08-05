from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.audit import accesso_negato, imposta_attore, token_rifiutato
from app.database import get_db
from app.models.user import User, UserRole
from app.models.client import ClientAccount
from app.utils.auth import decode_token

bearer_scheme = HTTPBearer()

# Staff and client tokens are signed with the same key, and `sub` is an id from
# a different table in each case (users vs client_accounts). Without checking
# which audience a token was minted for, a client token whose account id happens
# to match a staff user id authenticates as that user — so every dependency
# below must assert the audience, not just the signature.
CLIENT_TOKEN_TYPE = "client"


# Qui non si scrive mai il token, nemmeno un pezzo. Il motivo del rifiuto sì:
# è quello che distingue «una sessione è scaduta» da «qualcuno sta provando a
# entrare da una porta che non è la sua».


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None or payload.get("sub") is None:
        token_rifiutato(motivo="firma_o_scadenza")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
    # Reject client tokens: their `sub` indexes client_accounts, not users.
    if payload.get("type") == CLIENT_TOKEN_TYPE:
        # Il più interessante dei tre: un token cliente presentato a una rotta
        # dello staff è la forma esatta della escalation cliente→admin che
        # questo codice ha già avuto una volta. Se ricompare nei log, si sta
        # guardando qualcuno che ci prova.
        token_rifiutato(motivo="token_cliente_su_rotta_staff")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
    # Refresh tokens may only be exchanged at /auth/refresh, never used as access.
    if payload.get("refresh"):
        token_rifiutato(motivo="refresh_usato_come_access")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")

    user_id: int = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        # Un token ancora valido su un account chiuso: la firma regge fino a
        # scadenza, quindi disattivare qualcuno non gli toglie il token di
        # mano. Vale la pena vedere quante volte torna.
        token_rifiutato(
            motivo="utente_assente" if user is None else "utente_disattivato"
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utente non trovato")

    imposta_attore(user.role.value if hasattr(user.role, "value") else str(user.role), user.id)
    return user


async def require_admin(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != UserRole.admin:
        # Un collaboratore su una rotta da admin. Il più delle volte è un link
        # salvato o un pulsante che non doveva essere lì; è comunque il caso in
        # cui qualcuno di interno prova ad andare oltre i propri permessi, che
        # è la categoria che nessuno guarda mai.
        accesso_negato(motivo="serve_admin", percorso=request.url.path)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accesso riservato agli admin")
    return current_user


async def get_current_client(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientAccount:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None or payload.get("sub") is None or payload.get("type") != CLIENT_TOKEN_TYPE:
        token_rifiutato(motivo="non_valido_per_il_portale")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
    if payload.get("refresh"):
        token_rifiutato(motivo="refresh_usato_come_access")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")

    account_id: int = int(payload["sub"])
    result = await db.execute(select(ClientAccount).where(ClientAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None or not account.is_active:
        token_rifiutato(
            motivo="account_assente" if account is None else "account_disattivato"
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account non trovato")

    imposta_attore("client", account.id)
    return account
