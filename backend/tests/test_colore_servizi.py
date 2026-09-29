"""Il colore di un servizio, e come arriva al calendario.

Il valore finisce in uno `style` della pagina: per questo il test che conta
di più è quello che rifiuta tutto ciò che non è `#rrggbb` — una stringa
libera lì dentro sarebbe CSS scritto da chiunque possa salvare un servizio.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.appointment import Appointment, AppointmentService, AppointmentStatus
from app.models.service import Service
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

SERVICES = "/api/admin/services"


def _servizio(**campi):
    return {"name": "Colore test", "price": 40, "duration_slots": 2, "category": "Colore", **campi}


class TestIlColore:
    async def test_si_salva_in_minuscolo(self, client, admin_tokens):
        r = await client.post(SERVICES, headers=auth(admin_tokens), json=_servizio(color="#C8A96E"))
        assert r.status_code == 201, r.text
        assert r.json()["color"] == "#c8a96e"

    @pytest.mark.parametrize("sbagliato", [
        "red", "#12345", "#1234567", "c8a96e", "#zzzzzz",
        "#fff; background:url(https://x)", "url(javascript:1)",
    ])
    async def test_solo_rrggbb(self, client, admin_tokens, sbagliato):
        r = await client.post(SERVICES, headers=auth(admin_tokens), json=_servizio(color=sbagliato))
        assert r.status_code == 422

    async def test_senza_colore_va_bene(self, client, admin_tokens):
        r = await client.post(SERVICES, headers=auth(admin_tokens), json=_servizio())
        assert r.status_code == 201
        assert r.json()["color"] is None

    async def test_si_cambia_e_si_toglie(self, client, admin_tokens, service):
        r = await client.put(f"{SERVICES}/{service.id}", headers=auth(admin_tokens), json={"color": "#4a7c59"})
        assert r.status_code == 200, r.text
        assert r.json()["color"] == "#4a7c59"
        # Modifica parziale: cambiare il prezzo non tocca il colore.
        r = await client.put(f"{SERVICES}/{service.id}", headers=auth(admin_tokens), json={"price": 33})
        assert r.json()["color"] == "#4a7c59"
        r = await client.put(f"{SERVICES}/{service.id}", headers=auth(admin_tokens), json={"color": ""})
        assert r.json()["color"] is None

    async def test_il_collaboratore_non_lo_cambia(self, client, collab_tokens, service):
        r = await client.put(f"{SERVICES}/{service.id}", headers=auth(collab_tokens), json={"color": "#4a7c59"})
        assert r.status_code == 403


class TestNelCalendario:
    async def test_i_colori_seguono_i_servizi_in_ordine(
        self, client, db, admin_tokens, collaborator, service, other_client
    ):
        piega = Service(name="Piega", price=20, duration_slots=1, category="Styling", color="#b85c38")
        service.color = None
        db.add(piega)
        await db.flush()
        inizio = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
        appt = Appointment(
            client_id=other_client.id, collaborator_id=collaborator.id,
            start_time=inizio, end_time=inizio + timedelta(minutes=90),
            status=AppointmentStatus.confirmed,
        )
        db.add(appt)
        await db.flush()
        db.add(AppointmentService(appointment_id=appt.id, service_id=piega.id, price_snapshot=20))
        db.add(AppointmentService(appointment_id=appt.id, service_id=service.id, price_snapshot=30))
        await db.commit()

        r = await client.get("/api/admin/appointments", headers=auth(admin_tokens), params={
            "start_date": inizio.date().isoformat(), "end_date": inizio.date().isoformat(),
        })
        assert r.status_code == 200, r.text
        voci = r.json()
        voci = voci["items"] if isinstance(voci, dict) else voci
        a = next(x for x in voci if x["id"] == appt.id)
        assert len(a["service_colors"]) == len(a["service_names"]) == 2
        assert dict(zip(a["service_names"], a["service_colors"])) == {
            "Piega": "#b85c38", "Taglio test": None,
        }
