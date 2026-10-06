"""I giorni straordinari: prima delle 8 si lavora, dopo le 19 prenota solo il salone.

Segnalazione di Flavia del 2026-10-06: per sabato 10/10 aveva messo un
giorno straordinario dalle 07:30 alle 20:00, ma «non va». Il portale le
07:30 le offriva già; era il calendario del gestionale a partire comunque
dalle 08:00, senza modo di vederle né di prenotarle. E il portale, per lo
stesso giorno, offriva anche le 19:00 e le 19:30 — la fascia che il 29/09
era stata decisa solo del salone.

Qui il backend: la rotta da cui il calendario legge i giorni straordinari
della settimana, e il tetto delle 19 che il portale applica qualunque cosa
dicano gli orari. La griglia che parte prima sta nel frontend.
"""
from datetime import datetime, time, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.collaborator import CollaboratorSchedule
from app.models.extra_day import CollaboratorExtraDay
from app.utils.tempo import istante
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio

AVAILABILITY = "/api/public/availability"
CALENDAR = "/api/public/availability/calendar"
GIORNI = "/api/admin/extra-days"


@pytest_asyncio.fixture
async def sabato(db, collaborator):
    """Un giorno di lavoro con lo straordinario di Flavia: 07:30–20:00."""
    giorno = giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=3)).date()
    db.add(CollaboratorExtraDay(
        collaborator_id=collaborator.id, date=giorno,
        start_time=time(7, 30), end_time=time(20, 0),
    ))
    await db.commit()
    return giorno


async def _orari(client, collaborator, service, giorno):
    r = await client.get(AVAILABILITY, params={
        "service_id": service.id, "collaborator_id": collaborator.id,
        "target_date": giorno.isoformat(),
    })
    assert r.status_code == 200, r.text
    return [datetime.fromisoformat(s) for s in r.json()]


class TestIlPortaleNelGiornoStraordinario:
    async def test_le_7_30_si_prenotano(self, client, booking_config, collaborator, service, sabato):
        orari = await _orari(client, collaborator, service, sabato)
        assert min(orari) == istante(sabato, time(7, 30))

    async def test_dopo_le_19_no(self, client, booking_config, collaborator, service, sabato):
        """Il fixture `service` dura un'ora: l'ultima che finisce entro le 19
        comincia alle 18:00. Prima di questa correzione l'elenco arrivava alle
        19:00, cioè fino alle 20:00 dello straordinario."""
        orari = await _orari(client, collaborator, service, sabato)
        assert max(orari) == istante(sabato, time(18, 0))

    async def test_chiamata_a_mano_alle_19_rifiutata(
        self, client, booking_config, client_tokens, collaborator, service, sabato,
    ):
        """Il tetto vale anche sulla prenotazione, non solo sull'elenco: la
        fascia che il portale non mostra non si prende con curl."""
        inizio = istante(sabato, time(19, 0))
        r = await client.post("/api/public/appointments", headers=auth(client_tokens), json={
            "client_id": 0, "collaborator_id": collaborator.id,
            "start_time": inizio.isoformat(),
            "end_time": (inizio + timedelta(hours=1)).isoformat(),
            "service_ids": [service.id],
        })
        assert r.status_code == 409, r.text

    async def test_il_conteggio_del_calendario_e_lo_stesso(
        self, client, booking_config, collaborator, service, sabato,
    ):
        """Il calendario del portale conta gli orari liberi di ogni giorno:
        deve contare quelli dell'elenco, non quelli fino alle 20."""
        orari = await _orari(client, collaborator, service, sabato)
        r = await client.get(CALENDAR, params={
            "service_id": service.id, "collaborator_id": collaborator.id,
            "start_date": sabato.isoformat(), "end_date": sabato.isoformat(),
        })
        assert r.status_code == 200, r.text
        assert r.json()[0]["slots"] == len(orari)

    async def test_vale_anche_per_un_orario_settimanale_fino_alle_20(
        self, client, db, booking_config, collaborator, service,
    ):
        """Il tetto non dipende da come è scritto l'orario: un sabato
        settimanale messo fino alle 20 non apre la fascia alle clienti."""
        giorno = giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=3)).date()
        sched = CollaboratorSchedule(
            collaborator_id=collaborator.id, day_of_week=giorno.weekday(),
            start_time=time(9, 0), end_time=time(20, 0), is_working=True,
        )
        from sqlalchemy import delete
        await db.execute(delete(CollaboratorSchedule).where(
            CollaboratorSchedule.collaborator_id == collaborator.id,
            CollaboratorSchedule.day_of_week == giorno.weekday(),
        ))
        db.add(sched)
        await db.commit()

        orari = await _orari(client, collaborator, service, giorno)
        assert max(orari) == istante(giorno, time(18, 0))


class TestIlSaloneNelGiornoStraordinario:
    async def test_prenota_alle_7_30_e_alle_19(
        self, client, booking_config, admin_tokens, collaborator, service, other_client, sabato,
    ):
        for ora in (time(7, 30), time(19, 0)):
            inizio = istante(sabato, ora)
            r = await client.post("/api/admin/appointments", headers=auth(admin_tokens), json={
                "client_id": other_client.id, "collaborator_id": collaborator.id,
                "start_time": inizio.isoformat(),
                "end_time": (inizio + timedelta(hours=1)).isoformat(),
                "service_ids": [service.id],
            })
            assert r.status_code == 201, f"{ora}: {r.text}"

    async def test_gli_orari_del_gestionale_arrivano_alle_20(
        self, client, booking_config, admin_tokens, collaborator, sabato,
    ):
        """Il tetto delle 19 è del portale: gli orari che il gestionale chiede
        per lo stesso giorno arrivano fino alla fine dello straordinario."""
        r = await client.get("/api/admin/availability", headers=auth(admin_tokens), params={
            "collaborator_id": collaborator.id, "target_date": sabato.isoformat(),
            "duration_slots": 2,
        })
        assert r.status_code == 200, r.text
        orari = [datetime.fromisoformat(x) for x in r.json()]
        assert istante(sabato, time(19, 0)) in orari


class TestLaRottaPerIlCalendario:
    async def test_i_giorni_della_settimana(self, client, db, collab_tokens, collaborator, sabato):
        """Tutto lo staff, come il calendario: anche un collaboratore."""
        fuori = sabato + timedelta(days=30)
        db.add(CollaboratorExtraDay(
            collaborator_id=collaborator.id, date=fuori,
            start_time=time(9, 0), end_time=time(13, 0),
        ))
        await db.commit()

        r = await client.get(GIORNI, headers=auth(collab_tokens), params={
            "start_date": (sabato - timedelta(days=sabato.weekday())).isoformat(),
            "end_date": (sabato + timedelta(days=6 - sabato.weekday())).isoformat(),
        })
        assert r.status_code == 200, r.text
        giorni = r.json()
        assert [(g["date"], g["start_time"], g["end_time"]) for g in giorni] == [
            (sabato.isoformat(), "07:30:00", "20:00:00"),
        ]

    async def test_intervallo_rovesciato(self, client, admin_tokens):
        r = await client.get(GIORNI, headers=auth(admin_tokens), params={
            "start_date": "2026-10-10", "end_date": "2026-10-01",
        })
        assert r.status_code == 400

    async def test_intervallo_troppo_ampio(self, client, admin_tokens):
        r = await client.get(GIORNI, headers=auth(admin_tokens), params={
            "start_date": "2026-01-01", "end_date": "2026-12-31",
        })
        assert r.status_code == 400

    async def test_senza_accesso_niente(self, client):
        r = await client.get(GIORNI, params={"start_date": "2026-10-05", "end_date": "2026-10-11"})
        assert r.status_code == 401
