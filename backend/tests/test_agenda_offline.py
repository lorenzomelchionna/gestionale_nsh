"""
L'agenda per quando in salone manca internet (frontend `src/offline/`).

Il browser salva gli appuntamenti dei prossimi giorni dall'elenco
`/api/admin/appointments`; offline la scheda cliente non si apre, quindi il
telefono per richiamarla deve stare nell'appuntamento stesso.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.appointment import (
    Appointment, AppointmentOrigin, AppointmentService, AppointmentStatus,
)
from app.models.client import Client
from tests.conftest import auth


async def test_l_elenco_porta_il_telefono_della_cliente(
    client, db, collab_tokens, collaborator, service,
):
    cliente = Client(first_name="Anna", last_name="Prova", phone="+393331112223")
    db.add(cliente)
    await db.flush()
    inizio = datetime.combine(datetime.now().date() + timedelta(days=1), time(10), tzinfo=ZoneInfo("Europe/Rome"))
    a = Appointment(client_id=cliente.id, collaborator_id=collaborator.id, start_time=inizio,
                    end_time=inizio + timedelta(hours=1), status=AppointmentStatus.confirmed,
                    origin=AppointmentOrigin.salon)
    db.add(a)
    await db.flush()
    db.add(AppointmentService(appointment_id=a.id, service_id=service.id, price_snapshot=float(service.price)))
    await db.commit()

    # Un collaboratore: in salone lavorano anche loro, e l'agenda la vedono già.
    r = await client.get("/api/admin/appointments", headers=auth(collab_tokens))
    assert r.status_code == 200
    (riga,) = [x for x in r.json()["items"] if x["id"] == a.id]
    assert riga["client_phone"] == "+393331112223"
    assert riga["client_name"] == "Anna Prova"
