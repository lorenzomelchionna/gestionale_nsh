"""Le assenze nel calendario: l'elenco per intervallo che la griglia legge.

Un permesso a ore bloccava già le prenotazioni online, ma nel calendario del
salone quell'ora sembrava libera: la griglia le assenze non le chiedeva.
"""
from datetime import date, time, timedelta

import pytest

from app.models.absence import Absence, AbsenceType
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

URL = "/api/admin/absences"
OGGI = date.today()


async def _assenza(db, collaborator, inizio, fine, **campi):
    a = Absence(collaborator_id=collaborator.id, start_date=inizio, end_date=fine,
                type=campi.pop("type", AbsenceType.permit), **campi)
    db.add(a)
    await db.commit()
    return a


class TestIntervallo:
    async def test_prende_quelle_che_toccano_l_intervallo(self, client, db, admin_tokens, collaborator):
        dentro = await _assenza(db, collaborator, OGGI, OGGI, start_time=time(13), end_time=time(14), notes="Pausa pranzo")
        a_cavallo = await _assenza(db, collaborator, OGGI - timedelta(days=3), OGGI + timedelta(days=1), type=AbsenceType.vacation)
        prima = await _assenza(db, collaborator, OGGI - timedelta(days=20), OGGI - timedelta(days=10))
        dopo = await _assenza(db, collaborator, OGGI + timedelta(days=30), OGGI + timedelta(days=31))

        r = await client.get(URL, headers=auth(admin_tokens), params={
            "start_date": OGGI.isoformat(), "end_date": (OGGI + timedelta(days=6)).isoformat(),
        })
        assert r.status_code == 200, r.text
        ids = {a["id"] for a in r.json()}
        assert ids == {dentro.id, a_cavallo.id}
        assert prima.id not in ids and dopo.id not in ids
        permesso = next(a for a in r.json() if a["id"] == dentro.id)
        assert (permesso["start_time"], permesso["end_time"], permesso["notes"]) == ("13:00:00", "14:00:00", "Pausa pranzo")

    async def test_il_collaboratore_le_vede(self, client, db, collab_tokens, collaborator):
        await _assenza(db, collaborator, OGGI, OGGI, start_time=time(13), end_time=time(14))
        r = await client.get(URL, headers=auth(collab_tokens), params={
            "start_date": OGGI.isoformat(), "end_date": OGGI.isoformat(),
        })
        assert r.status_code == 200
        assert len(r.json()) == 1

    async def test_la_cliente_no(self, client, client_tokens):
        r = await client.get(URL, headers=auth(client_tokens), params={
            "start_date": OGGI.isoformat(), "end_date": OGGI.isoformat(),
        })
        assert r.status_code == 401

    async def test_intervalli_sbagliati(self, client, admin_tokens):
        rovescio = await client.get(URL, headers=auth(admin_tokens), params={
            "start_date": OGGI.isoformat(), "end_date": (OGGI - timedelta(days=1)).isoformat(),
        })
        assert rovescio.status_code == 400
        enorme = await client.get(URL, headers=auth(admin_tokens), params={
            "start_date": OGGI.isoformat(), "end_date": (OGGI + timedelta(days=400)).isoformat(),
        })
        assert enorme.status_code == 400
