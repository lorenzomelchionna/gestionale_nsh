"""
Permessi a ore: assentarsi un pomeriggio senza perdere la giornata.

Richiesta di Flavia (2026-08-04): voleva un "servizio Pausa" nascosto ai
clienti da usare per prendere qualche ora di permesso. Il modello degli
appuntamenti però pretende un `client_id`, quindi quella strada avrebbe
richiesto un cliente finto in anagrafica per ogni pausa, sporcando elenco
clienti e statistiche.

`Absence` esiste già per questo e blocca il calendario nel modo giusto —
mancava solo di poterla limitare a una fascia oraria invece che alla
giornata intera.

Entrambe le ore assenti = giornata intera, cioè il comportamento di prima:
è quello che rende retrocompatibili le assenze già registrate.
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.absence import Absence, AbsenceType
from app.services.availability import get_available_slots
from tests.conftest import auth


@pytest_asyncio.fixture
async def giorno_lavorativo(collaborator):
    """Il fixture lavora lun–sab 09:00–19:00."""
    d = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d


async def _orari_liberi(db, collaborator, giorno, durata=1):
    slots = await get_available_slots(db, collaborator.id, giorno, durata)
    return {s.strftime("%H:%M") for s in slots}


class TestPermessoAOre:
    async def test_blocca_solo_la_fascia_indicata(
        self, db, booking_config, collaborator, giorno_lavorativo
    ):
        db.add(Absence(
            collaborator_id=collaborator.id,
            start_date=giorno_lavorativo, end_date=giorno_lavorativo,
            start_time=time(14, 0), end_time=time(16, 0),
            type=AbsenceType.permit, notes="Visita medica",
        ))
        await db.commit()

        orari = await _orari_liberi(db, collaborator, giorno_lavorativo)

        assert "14:00" not in orari
        assert "15:00" not in orari
        assert "15:30" not in orari
        assert "10:00" in orari, "ha tolto anche la mattina"
        assert "16:00" in orari, "non ha restituito il pomeriggio dopo il permesso"

    async def test_la_giornata_intera_continua_a_valere(
        self, db, booking_config, collaborator, giorno_lavorativo
    ):
        """Le assenze registrate finora non hanno le ore: devono comportarsi
        esattamente come prima."""
        db.add(Absence(
            collaborator_id=collaborator.id,
            start_date=giorno_lavorativo, end_date=giorno_lavorativo,
            type=AbsenceType.vacation,
        ))
        await db.commit()

        assert await _orari_liberi(db, collaborator, giorno_lavorativo) == set()

    async def test_due_permessi_nello_stesso_giorno(
        self, db, booking_config, collaborator, giorno_lavorativo
    ):
        """Prima falliva del tutto: la query usava `scalar_one_or_none()`, che
        con due righe solleva invece di rispondere. Coi permessi a ore due
        assenze in un giorno diventano normali."""
        db.add(Absence(
            collaborator_id=collaborator.id,
            start_date=giorno_lavorativo, end_date=giorno_lavorativo,
            start_time=time(9, 0), end_time=time(10, 0),
            type=AbsenceType.permit,
        ))
        db.add(Absence(
            collaborator_id=collaborator.id,
            start_date=giorno_lavorativo, end_date=giorno_lavorativo,
            start_time=time(17, 0), end_time=time(19, 0),
            type=AbsenceType.permit,
        ))
        await db.commit()

        orari = await _orari_liberi(db, collaborator, giorno_lavorativo)
        assert "09:00" not in orari
        assert "17:00" not in orari
        assert "12:00" in orari

    async def test_una_giornata_intera_vince_sul_permesso(
        self, db, booking_config, collaborator, giorno_lavorativo
    ):
        """Un permesso di due ore dentro una settimana di ferie non rende
        prenotabile il resto del giorno."""
        db.add(Absence(
            collaborator_id=collaborator.id,
            start_date=giorno_lavorativo, end_date=giorno_lavorativo,
            start_time=time(9, 0), end_time=time(10, 0),
            type=AbsenceType.permit,
        ))
        db.add(Absence(
            collaborator_id=collaborator.id,
            start_date=giorno_lavorativo, end_date=giorno_lavorativo,
            type=AbsenceType.vacation,
        ))
        await db.commit()

        assert await _orari_liberi(db, collaborator, giorno_lavorativo) == set()

    async def test_la_fascia_vale_su_tutti_i_giorni_dell_intervallo(
        self, db, booking_config, collaborator, giorno_lavorativo
    ):
        """«Tutte le mattine di questa settimana»."""
        fine = giorno_lavorativo + timedelta(days=2)
        db.add(Absence(
            collaborator_id=collaborator.id,
            start_date=giorno_lavorativo, end_date=fine,
            start_time=time(9, 0), end_time=time(13, 0),
            type=AbsenceType.permit,
        ))
        await db.commit()

        for giorno in (giorno_lavorativo, giorno_lavorativo + timedelta(days=1)):
            if giorno.weekday() == 6:
                continue
            orari = await _orari_liberi(db, collaborator, giorno)
            assert "09:00" not in orari, f"{giorno}: mattina non bloccata"
            assert "14:00" in orari, f"{giorno}: pomeriggio tolto per sbaglio"

    async def test_un_appuntamento_non_entra_nella_fascia_di_permesso(
        self, client, db, booking_config, client_tokens, collaborator, service,
        giorno_lavorativo,
    ):
        """La verifica che conta: non basta che l'orario sparisca dalla lista,
        deve rifiutarlo anche chi prova a prenotarlo direttamente."""
        db.add(Absence(
            collaborator_id=collaborator.id,
            start_date=giorno_lavorativo, end_date=giorno_lavorativo,
            start_time=time(14, 0), end_time=time(16, 0),
            type=AbsenceType.permit,
        ))
        await db.commit()

        quando = datetime.combine(giorno_lavorativo, time(14, 0), tzinfo=timezone.utc)
        resp = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,
                "collaborator_id": collaborator.id,
                "start_time": quando.isoformat(),
                "end_time": (quando + timedelta(hours=1)).isoformat(),
                "service_ids": [service.id],
            },
        )
        assert resp.status_code == 409, resp.text


class TestLApiDelleAssenze:
    async def test_si_registra_un_permesso_a_ore(
        self, client, admin_tokens, collaborator, giorno_lavorativo
    ):
        resp = await client.post(
            "/api/admin/absences", headers=auth(admin_tokens),
            json={
                "collaborator_id": collaborator.id,
                "start_date": giorno_lavorativo.isoformat(),
                "end_date": giorno_lavorativo.isoformat(),
                "start_time": "14:00:00",
                "end_time": "16:00:00",
                "type": "permesso",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["start_time"] == "14:00:00"
        assert body["end_time"] == "16:00:00"

    async def test_la_giornata_intera_resta_possibile(
        self, client, admin_tokens, collaborator, giorno_lavorativo
    ):
        resp = await client.post(
            "/api/admin/absences", headers=auth(admin_tokens),
            json={
                "collaborator_id": collaborator.id,
                "start_date": giorno_lavorativo.isoformat(),
                "end_date": giorno_lavorativo.isoformat(),
                "type": "ferie",
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["start_time"] is None

    async def test_una_sola_ora_e_rifiutata(
        self, client, admin_tokens, collaborator, giorno_lavorativo
    ):
        """Senza il confine di fine il calendario non saprebbe dove fermarsi e
        tratterebbe l'assenza come giornata intera — l'opposto della richiesta."""
        resp = await client.post(
            "/api/admin/absences", headers=auth(admin_tokens),
            json={
                "collaborator_id": collaborator.id,
                "start_date": giorno_lavorativo.isoformat(),
                "end_date": giorno_lavorativo.isoformat(),
                "start_time": "14:00:00",
                "type": "permesso",
            },
        )
        assert resp.status_code == 422

    async def test_ora_di_fine_precedente_e_rifiutata(
        self, client, admin_tokens, collaborator, giorno_lavorativo
    ):
        resp = await client.post(
            "/api/admin/absences", headers=auth(admin_tokens),
            json={
                "collaborator_id": collaborator.id,
                "start_date": giorno_lavorativo.isoformat(),
                "end_date": giorno_lavorativo.isoformat(),
                "start_time": "16:00:00",
                "end_time": "14:00:00",
                "type": "permesso",
            },
        )
        assert resp.status_code == 422

    async def test_data_di_fine_precedente_e_rifiutata(
        self, client, admin_tokens, collaborator, giorno_lavorativo
    ):
        resp = await client.post(
            "/api/admin/absences", headers=auth(admin_tokens),
            json={
                "collaborator_id": collaborator.id,
                "start_date": giorno_lavorativo.isoformat(),
                "end_date": (giorno_lavorativo - timedelta(days=3)).isoformat(),
                "type": "ferie",
            },
        )
        assert resp.status_code == 422
