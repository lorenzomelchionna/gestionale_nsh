"""
Le cose lasciate indietro nei due giri precedenti, chiuse insieme.

Ognuna era stata annotata in TODO come «rimasto fuori»: nessuna rompeva
niente da sola, tutte erano il tipo di dettaglio che diventa un problema il
giorno in cui qualcuno ci sbatte contro.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.models.appointment import (
    Appointment, AppointmentService, AppointmentOrigin, AppointmentStatus,
)
from app.models.gift_card import GiftCard
from app.models.product import Product
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def prodotto(db) -> Product:
    p = Product(
        name="Shampoo test", purchase_price=4.0, sale_price=12.0,
        category="Capelli", quantity=5,
    )
    db.add(p)
    await db.commit()
    return p


class TestArchiviareUnProdotto:
    """Prima `is_active` era modificabile via API ma la lista filtrava sempre
    gli attivi: archiviare voleva dire perdere il prodotto per sempre."""

    async def test_di_default_gli_archiviati_non_si_vedono(
        self, client, db, admin_tokens, prodotto
    ):
        prodotto.is_active = False
        await db.commit()

        resp = await client.get("/api/admin/products", headers=auth(admin_tokens))
        assert resp.json()["total"] == 0

    async def test_si_possono_rivedere(self, client, db, admin_tokens, prodotto):
        prodotto.is_active = False
        await db.commit()

        resp = await client.get(
            "/api/admin/products", headers=auth(admin_tokens),
            params={"active_only": "false"},
        )
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["is_active"] is False

    async def test_e_si_possono_rimettere_in_catalogo(
        self, client, db, admin_tokens, prodotto
    ):
        """La parte che rende l'archiviazione una scelta e non una perdita."""
        await client.put(
            f"/api/admin/products/{prodotto.id}", headers=auth(admin_tokens),
            json={"is_active": False},
        )
        await client.put(
            f"/api/admin/products/{prodotto.id}", headers=auth(admin_tokens),
            json={"is_active": True},
        )
        resp = await client.get("/api/admin/products", headers=auth(admin_tokens))
        assert resp.json()["total"] == 1

    async def test_l_archiviato_resta_fuori_dal_sotto_scorta(
        self, client, db, admin_tokens, prodotto
    ):
        """Un prodotto fuori catalogo non va riordinato: comparire fra i
        «sotto scorta» sarebbe un promemoria a comprare roba che non si vende
        più."""
        prodotto.is_active = False
        prodotto.quantity = 0
        await db.commit()

        resp = await client.get(
            "/api/admin/products", headers=auth(admin_tokens), params={"low_stock": "true"}
        )
        assert resp.json()["total"] == 0


class TestPrezziNegativi:
    async def test_in_creazione_rifiutati(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/products", headers=auth(admin_tokens),
            json={
                "name": "Storto", "purchase_price": -5, "sale_price": 10,
                "category": "Capelli",
            },
        )
        assert resp.status_code == 422

    async def test_in_modifica_rifiutati(self, client, admin_tokens, prodotto):
        resp = await client.put(
            f"/api/admin/products/{prodotto.id}", headers=auth(admin_tokens),
            json={"sale_price": -1},
        )
        assert resp.status_code == 422

    async def test_giacenza_negativa_rifiutata(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/products", headers=auth(admin_tokens),
            json={
                "name": "Storto", "purchase_price": 5, "sale_price": 10,
                "category": "Capelli", "quantity": -3,
            },
        )
        assert resp.status_code == 422

    async def test_il_vincolo_non_tocca_la_lettura(
        self, client, db, admin_tokens, prodotto
    ):
        """Il motivo per cui il vincolo sta su `ProductCreate` e non su
        `ProductBase`: se una riga storta esistesse già a database, a fallire
        dev'essere la scrittura che la corregge, non l'elenco da cui ci si
        accorge del problema."""
        await db.execute(
            text("UPDATE products SET sale_price = -1 WHERE id = :i"),
            {"i": prodotto.id},
        )
        await db.commit()

        resp = await client.get("/api/admin/products", headers=auth(admin_tokens))
        assert resp.status_code == 200
        assert resp.json()["items"][0]["sale_price"] == -1.0


class TestRiscattoAgganciatoAllaVisita:
    @pytest_asyncio.fixture
    async def visita(self, db, collaborator, service, other_client) -> Appointment:
        start = datetime.now(timezone.utc) - timedelta(hours=2)
        a = Appointment(
            client_id=other_client.id,
            collaborator_id=collaborator.id,
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=AppointmentStatus.completed,
            origin=AppointmentOrigin.salon,
        )
        db.add(a)
        await db.flush()
        db.add(AppointmentService(
            appointment_id=a.id, service_id=service.id, price_snapshot=30.0
        ))
        await db.commit()
        return a

    @pytest_asyncio.fixture
    async def buono(self, client, admin_tokens) -> dict:
        resp = await client.post(
            "/api/admin/gift-cards", headers=auth(admin_tokens),
            json={
                "amount": 50.0, "recipient_name": "Chiara",
                "recipient_email": "chiara@example.it",
            },
        )
        return resp.json()

    async def test_il_riscatto_ricorda_su_quale_visita(
        self, client, admin_tokens, buono, visita
    ):
        """Il campo esisteva ma nessuna schermata lo scriveva: si sapeva
        quanto era stato speso, non su cosa."""
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens),
            json={"amount": 30.0, "appointment_id": visita.id},
        )
        assert resp.status_code == 200, resp.text
        riscatto = resp.json()["redemptions"][0]
        assert riscatto["appointment_id"] == visita.id
        assert "Estranea Test" in riscatto["appointment_label"]

    async def test_resta_facoltativo(self, client, admin_tokens, buono):
        """Al banco capita di scalare un buono senza un appuntamento a cui
        agganciarlo — un prodotto, o chi passa senza prenotare."""
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 10.0},
        )
        assert resp.status_code == 200
        assert resp.json()["redemptions"][0]["appointment_id"] is None
        assert resp.json()["redemptions"][0]["appointment_label"] is None

    async def test_un_appuntamento_inventato_non_scala_niente(
        self, client, db, admin_tokens, buono
    ):
        """Senza il controllo l'id sbagliato arriverebbe alla foreign key: 500
        dal database, e per giunta col saldo già ridotto in transazione."""
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens),
            json={"amount": 30.0, "appointment_id": 999999},
        )
        assert resp.status_code == 400

        card = (await db.execute(
            select(GiftCard).where(GiftCard.id == buono["id"])
        )).scalar_one()
        assert float(card.balance) == 50.0


class TestAccodareNonBlocca:
    async def test_la_pubblicazione_non_ritenta(self):
        """Ogni `.delay()` dell'app è dentro un `try/except`, ma coi default
        di Celery fallisce **dopo** aver ritentato con backoff: con Redis
        irraggiungibile la richiesta resta appesa per decine di secondi, e
        alla cassa c'è qualcuno che aspetta.
        """
        from app.tasks.celery_app import celery_app

        assert celery_app.conf.task_publish_retry is False
        opzioni = celery_app.conf.broker_transport_options
        assert opzioni.get("socket_connect_timeout") == 2
        assert opzioni.get("socket_timeout") == 2

    async def test_il_worker_invece_aspetta_il_broker(self):
        """Vale solo per chi pubblica. Il worker all'avvio deve ritentare,
        altrimenti un riavvio simultaneo dei due servizi lo fa morire prima
        che Redis sia pronto."""
        from app.tasks.celery_app import celery_app

        assert celery_app.conf.broker_connection_retry_on_startup is True
