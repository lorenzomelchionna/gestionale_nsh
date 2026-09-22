"""
Accettare una proposta di orario alternativo doveva spostare l'appuntamento
di netto — stessa durata, nuovo inizio. Calcolava invece la durata *dopo*
aver già sovrascritto `start_time` col nuovo orario, quindi
`durata = vecchia_fine - nuovo_inizio` e `nuovo_inizio + durata` tornavano
sempre alla vecchia fine, qualunque fosse il nuovo inizio. Spostato in
avanti, l'appuntamento si accorciava; spostato oltre la vecchia fine,
finiva con durata negativa.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentStatus
from app.models.client import Client

pytestmark = pytest.mark.asyncio


class TestAccettaAlternativaMantieneLaDurata:
    async def test_end_time_segue_il_nuovo_inizio_con_la_stessa_durata(
        self, client, db, client_tokens, client_account, collaborator, service
    ):
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        vecchio_inizio = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=5)
        vecchia_fine = vecchio_inizio + timedelta(hours=1)  # durata reale: 1h
        nuovo_inizio = vecchio_inizio + timedelta(hours=3)  # proposta 3h più tardi

        appt = Appointment(
            client_id=cliente.id,
            collaborator_id=collaborator.id,
            start_time=vecchio_inizio,
            end_time=vecchia_fine,
            status=AppointmentStatus.rescheduled,
            alternative_time=nuovo_inizio,
        )
        db.add(appt)
        await db.commit()
        await db.refresh(appt)

        resp = await client.post(
            f"/api/public/appointments/{appt.id}/accept-alternative",
            headers={"Authorization": f"Bearer {client_tokens['access_token']}"},
        )
        assert resp.status_code == 200

        await db.refresh(appt)
        durata = vecchia_fine - vecchio_inizio
        assert appt.start_time == nuovo_inizio
        assert appt.end_time == nuovo_inizio + durata, (
            "l'appuntamento deve durare quanto durava, spostato al nuovo "
            f"inizio ({nuovo_inizio + durata}), non tornare alla vecchia fine "
            f"({vecchia_fine})"
        )
        assert appt.end_time > appt.start_time, "durata negativa: il sintomo peggiore del difetto"
        assert appt.status == AppointmentStatus.confirmed
        assert appt.alternative_time is None

    async def test_anche_spostato_indietro_la_durata_resta_quella_vera(
        self, client, db, client_tokens, client_account, collaborator, service
    ):
        """Caso limite che il calcolo sbagliato rendeva peggiore degli altri:
        un nuovo inizio *oltre* la vecchia fine dava una durata negativa."""
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        vecchio_inizio = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=5)
        vecchia_fine = vecchio_inizio + timedelta(minutes=30)  # durata reale: 30 min
        nuovo_inizio = vecchia_fine + timedelta(hours=2)  # oltre la vecchia fine

        appt = Appointment(
            client_id=cliente.id,
            collaborator_id=collaborator.id,
            start_time=vecchio_inizio,
            end_time=vecchia_fine,
            status=AppointmentStatus.rescheduled,
            alternative_time=nuovo_inizio,
        )
        db.add(appt)
        await db.commit()
        await db.refresh(appt)

        resp = await client.post(
            f"/api/public/appointments/{appt.id}/accept-alternative",
            headers={"Authorization": f"Bearer {client_tokens['access_token']}"},
        )
        assert resp.status_code == 200

        await db.refresh(appt)
        assert appt.end_time == nuovo_inizio + timedelta(minutes=30)
