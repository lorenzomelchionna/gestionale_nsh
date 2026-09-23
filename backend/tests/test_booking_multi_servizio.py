"""Più servizi nello stesso appuntamento, dal portale.

La prenotazione li accettava già — somma delle durate, tempi di posa in
sequenza, collaboratore che deve farli tutti — ma i due endpoint che
calcolano gli orari ne accettavano uno solo. La pagina avrebbe quindi mostrato
orari validi per il primo servizio, e il server avrebbe rifiutato quelli in cui
la durata complessiva non ci sta.

Il punto che questi test fissano è l'**accordo**: un orario che la
disponibilità offre per una combinazione di servizi dev'essere un orario che
la prenotazione accetta per la stessa combinazione.
"""
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio

from app.models.collaborator import CollaboratorService
from app.models.service import Service
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio

AVAILABILITY = "/api/public/availability"
CALENDAR = "/api/public/availability/calendar"


@pytest_asyncio.fixture
async def piega(db, collaborator):
    """Un secondo servizio, offerto dallo stesso collaboratore."""
    svc = Service(
        name="Piega test", price=20.0, duration_slots=2,
        category="Styling", bookable_online=True, is_active=True,
    )
    db.add(svc)
    await db.flush()
    db.add(CollaboratorService(collaborator_id=collaborator.id, service_id=svc.id))
    await db.commit()
    return svc


@pytest_asyncio.fixture
async def non_offerto(db):
    """Un servizio che il collaboratore del fixture non fa."""
    svc = Service(
        name="Trattamento test", price=50.0, duration_slots=2,
        category="Trattamenti", bookable_online=True, is_active=True,
    )
    db.add(svc)
    await db.commit()
    return svc


def _giorno() -> date:
    return giorno_lavorativo(date.today() + timedelta(days=2))


async def _orari(client, collaborator, *, service_id=None, service_ids=None):
    params: list = [("collaborator_id", collaborator.id), ("target_date", _giorno().isoformat())]
    if service_id is not None:
        params.append(("service_id", service_id))
    for sid in service_ids or []:
        params.append(("service_ids", sid))
    return await client.get(AVAILABILITY, params=params)


class TestOrari:
    async def test_la_durata_e_quella_complessiva(
        self, client, booking_config, collaborator, service, piega
    ):
        """Due servizi da un'ora l'uno: l'ultimo inizio possibile arriva
        un'ora prima che con uno solo, perché la giornata finisce alle 19."""
        uno = await _orari(client, collaborator, service_ids=[service.id])
        due = await _orari(client, collaborator, service_ids=[service.id, piega.id])
        assert uno.status_code == 200, uno.text
        assert due.status_code == 200, due.text

        ultimo_uno = max(datetime.fromisoformat(s) for s in uno.json())
        ultimo_due = max(datetime.fromisoformat(s) for s in due.json())
        assert ultimo_uno - ultimo_due == timedelta(hours=1)

    async def test_la_forma_di_prima_funziona_ancora(
        self, client, booking_config, collaborator, service
    ):
        """`service_id` singolo: le pagine già aperte nei browser lo usano."""
        vecchia = await _orari(client, collaborator, service_id=service.id)
        nuova = await _orari(client, collaborator, service_ids=[service.id])
        assert vecchia.status_code == 200, vecchia.text
        assert vecchia.json() == nuova.json()

    async def test_senza_servizi_rifiuta(self, client, booking_config, collaborator):
        r = await _orari(client, collaborator)
        assert r.status_code == 422

    async def test_il_collaboratore_deve_farli_tutti(
        self, client, booking_config, collaborator, service, non_offerto
    ):
        r = await _orari(client, collaborator, service_ids=[service.id, non_offerto.id])
        assert r.status_code in (400, 404), r.text

    async def test_un_servizio_non_prenotabile_online_rifiuta(
        self, client, booking_config, collaborator, service, piega, db
    ):
        piega.bookable_online = False
        await db.commit()
        r = await _orari(client, collaborator, service_ids=[service.id, piega.id])
        assert r.status_code == 404


class TestCalendario:
    async def test_meno_orari_con_piu_servizi(
        self, client, booking_config, collaborator, service, piega
    ):
        giorno = _giorno()
        base = [
            ("collaborator_id", collaborator.id),
            ("start_date", giorno.isoformat()),
            ("end_date", giorno.isoformat()),
        ]
        uno = await client.get(CALENDAR, params=base + [("service_ids", service.id)])
        due = await client.get(
            CALENDAR, params=base + [("service_ids", service.id), ("service_ids", piega.id)]
        )
        assert uno.status_code == 200, uno.text
        assert due.status_code == 200, due.text
        assert 0 < due.json()[0]["slots"] < uno.json()[0]["slots"]

    async def test_la_forma_di_prima_funziona_ancora(
        self, client, booking_config, collaborator, service
    ):
        giorno = _giorno()
        r = await client.get(CALENDAR, params={
            "service_id": service.id, "collaborator_id": collaborator.id,
            "start_date": giorno.isoformat(), "end_date": giorno.isoformat(),
        })
        assert r.status_code == 200, r.text


class TestAccordoConLaPrenotazione:
    async def test_l_ultimo_orario_offerto_viene_accettato(
        self, client, booking_config, collaborator, service, piega, client_tokens
    ):
        """L'orario più tardo è quello al limite: se la disponibilità usasse
        la durata di un solo servizio, è proprio questo che la prenotazione
        rifiuterebbe."""
        orari = await _orari(client, collaborator, service_ids=[service.id, piega.id])
        inizio = max(datetime.fromisoformat(s) for s in orari.json())

        r = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,
                "collaborator_id": collaborator.id,
                "start_time": inizio.isoformat(),
                "end_time": (inizio + timedelta(hours=2)).isoformat(),
                "service_ids": [service.id, piega.id],
            },
        )
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert sorted(corpo["service_names"]) == ["Piega test", "Taglio test"]
        assert corpo["total_price"] == 50.0
        # La fine la calcola il server dalla somma delle durate, non la prende
        # dal browser: 2 + 2 slot da 30 minuti.
        assert datetime.fromisoformat(corpo["end_time"]) - inizio == timedelta(hours=2)
