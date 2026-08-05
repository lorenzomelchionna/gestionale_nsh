from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import require_admin
from app.models.appointment import Appointment
from app.models.client import Client
from app.models.gift_card import (
    GiftCard, GiftCardRedemption, GiftCardStatus, generate_code,
)
from app.models.payment import Payment, PaymentMethod, PaymentType
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.gift_card import (
    GiftCardCancel, GiftCardCreate, GiftCardOut, GiftCardRedeem, GiftCardResend,
)

router = APIRouter(prefix="/gift-cards", tags=["Gift cards"])

# Quanti codici provare prima di arrendersi. Una collisione su 57 bit non
# succede; il ciclo c'è perché «non succede» e «non può succedere» sono due
# cose diverse quando in mezzo c'è un vincolo di unicità a database.
MAX_CODE_ATTEMPTS = 5


def _trigger_gift_card_email(gift_card_id: int) -> None:
    """Manda l'email al destinatario, senza far aspettare la cassa.

    Fire-and-forget come le altre notifiche: se il broker non risponde, la
    vendita resta registrata e l'email si rimanda dalla scheda. Il contrario —
    perdere la vendita perché l'email non parte — sarebbe peggio, visto che i
    soldi sono già stati incassati.
    """
    try:
        from app.tasks.reminders import send_gift_card_task
        send_gift_card_task.delay(gift_card_id)
    except Exception as e:  # pragma: no cover - dipende dal broker
        print(f"[NOTIFY] Could not queue gift card email {gift_card_id}: {e}")


def _carica_riscatti():
    """Tutto quello che la proiezione di un buono legge, in un posto solo.

    L'appuntamento e la sua cliente servono all'etichetta «05/08/2026 · Laura
    Ricci» nello storico dei riscatti. Senza caricarli qui, ogni riga li
    andrebbe a cercare da sola — cioè una query a riscatto sotto asyncio, che
    non è lenta: è un `MissingGreenlet`.
    """
    return selectinload(GiftCard.redemptions).selectinload(
        GiftCardRedemption.appointment
    ).selectinload(Appointment.client)


async def _load(db: AsyncSession, gift_card_id: int) -> GiftCard:
    result = await db.execute(
        select(GiftCard)
        .options(_carica_riscatti())
        .where(GiftCard.id == gift_card_id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Buono regalo non trovato")
    return card


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(MAX_CODE_ATTEMPTS):
        code = generate_code()
        exists = await db.execute(select(GiftCard.id).where(GiftCard.code == code))
        if exists.scalar_one_or_none() is None:
            return code
    raise HTTPException(
        status_code=500, detail="Non è stato possibile generare un codice. Riprova."
    )


@router.get("", response_model=PaginatedResponse[GiftCardOut])
async def list_gift_cards(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    status_filter: Optional[GiftCardStatus] = Query(None, alias="status"),
):
    """L'elenco dei buoni emessi.

    Il filtro per stato non può diventare un `WHERE`: lo stato non esiste a
    database, si ricava. Si filtra in Python sulla pagina già letta, e il
    totale viene ricontato di conseguenza — con i numeri di un salone la
    differenza non si vede, e la coerenza vale più della query.
    """
    q = select(GiftCard).options(_carica_riscatti())
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(
            GiftCard.code.ilike(like),
            GiftCard.recipient_name.ilike(like),
            GiftCard.recipient_email.ilike(like),
            GiftCard.purchaser_name.ilike(like),
        ))

    result = await db.execute(q.order_by(GiftCard.created_at.desc()))
    cards = [GiftCardOut.from_card(c) for c in result.scalars().all()]
    if status_filter:
        cards = [c for c in cards if c.status == status_filter]

    total = len(cards)
    inizio = (page - 1) * page_size
    return PaginatedResponse(
        items=cards[inizio:inizio + page_size],
        total=total, page=page, page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.get("/by-code/{code}", response_model=GiftCardOut)
async def get_by_code(
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Cerca per codice, che è come arriva al banco: letto da un'email.

    Maiuscole, spazi e trattini non contano. Il codice viene ricopiato a mano
    o dettato al telefono, e `nsh a7k2 9qx4 mt3f` è lo stesso buono di
    `NSH-A7K2-9QX4-MT3F`: farlo fallire per un trattino vorrebbe dire dare
    della bugiarda a una cliente che ha il buono in mano.
    """
    def _pulisci(valore: str) -> str:
        return valore.strip().upper().replace(" ", "").replace("-", "")

    result = await db.execute(
        select(GiftCard)
        .options(_carica_riscatti())
        .where(func.replace(func.upper(GiftCard.code), "-", "") == _pulisci(code))
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Nessun buono con questo codice")
    return GiftCardOut.from_card(card)


@router.post("", response_model=GiftCardOut, status_code=status.HTTP_201_CREATED)
async def create_gift_card(
    payload: GiftCardCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Vende un buono: incassa, genera il codice, manda l'email al destinatario."""
    if payload.purchaser_client_id is not None:
        cliente = await db.execute(
            select(Client).where(Client.id == payload.purchaser_client_id)
        )
        if cliente.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Cliente acquirente non trovato")

    importo = Decimal(str(payload.amount))

    # L'incasso è di oggi: il denaro entra alla vendita, non al riscatto.
    pagamento = Payment(
        client_id=payload.purchaser_client_id,
        amount=importo,
        method=payload.payment_method,
        type=PaymentType.gift_card,
        notes=f"Buono regalo per {payload.recipient_name}",
    )
    db.add(pagamento)
    await db.flush()

    card = GiftCard(
        code=await _unique_code(db),
        initial_amount=importo,
        balance=importo,
        recipient_name=payload.recipient_name,
        recipient_email=str(payload.recipient_email),
        message=payload.message,
        purchaser_client_id=payload.purchaser_client_id,
        purchaser_name=payload.purchaser_name,
        expires_at=date.today() + timedelta(days=payload.validity_days),
        payment_id=pagamento.id,
        created_by_id=current_user.id,
    )
    db.add(card)
    await db.flush()
    card_id = card.id

    # Commit prima di accodare: il worker legge da una transazione sua, e un id
    # passato mentre questa è ancora aperta punta a una riga che non vede.
    await db.commit()
    _trigger_gift_card_email(card_id)

    return GiftCardOut.from_card(await _load(db, card_id))


@router.post("/{gift_card_id}/redeem", response_model=GiftCardOut)
async def redeem_gift_card(
    gift_card_id: int,
    payload: GiftCardRedeem,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Scala un importo dal credito.

    La riga viene bloccata (`FOR UPDATE`) per tutta l'operazione. Senza,
    due postazioni che riscattano lo stesso buono nello stesso istante
    leggerebbero entrambe lo stesso saldo e lo scalerebbero entrambe: un
    buono da 50€ ne pagherebbe 100. È l'unico punto della funzionalità in
    cui due persone possono toccare la stessa riga insieme, ed è anche
    quello in cui la riga è denaro.

    Non nasce nessun `Payment`: l'incasso è già stato registrato alla vendita,
    e registrarlo di nuovo conterebbe gli stessi euro due volte.
    """
    bloccata = await db.execute(
        select(GiftCard).where(GiftCard.id == gift_card_id).with_for_update()
    )
    card = bloccata.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Buono regalo non trovato")

    stato = card.compute_status()
    if stato != GiftCardStatus.active:
        motivi = {
            GiftCardStatus.exhausted: "Questo buono è già stato speso del tutto.",
            GiftCardStatus.expired: f"Questo buono è scaduto il {card.expires_at.strftime('%d/%m/%Y')}.",
            GiftCardStatus.cancelled: "Questo buono è stato annullato.",
        }
        raise HTTPException(status_code=400, detail=motivi[stato])

    if payload.appointment_id is not None:
        # Controllato prima di scalare: un id inesistente arriverebbe alla
        # foreign key e tornerebbe un 500 dal database, per giunta **dopo**
        # aver già ridotto il saldo in questa transazione.
        esiste = await db.execute(
            select(Appointment.id).where(Appointment.id == payload.appointment_id)
        )
        if esiste.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Appuntamento non trovato")

    importo = Decimal(str(payload.amount))
    if importo > card.balance:
        raise HTTPException(
            status_code=400,
            detail=f"Il buono ha solo €{float(card.balance):.2f} di credito residuo.",
        )

    card.balance = card.balance - importo
    db.add(GiftCardRedemption(
        gift_card_id=card.id,
        amount=importo,
        appointment_id=payload.appointment_id,
        notes=payload.notes,
        created_by_id=current_user.id,
    ))
    await db.flush()

    return GiftCardOut.from_card(await _load(db, gift_card_id))


@router.post("/{gift_card_id}/cancel", response_model=GiftCardOut)
async def cancel_gift_card(
    gift_card_id: int,
    payload: GiftCardCancel,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Storna un buono.

    Il saldo non viene azzerato: quello che era stato speso resta scritto,
    e la card annullata continua a raccontare quanto valeva e quanto ne era
    già stato usato. Serve a rispondere a «quanto gli dobbiamo?» quando il
    motivo dello storno è un rimborso.
    """
    card = await _load(db, gift_card_id)
    if card.cancelled_at is not None:
        raise HTTPException(status_code=400, detail="Buono già annullato")

    card.cancelled_at = datetime.now(timezone.utc)
    card.cancel_reason = payload.reason
    await db.flush()
    return GiftCardOut.from_card(await _load(db, gift_card_id))


@router.post("/{gift_card_id}/resend-email", response_model=GiftCardOut)
async def resend_gift_card_email(
    gift_card_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    payload: Optional[GiftCardResend] = None,
):
    """Rimanda l'email, eventualmente a un altro indirizzo.

    L'indirizzo si può correggere qui perché è il motivo per cui si rimanda:
    un'email sbagliata dettata al banco è la norma, non l'eccezione, e
    rispedire allo stesso indirizzo sbagliato non risolverebbe niente. Senza
    questa possibilità l'unica strada sarebbe rifare il buono da capo — cioè
    incassare due volte una vendita sola.
    """
    card = await _load(db, gift_card_id)
    if card.cancelled_at is not None:
        raise HTTPException(
            status_code=400, detail="Il buono è annullato: non ha senso rimandarlo."
        )

    if payload is not None and payload.recipient_email is not None:
        card.recipient_email = str(payload.recipient_email)
    await db.commit()
    _trigger_gift_card_email(gift_card_id)
    return GiftCardOut.from_card(await _load(db, gift_card_id))
