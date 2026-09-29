"""«Incassa» dall'appuntamento: chiudere la visita e registrare il pagamento.

Richiesta del 2026-09-29: dall'appuntamento si poteva solo segnare
completato, e l'incasso andava rifatto a mano in Cassa. Quello che questi
test fissano: il pagamento nasce legato ad appuntamento e cliente, un
appuntamento non si incassa due volte, e la cassa resta dell'admin.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.appointment import (
    Appointment, AppointmentOrigin, AppointmentService, AppointmentStatus,
)
from app.models.payment import Payment, PaymentMethod, PaymentType
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def visita(db, collaborator, service, other_client) -> Appointment:
    start = giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=1))
    a = Appointment(
        client_id=other_client.id,
        collaborator_id=collaborator.id,
        start_time=start,
        end_time=start + timedelta(hours=1),
        status=AppointmentStatus.confirmed,
        origin=AppointmentOrigin.salon,
    )
    db.add(a)
    await db.flush()
    db.add(AppointmentService(appointment_id=a.id, service_id=service.id, price_snapshot=30.0))
    await db.commit()
    return a


def _url(a):
    return f"/api/admin/appointments/{a.id}/checkout"


async def _pagamenti(db, a):
    return (await db.execute(
        select(Payment).where(Payment.appointment_id == a.id)
    )).scalars().all()


class TestIncassa:
    async def test_chiude_e_registra_il_pagamento(self, client, db, admin_tokens, visita, other_client):
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={"method": "carta", "amount": 30})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["status"] == "completed"
        assert (corpo["paid_amount"], corpo["paid_method"]) == (30.0, "carta")

        [p] = await _pagamenti(db, visita)
        assert p.client_id == other_client.id
        assert p.method == PaymentMethod.card
        assert p.type == PaymentType.service
        assert float(p.amount) == 30.0

    async def test_importo_diverso_dal_listino(self, client, db, admin_tokens, visita):
        """Uno sconto, un prodotto aggiunto: vale quello che si incassa."""
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={"method": "contanti", "amount": 25.5})
        assert r.status_code == 200, r.text
        [p] = await _pagamenti(db, visita)
        assert float(p.amount) == 25.5 and p.method == PaymentMethod.cash

    async def test_scrive_la_nota_della_visita(self, client, db, admin_tokens, visita):
        await client.post(_url(visita), headers=auth(admin_tokens), json={
            "method": "carta", "amount": 30, "visit_notes": "  Colore 7.3  ",
        })
        await db.refresh(visita)
        assert visita.visit_notes == "Colore 7.3"

    async def test_non_si_incassa_due_volte(self, client, db, admin_tokens, visita):
        prima = await client.post(_url(visita), headers=auth(admin_tokens), json={"method": "carta", "amount": 30})
        assert prima.status_code == 200
        seconda = await client.post(_url(visita), headers=auth(admin_tokens), json={"method": "contanti", "amount": 30})
        assert seconda.status_code == 409
        assert len(await _pagamenti(db, visita)) == 1

    async def test_si_incassa_anche_dopo_segna_completato(self, client, db, admin_tokens, visita):
        r = await client.post(f"/api/admin/appointments/{visita.id}/complete", headers=auth(admin_tokens))
        assert r.status_code == 200
        assert r.json()["paid_amount"] is None

        r = await client.post(_url(visita), headers=auth(admin_tokens), json={"method": "contanti", "amount": 30})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed"
        assert r.json()["paid_method"] == "contanti"

    @pytest.mark.parametrize("stato", [
        AppointmentStatus.pending, AppointmentStatus.cancelled, AppointmentStatus.rejected,
    ])
    async def test_solo_confermati_o_completati(self, client, db, admin_tokens, visita, stato):
        visita.status = stato
        await db.commit()
        r = await client.post(_url(visita), headers=auth(admin_tokens), json={"method": "carta", "amount": 30})
        assert r.status_code == 400
        assert await _pagamenti(db, visita) == []

    @pytest.mark.parametrize("corpo", [
        {"method": "misto", "amount": 30},
        {"method": "bitcoin", "amount": 30},
        {"method": "carta", "amount": 0},
        {"method": "carta", "amount": -5},
        {"method": "carta"},
    ])
    async def test_dati_non_validi(self, client, admin_tokens, visita, corpo):
        r = await client.post(_url(visita), headers=auth(admin_tokens), json=corpo)
        assert r.status_code == 422

    async def test_il_collaboratore_non_incassa(self, client, db, collab_tokens, visita):
        r = await client.post(_url(visita), headers=auth(collab_tokens), json={"method": "carta", "amount": 30})
        assert r.status_code == 403
        await db.refresh(visita)
        assert visita.status == AppointmentStatus.confirmed
        assert await _pagamenti(db, visita) == []


class TestNelCalendario:
    async def test_l_elenco_dice_se_e_incassato(self, client, admin_tokens, visita):
        giorno = visita.start_time.date().isoformat()
        prima = (await client.get("/api/admin/appointments", headers=auth(admin_tokens),
                                  params={"start_date": giorno, "end_date": giorno})).json()
        prima = prima["items"] if isinstance(prima, dict) else prima
        assert next(a for a in prima if a["id"] == visita.id)["paid_amount"] is None

        await client.post(_url(visita), headers=auth(admin_tokens), json={"method": "carta", "amount": 30})
        dopo = (await client.get("/api/admin/appointments", headers=auth(admin_tokens),
                                 params={"start_date": giorno, "end_date": giorno})).json()
        dopo = dopo["items"] if isinstance(dopo, dict) else dopo
        a = next(a for a in dopo if a["id"] == visita.id)
        assert (a["paid_amount"], a["paid_method"]) == (30.0, "carta")
