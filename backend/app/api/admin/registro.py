"""Il registro dei messaggi inviati, per la pagina «Registro messaggi».

Solo admin (decisione di Lorenzo, 2026-11-20): numeri, indirizzi e testi di
tutte le clienti in un posto solo, come Cassa e Impostazioni.
"""
import re
from datetime import date, timedelta, time
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.client import Client
from app.models.registro_messaggi import RegistroMessaggio
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.registro import VoceRegistro
from app.services.registro import TIPI
from app.utils.tempo import istante

router = APIRouter(prefix="/registro-messaggi", tags=["Registro messaggi"])


@router.get("/tipi", response_model=dict[str, str])
async def tipi(current_user: Annotated[User, Depends(require_admin)]):
    """I tipi di messaggio con l'etichetta leggibile, per il filtro."""
    return TIPI


@router.get("", response_model=PaginatedResponse[VoceRegistro])
async def elenco(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    cerca: str = Query("", max_length=100, description="Nome, numero, email o oggetto"),
    dal: Optional[date] = Query(None, description="Giorno del salone, compreso"),
    al: Optional[date] = Query(None, description="Giorno del salone, compreso"),
    canale: Optional[str] = Query(None, pattern="^(email|whatsapp)$"),
    tipo: Optional[str] = Query(None, max_length=40),
    stato: Optional[str] = Query(None, max_length=20),
    client_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    q = select(RegistroMessaggio, Client).outerjoin(Client, Client.id == RegistroMessaggio.client_id)

    termine = cerca.strip()
    if termine:
        like = f"%{termine}%"
        condizioni = [
            RegistroMessaggio.destinatario.ilike(like),
            RegistroMessaggio.oggetto.ilike(like),
            Client.first_name.ilike(like),
            Client.last_name.ilike(like),
            (Client.first_name + " " + Client.last_name).ilike(like),
        ]
        # «333 123 4567» deve trovare «+393331234567», e anche un numero
        # salvato con gli spazi: si confrontano solo le cifre, da tutte e due
        # le parti.
        cifre = re.sub(r"\D", "", termine)
        if len(cifre) >= 5:
            condizioni.append(
                func.regexp_replace(RegistroMessaggio.destinatario, r"\D", "", "g").like(f"%{cifre}%")
            )
        q = q.where(or_(*condizioni))

    # Giorni del salone, non UTC: «i messaggi del 24» sono quelli partiti fra
    # la mezzanotte e la mezzanotte di Melito, non di Greenwich.
    if dal:
        q = q.where(RegistroMessaggio.creato_il >= istante(dal, time(0, 0)))
    if al:
        q = q.where(RegistroMessaggio.creato_il < istante(al + timedelta(days=1), time(0, 0)))
    if canale:
        q = q.where(RegistroMessaggio.canale == canale)
    if tipo:
        q = q.where(RegistroMessaggio.tipo == tipo)
    if stato:
        q = q.where(RegistroMessaggio.stato == stato)
    if client_id is not None:
        q = q.where(RegistroMessaggio.client_id == client_id)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    righe = (await db.execute(
        q.order_by(RegistroMessaggio.creato_il.desc(), RegistroMessaggio.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()

    items = [
        VoceRegistro(
            id=r.id, creato_il=r.creato_il, canale=r.canale, tipo=r.tipo,
            tipo_etichetta=TIPI.get(r.tipo, r.tipo), destinatario=r.destinatario,
            client_id=r.client_id,
            cliente_nome=f"{c.first_name} {c.last_name}".strip() if c else None,
            appointment_id=r.appointment_id, oggetto=r.oggetto, testo=r.testo,
            formato=r.formato, stato=r.stato, errore=r.errore,
            stato_aggiornato_il=r.stato_aggiornato_il,
        )
        for r, c in righe
    ]
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=-(-total // page_size),
    )
