"""Vendere prodotti dalla Cassa, a chi entra solo a comprare.

Richiesta del 2026-10-09, seguito di quella del giorno prima: la vendita
all'«Incassa» della visita non bastava, perché chi compra uno shampoo senza
fare un servizio non ha una visita. Stesse regole: giacenza che blocca,
movimento «vendita», tutto o niente. In più, dalla Cassa: l'importo deve
essere la somma dei prodotti, il tipo deve essere «prodotto», e il misto
contanti + carta continua a funzionare.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentOrigin, AppointmentStatus

from app.models.payment import Payment, PaymentMethod, PaymentType
from app.models.product import MovementType, Product, ProductMovement
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio

URL = "/api/admin/payments"


@pytest_asyncio.fixture
async def shampoo(db) -> Product:
    p = Product(name="Shampoo Argan", purchase_price=7, sale_price=22,
                category="Rivendita", quantity=4)
    db.add(p)
    await db.commit()
    return p


@pytest_asyncio.fixture
async def lacca(db) -> Product:
    p = Product(name="Lacca Forte", purchase_price=5, sale_price=14,
                category="Styling", quantity=1)
    db.add(p)
    await db.commit()
    return p


async def _pagamenti(db):
    return (await db.execute(select(Payment).order_by(Payment.id))).scalars().all()


async def _giacenza(db, p):
    return (await db.execute(select(Product.quantity).where(Product.id == p.id))).scalar_one()


async def _movimenti(db, p):
    return (await db.execute(
        select(ProductMovement).where(ProductMovement.product_id == p.id)
    )).scalars().all()


class TestVenditaAlBanco:
    async def test_incassa_e_scala(self, client, db, admin_tokens, shampoo, lacca):
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 58, "method": "carta", "type": "prodotto",
            "products": [
                {"product_id": shampoo.id, "quantity": 2, "unit_price": 22},
                {"product_id": lacca.id, "quantity": 1, "unit_price": 14},
            ],
        })
        assert r.status_code == 201, r.text
        [p] = await _pagamenti(db)
        assert (p.type, float(p.amount), p.method) == (PaymentType.product, 58.0, PaymentMethod.card)
        assert p.appointment_id is None
        assert p.notes == "2× Shampoo Argan, 1× Lacca Forte"

        assert await _giacenza(db, shampoo) == 2
        assert await _giacenza(db, lacca) == 0
        [m] = await _movimenti(db, shampoo)
        assert (m.type, m.quantity, m.appointment_id) == (MovementType.sale, 2, None)

    async def test_la_nota_scritta_resta(self, client, db, admin_tokens, shampoo):
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 22, "method": "contanti", "type": "prodotto", "notes": " cliente di passaggio ",
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 22}],
        })
        assert r.status_code == 201, r.text
        [p] = await _pagamenti(db)
        assert p.notes == "1× Shampoo Argan — cliente di passaggio"

    async def test_misto_contanti_e_carta(self, client, db, admin_tokens, shampoo):
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 44, "method": "misto", "type": "prodotto",
            "cash_amount": 20, "card_amount": 24,
            "products": [{"product_id": shampoo.id, "quantity": 2, "unit_price": 22}],
        })
        assert r.status_code == 201, r.text
        [p] = await _pagamenti(db)
        assert (float(p.cash_amount), float(p.card_amount)) == (20.0, 24.0)
        assert await _giacenza(db, shampoo) == 2

    async def test_prezzo_scontato(self, client, db, admin_tokens, shampoo):
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 18.5, "method": "contanti", "type": "prodotto",
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 18.5}],
        })
        assert r.status_code == 201, r.text
        [p] = await _pagamenti(db)
        assert float(p.amount) == 18.5

    async def test_senza_prodotti_come_prima(self, client, db, admin_tokens, shampoo):
        """L'incasso scritto a mano resta: un prodotto fuori catalogo, una
        correzione."""
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 10, "method": "contanti", "type": "prodotto", "notes": "fuori catalogo",
        })
        assert r.status_code == 201, r.text
        assert await _giacenza(db, shampoo) == 4
        assert await _movimenti(db, shampoo) == []


    async def test_legata_a_una_visita_se_indicata(
        self, client, db, admin_tokens, shampoo, collaborator, other_client,
    ):
        """La rotta accetta già `appointment_id`: se c'è, anche il movimento
        di magazzino dice a quale visita appartiene la vendita."""
        start = giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=1))
        a = Appointment(
            client_id=other_client.id, collaborator_id=collaborator.id,
            start_time=start, end_time=start + timedelta(hours=1),
            status=AppointmentStatus.completed, origin=AppointmentOrigin.salon,
        )
        db.add(a)
        await db.commit()
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 22, "method": "carta", "type": "prodotto", "appointment_id": a.id,
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 22}],
        })
        assert r.status_code == 201, r.text
        [m] = await _movimenti(db, shampoo)
        assert m.appointment_id == a.id


class TestRegole:
    async def test_giacenza_insufficiente_niente_incasso(self, client, db, admin_tokens, shampoo, lacca):
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 50, "method": "carta", "type": "prodotto",
            "products": [
                {"product_id": shampoo.id, "quantity": 1, "unit_price": 22},
                {"product_id": lacca.id, "quantity": 2, "unit_price": 14},
            ],
        })
        assert r.status_code == 409
        assert "Lacca Forte" in r.json()["detail"]
        assert await _pagamenti(db) == []
        assert await _giacenza(db, shampoo) == 4
        assert await _movimenti(db, shampoo) == []

    async def test_importo_diverso_dai_prodotti(self, client, db, admin_tokens, shampoo):
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 30, "method": "carta", "type": "prodotto",
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 22}],
        })
        assert r.status_code == 422
        assert await _giacenza(db, shampoo) == 4

    async def test_righe_doppie_sommate_anche_nell_importo(self, client, db, admin_tokens, shampoo):
        """Due righe dello stesso prodotto: la giacenza le conta insieme, e
        l'importo atteso è quello della somma."""
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 44, "method": "carta", "type": "prodotto",
            "products": [
                {"product_id": shampoo.id, "quantity": 1, "unit_price": 22},
                {"product_id": shampoo.id, "quantity": 1, "unit_price": 22},
            ],
        })
        assert r.status_code == 201, r.text
        assert await _giacenza(db, shampoo) == 2

    async def test_con_prodotti_il_tipo_e_prodotto(self, client, db, admin_tokens, shampoo):
        """Altrimenti il cruscotto conterebbe la rivendita fra i servizi."""
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 22, "method": "carta", "type": "servizio",
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 22}],
        })
        assert r.status_code == 422
        assert await _giacenza(db, shampoo) == 4

    async def test_tutto_omaggio_no(self, client, db, admin_tokens, shampoo):
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 0, "method": "contanti", "type": "prodotto",
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 0}],
        })
        assert r.status_code == 422
        assert await _giacenza(db, shampoo) == 4

    async def test_archiviato_no(self, client, db, admin_tokens, shampoo):
        shampoo.is_active = False
        await db.commit()
        r = await client.post(URL, headers=auth(admin_tokens), json={
            "amount": 22, "method": "carta", "type": "prodotto",
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 22}],
        })
        assert r.status_code == 400
        assert await _pagamenti(db) == []

    async def test_un_collaboratore_non_vende(self, client, db, collab_tokens, shampoo):
        r = await client.post(URL, headers=auth(collab_tokens), json={
            "amount": 22, "method": "carta", "type": "prodotto",
            "products": [{"product_id": shampoo.id, "quantity": 1, "unit_price": 22}],
        })
        assert r.status_code == 403
        assert await _giacenza(db, shampoo) == 4
