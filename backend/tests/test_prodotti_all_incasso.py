"""I prodotti comprati alla fine della visita, nell'«Incassa» dell'appuntamento.

Richiesta del 2026-10-08: una cliente che ha fatto un servizio compra anche
uno shampoo. Prima l'incasso del prodotto andava rifatto a parte in Cassa e
lo scarico a parte nel magazzino — due passi che si dimenticano. Decisioni
del salone: prezzo di listino ma modificabile, e la giacenza blocca la
vendita (più di quanti ne risultano non se ne vendono).

Quello che questi test fissano: un pagamento «prodotto» separato da quello
dei servizi, la giacenza scalata con un movimento «vendita» legato alla
visita, e il tutto-o-niente — se un prodotto non basta non si incassa
nemmeno il servizio.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.appointment import (
    Appointment, AppointmentOrigin, AppointmentService, AppointmentStatus,
)
from app.models.payment import Payment, PaymentMethod, PaymentType
from app.models.product import MovementType, Product, ProductMovement
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def visita(db, collaborator, service, other_client) -> Appointment:
    start = giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=1))
    a = Appointment(
        client_id=other_client.id, collaborator_id=collaborator.id,
        start_time=start, end_time=start + timedelta(hours=1),
        status=AppointmentStatus.confirmed, origin=AppointmentOrigin.salon,
    )
    db.add(a)
    await db.flush()
    db.add(AppointmentService(appointment_id=a.id, service_id=service.id, price_snapshot=30.0))
    await db.commit()
    return a


@pytest_asyncio.fixture
async def shampoo(db) -> Product:
    p = Product(name="Shampoo Ristrutturante", purchase_price=6, sale_price=18,
                category="Rivendita", quantity=5)
    db.add(p)
    await db.commit()
    return p


@pytest_asyncio.fixture
async def maschera(db) -> Product:
    p = Product(name="Maschera", purchase_price=8, sale_price=24,
                category="Rivendita", quantity=1)
    db.add(p)
    await db.commit()
    return p


def _url(a):
    return f"/api/admin/appointments/{a.id}/checkout"


async def _pagamenti(db, a):
    return (await db.execute(
        select(Payment).where(Payment.appointment_id == a.id).order_by(Payment.id)
    )).scalars().all()


async def _giacenza(db, p):
    return (await db.execute(select(Product.quantity).where(Product.id == p.id))).scalar_one()


async def _movimenti(db, p):
    return (await db.execute(
        select(ProductMovement).where(ProductMovement.product_id == p.id)
    )).scalars().all()


class TestVendita:
    async def test_due_incassi_e_giacenza_scalata(
        self, client, db, admin_tokens, visita, shampoo, maschera, other_client,
    ):
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30,
            "products": [
                {"product_id": shampoo.id, "quantity": 2, "unit_price": 18},
                {"product_id": maschera.id, "quantity": 1, "unit_price": 24},
            ],
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["paid_amount"] == 30.0, "i prodotti non vanno nell'incasso dei servizi"
        assert corpo["products_paid_amount"] == 60.0

        servizio, prodotti = await _pagamenti(db, visita)
        assert (servizio.type, float(servizio.amount)) == (PaymentType.service, 30.0)
        assert (prodotti.type, float(prodotti.amount)) == (PaymentType.product, 60.0)
        assert prodotti.method == PaymentMethod.card
        assert prodotti.client_id == other_client.id
        assert "2× Shampoo Ristrutturante" in prodotti.notes
        assert "1× Maschera" in prodotti.notes

        assert await _giacenza(db, shampoo) == 3
        assert await _giacenza(db, maschera) == 0
        [m] = await _movimenti(db, shampoo)
        assert (m.type, m.quantity, m.appointment_id) == (MovementType.sale, 2, visita.id)

    async def test_prezzo_scontato(self, client, db, admin_tokens, visita, shampoo):
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "contanti", "amount": 30,
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 15.5}],
        })
        assert r.status_code == 200, r.text
        _, prodotti = await _pagamenti(db, visita)
        assert float(prodotti.amount) == 15.5
        assert prodotti.method == PaymentMethod.cash

    async def test_senza_prodotti_come_prima(self, client, db, admin_tokens, visita, shampoo):
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={"method": "carta", "amount": 30})
        assert r.status_code == 200, r.text
        assert r.json()["products_paid_amount"] is None
        [p] = await _pagamenti(db, visita)
        assert p.type == PaymentType.service
        assert await _giacenza(db, shampoo) == 5

    async def test_omaggio_scala_ma_non_incassa(self, client, db, admin_tokens, visita, shampoo):
        """Un campione regalato esce dal magazzino, ma un pagamento da zero
        in Cassa sarebbe solo rumore."""
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30,
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 0}],
        })
        assert r.status_code == 200, r.text
        [p] = await _pagamenti(db, visita)
        assert p.type == PaymentType.service
        assert await _giacenza(db, shampoo) == 4


class TestGiacenza:
    async def test_piu_di_quanti_ce_ne_sono_no(self, client, db, admin_tokens, visita, maschera):
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30,
            "products": [{"product_id": maschera.id, "quantity": 2, "unit_price": 24}],
        })
        assert r.status_code == 409
        assert "Maschera" in r.json()["detail"]

    async def test_tutto_o_niente(self, client, db, admin_tokens, visita, shampoo, maschera):
        """Lo shampoo c'è, la maschera no: niente di niente — né il servizio
        incassato, né la visita chiusa, né lo shampoo scalato."""
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30,
            "products": [
                {"product_id": shampoo.id, "quantity": 1, "unit_price": 18},
                {"product_id": maschera.id, "quantity": 3, "unit_price": 24},
            ],
        })
        assert r.status_code == 409
        assert await _pagamenti(db, visita) == []
        assert await _giacenza(db, shampoo) == 5
        assert await _movimenti(db, shampoo) == []
        stato = (await db.execute(
            select(Appointment.status).where(Appointment.id == visita.id)
        )).scalar_one()
        assert stato == AppointmentStatus.confirmed

    async def test_la_stessa_riga_due_volte_conta_il_totale(
        self, client, db, admin_tokens, visita, maschera,
    ):
        """Una maschera sola a magazzino, aggiunta due volte da una riga per
        uno: prese una per una passerebbero entrambe."""
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30,
            "products": [
                {"product_id": maschera.id, "quantity": 1, "unit_price": 24},
                {"product_id": maschera.id, "quantity": 1, "unit_price": 24},
            ],
        })
        assert r.status_code == 409
        assert await _giacenza(db, maschera) == 1

    async def test_prodotto_archiviato_no(self, client, db, admin_tokens, visita, shampoo):
        shampoo.is_active = False
        await db.commit()
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30,
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 18}],
        })
        assert r.status_code == 400
        assert await _pagamenti(db, visita) == []

    async def test_prodotto_inesistente_no(self, client, db, admin_tokens, visita):
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30,
            "products": [{"product_id": 999999, "quantity": 1, "unit_price": 18}],
        })
        assert r.status_code == 400
        assert await _pagamenti(db, visita) == []

    @pytest.mark.parametrize("riga", [
        {"quantity": 0, "unit_price": 18},
        {"quantity": 1, "unit_price": -1},
    ])
    async def test_righe_storte(self, client, db, admin_tokens, visita, shampoo, riga):
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30,
            "products": [{"product_id": shampoo.id, **riga}],
        })
        assert r.status_code == 422
        assert await _giacenza(db, shampoo) == 5


class TestPermessi:
    async def test_un_collaboratore_non_vende(self, client, db, collab_tokens, visita, shampoo):
        r = await client.post(_url(visita), headers=auth(collab_tokens), json={
            "method": "carta", "amount": 30,
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 18}],
        })
        assert r.status_code == 403
        assert await _giacenza(db, shampoo) == 5
