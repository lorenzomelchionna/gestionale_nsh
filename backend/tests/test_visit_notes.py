"""
La nota di visita: dove si scrive, e chi non deve leggerla.

Richiesta di Flavia (2026-08-04): segnare il colore usato a ogni visita.
`Client.notes` non serve — è un campo solo, quindi la nota di oggi cancella
quella di tre mesi fa. `Appointment.visit_notes` è il campo giusto e c'era
già nel modello, ma **nessuna schermata lo scriveva**.

Il fatto che restasse sempre vuoto teneva nascosto un problema: il portale
cliente restituiva l'appuntamento con dentro `visit_notes` e `notes`. Finché
erano vuoti non usciva niente; dal momento in cui il salone ci scrive
davvero «colore 7.3, capello in difficoltà», sarebbe la cliente a leggersi
gli appunti interni.

Per questo il collegamento della UI e la chiusura del portale stanno nello
stesso giro: separati, il primo aprirebbe una falla che il secondo chiude.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.appointment import (
    Appointment, AppointmentService, AppointmentStatus, AppointmentOrigin,
)
from app.models.client import Client
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def visita(db, collaborator, service, client_account) -> Appointment:
    """Un appuntamento confermato della cliente che ha l'accesso al portale."""
    c = (await db.execute(
        select(Client).where(Client.account_id == client_account.id)
    )).scalar_one()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    a = Appointment(
        client_id=c.id,
        collaborator_id=collaborator.id,
        start_time=start,
        end_time=start + timedelta(hours=1),
        status=AppointmentStatus.confirmed,
        origin=AppointmentOrigin.salon,
        notes="Chiede di non usare il phon caldo",
    )
    db.add(a)
    await db.flush()
    db.add(AppointmentService(
        appointment_id=a.id, service_id=service.id, price_snapshot=30.0
    ))
    await db.commit()
    return a


class TestScrivereLaNota:
    async def test_si_scrive_chiudendo_la_visita(
        self, client, db, admin_tokens, visita
    ):
        """È il momento in cui si sa cosa scrivere: la visita è appena finita."""
        resp = await client.post(
            f"/api/admin/appointments/{visita.id}/complete",
            headers=auth(admin_tokens),
            json={"visit_notes": "Colore 7.3 + 20 vol, 35 minuti di posa"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "completed"

        await db.refresh(visita)
        assert visita.visit_notes == "Colore 7.3 + 20 vol, 35 minuti di posa"

    async def test_completare_senza_nota_resta_un_clic_solo(
        self, client, db, admin_tokens, visita
    ):
        """Il corpo è facoltativo: quando il salone è pieno non si scrive niente."""
        resp = await client.post(
            f"/api/admin/appointments/{visita.id}/complete",
            headers=auth(admin_tokens),
        )
        assert resp.status_code == 200, resp.text

        await db.refresh(visita)
        assert visita.status == AppointmentStatus.completed
        assert visita.visit_notes is None

    async def test_una_nota_di_soli_spazi_non_cancella_quella_di_prima(
        self, client, db, admin_tokens, visita
    ):
        """Un textarea lasciato bianco vuol dire «non ho scritto niente»."""
        visita.visit_notes = "Colore 6.0"
        visita.status = AppointmentStatus.confirmed
        await db.commit()

        await client.post(
            f"/api/admin/appointments/{visita.id}/complete",
            headers=auth(admin_tokens),
            json={"visit_notes": "   "},
        )
        await db.refresh(visita)
        assert visita.visit_notes == "Colore 6.0"

    async def test_si_corregge_dopo_dal_put(self, client, db, admin_tokens, visita):
        """Ci si ricorda un dettaglio mezz'ora dopo, e la visita è già chiusa."""
        resp = await client.put(
            f"/api/admin/appointments/{visita.id}",
            headers=auth(admin_tokens),
            json={"visit_notes": "Colore 7.3, la prossima volta niente decolorante"},
        )
        assert resp.status_code == 200, resp.text
        await db.refresh(visita)
        assert visita.visit_notes.endswith("niente decolorante")


class TestIlPortaleNonLaVede:
    """Il confine che rende sicuro scrivere la nota."""

    async def test_la_nota_di_visita_non_esce_dal_portale(
        self, client, db, admin_tokens, client_tokens, visita
    ):
        await client.post(
            f"/api/admin/appointments/{visita.id}/complete",
            headers=auth(admin_tokens),
            json={"visit_notes": "Capello in difficoltà, sconsigliata la decolorazione"},
        )

        resp = await client.get(
            "/api/public/appointments", headers=auth(client_tokens)
        )
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert len(corpo) == 1

        assert "visit_notes" not in corpo[0]
        # Anche il testo, non solo la chiave: una serializzazione diversa non
        # deve poterlo far uscire sotto un altro nome.
        assert "decolorazione" not in resp.text

    async def test_nemmeno_la_nota_interna_di_prenotazione(
        self, client, client_tokens, visita
    ):
        resp = await client.get(
            "/api/public/appointments", headers=auth(client_tokens)
        )
        assert "notes" not in resp.json()[0]
        assert "phon caldo" not in resp.text

    async def test_quello_che_la_cliente_deve_vedere_c_e_ancora(
        self, client, client_tokens, visita
    ):
        """Chiudere non vuol dire svuotare: la scheda resta leggibile."""
        resp = await client.get(
            "/api/public/appointments", headers=auth(client_tokens)
        )
        a = resp.json()[0]
        assert a["id"] == visita.id
        assert a["status"] == "confirmed"
        assert a["collaborator_name"] == "Sofia Test"
        assert a["service_names"] == ["Taglio test"]
        assert a["total_price"] == 30.0

    async def test_il_motivo_del_rifiuto_resta_visibile(
        self, client, db, admin_tokens, client_tokens, visita
    ):
        """È scritto apposta per chi l'ha subito: toglierlo sarebbe un rifiuto muto."""
        await client.post(
            f"/api/admin/appointments/{visita.id}/reject",
            headers=auth(admin_tokens),
            json={"reason": "Quel giorno il salone è chiuso"},
        )
        resp = await client.get(
            "/api/public/appointments", headers=auth(client_tokens)
        )
        assert resp.json()[0]["rejection_reason"] == "Quel giorno il salone è chiuso"

    async def test_anche_la_risposta_alla_prenotazione_e_ripulita(
        self, client, db, booking_config, collaborator, service, client_tokens
    ):
        """La prenotazione online risponde con l'appuntamento appena creato:
        stessa proiezione, stesso confine."""
        start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        resp = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,  # ignorato: lo ricava dall'account
                "collaborator_id": collaborator.id,
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=1)).isoformat(),
                "service_ids": [service.id],
                "notes": "Nota della cliente",
            },
        )
        assert resp.status_code == 201, resp.text
        corpo = resp.json()
        assert "visit_notes" not in corpo
        assert "notes" not in corpo
        # Le relazioni servono a nome e servizi: se la risposta le perdesse,
        # o sollevasse MissingGreenlet, se ne accorgerebbe solo la cliente.
        assert corpo["collaborator_name"] == "Sofia Test"
        assert corpo["service_names"] == ["Taglio test"]
