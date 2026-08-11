import logging
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.audit import RESET_ESEGUITO, evento
from app.database import get_db
from app.logging_config import maschera_email
from app.models.client import Client, ClientAccount
from app.models.appointment import Appointment, appointment_detail_loads
from app.models.user import User
from app.schemas.client import (
    AdminPasswordReset, ClientCreate, ClientUpdate, ClientOut, MergePreview, MergeRequest,
)
from app.schemas.appointment import AppointmentOutWithNames
from app.schemas.common import PaginatedResponse
from app.dependencies import get_current_user, require_admin
from app.services import client_merge
from app.utils.auth import hash_password

router = APIRouter(prefix="/clients", tags=["Clients"])

log = logging.getLogger("nsh.clienti")


def _anteprima_in_schema(a: client_merge.Anteprima) -> MergePreview:
    return MergePreview(
        source=ClientOut.model_validate(a.origine),
        target=ClientOut.model_validate(a.destinazione),
        moved=a.conteggi,
        filled_fields=a.campi_riempiti,
        notes_merged=a.note_unite,
        account_moved=a.account_spostato,
        total_rows=a.righe_totali,
    )


@router.get("", response_model=PaginatedResponse[ClientOut])
async def list_clients(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: str = Query(""),
):
    q = select(Client).where(Client.is_active == True)
    if search:
        term = f"%{search}%"
        q = q.where(
            or_(
                Client.first_name.ilike(term),
                Client.last_name.ilike(term),
                Client.phone.ilike(term),
                Client.email.ilike(term),
            )
        )

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    return PaginatedResponse(
        items=[ClientOut.model_validate(c) for c in result.scalars().all()],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size),
    )


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    client = Client(**payload.model_dump())
    db.add(client)
    await db.flush()
    await db.refresh(client)
    return ClientOut.model_validate(client)


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    return ClientOut.model_validate(client)


@router.put("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: int,
    payload: ClientUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await db.flush()
    return ClientOut.model_validate(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    client.is_active = False


@router.get("/{client_id}/merge-preview", response_model=MergePreview)
async def preview_merge(
    client_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    source_id: int = Query(..., description="La scheda che verrà svuotata"),
):
    """Cosa comporterebbe unire `source_id` dentro `client_id`. Non tocca niente."""
    try:
        anteprima = await client_merge.prepara(db, client_id, source_id)
    except client_merge.MergeRefused as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _anteprima_in_schema(anteprima)


@router.post("/{client_id}/merge", response_model=MergePreview)
async def merge_clients(
    client_id: int,
    payload: MergeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Unisce due schede: `source_id` confluisce in `client_id`, che resta.

    `require_admin` e non `get_current_user`: sposta appuntamenti, incassi e
    buoni regalo fra due persone e non si annulla. È della stessa famiglia di
    `POST /api/admin/clients`, che è già admin — non di `GET`, che è staff.
    """
    try:
        esito = await client_merge.esegui(db, client_id, payload.source_id)
    except client_merge.MergeRefused as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Il singolo passaggio di questo codice in cui i dati di una persona
    # diventano quelli di un'altra. Se un domani una cliente si ritrova
    # appuntamenti che non sono i suoi, questa riga dice quando è successo,
    # fra quali schede, e quale operatore l'ha chiesto — `attore` lo mette il
    # registro accessi.
    log.info(
        "schede cliente unite",
        extra={
            "id_destinazione": client_id,
            "id_origine": payload.source_id,
            "righe_spostate": esito.righe_totali,
            "dettaglio": esito.conteggi,
            "account_spostato": esito.account_spostato,
        },
    )
    return _anteprima_in_schema(esito)


@router.post("/{client_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_client_password(
    client_id: int,
    payload: AdminPasswordReset,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Admin sets a client's portal password, e.g. after they call in locked out.

    Mirrors `POST /api/admin/team/{user_id}/reset-password` for staff. Before
    this there was no way in for a client who lost access to their own inbox:
    the only path was the self-service `forgot-password` email, which is no
    help if the email itself is unreachable.
    """
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    if not client.account_id:
        raise HTTPException(
            status_code=400, detail="Questo cliente non ha un account sul portale"
        )

    account = (await db.execute(
        select(ClientAccount).where(ClientAccount.id == client.account_id)
    )).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account portale non trovato")

    # Su un account non verificato il login rifiuta comunque, password giusta o
    # no. Senza questo controllo l'operatore detterebbe una password che non
    # funziona e non saprebbe perché: la strada per quel caso è rimandare il
    # codice, non cambiare la password. Verificare l'indirizzo da qui non è
    # un'opzione — è la prova che l'indirizzo è suo, e da quella prova dipende
    # l'aggancio alla scheda del salone.
    if not account.email_verified:
        raise HTTPException(
            status_code=400,
            detail="Indirizzo email non ancora verificato: la cliente deve prima "
                   "inserire il codice ricevuto per posta. Cambiare la password "
                   "non la farebbe entrare.",
        )

    account.password_hash = await hash_password(payload.new_password)
    # Un link di reset chiesto per email e non ancora usato resterebbe valido:
    # chi ce l'ha in mano potrebbe sovrascrivere la password appena impostata.
    account.reset_token = None
    account.reset_token_expires = None
    await db.flush()

    # `via` distingue questo reset da quello self-service, che scrive lo stesso
    # nome di evento: chi guarda il registro deve poter dire se la password
    # l'ha cambiata la cliente col token via email o un operatore dal
    # gestionale. Chi sia l'operatore lo mette già `attore`.
    evento(
        RESET_ESEGUITO,
        id_account=account.id,
        email=maschera_email(account.email),
        via="admin",
    )


@router.get("/{client_id}/appointments", response_model=List[AppointmentOutWithNames])
async def get_client_appointments(
    client_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Appointment)
        .options(*appointment_detail_loads())
        .where(Appointment.client_id == client_id)
        .order_by(Appointment.start_time.desc())
    )
    appointments = result.scalars().all()
    return [AppointmentOutWithNames.from_appointment(a) for a in appointments]
