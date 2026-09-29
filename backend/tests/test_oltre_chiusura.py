"""La fascia dopo la chiusura: il salone ci prenota, le clienti no.

Richiesta del 2026-09-29: il salone apre alle 8 e chiude alle 19, ma fra le
19 e le 20 capita di tenere una cliente. Quell'ora deve restare prenotabile
dal gestionale e mai dal portale.

La regola non sta in una costante: il portale offre solo ciò che cade dentro
l'orario di lavoro del collaboratore (in produzione 08:00–19:00), il
gestionale non lo controlla. Questi test fissano le due metà, così che nessuno
«sistemi» l'una senza accorgersi dell'altra — aggiungere al gestionale il
controllo sugli orari toglierebbe al salone proprio la fascia che chiede.
"""
from datetime import datetime, time, timedelta, timezone

import pytest
import pytest_asyncio

from app.utils.tempo import istante
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def giorno(collaborator):
    # Il fixture `collaborator` chiude alle 19:00; `service` dura un'ora.
    return giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=2)).date()


async def test_il_portale_non_offre_niente_che_finisca_dopo_le_19(
    client, booking_config, collaborator, service, giorno,
):
    r = await client.get("/api/public/availability", params={
        "service_id": service.id,
        "collaborator_id": collaborator.id,
        "target_date": giorno.isoformat(),
    })
    assert r.status_code == 200, r.text
    orari = [datetime.fromisoformat(s) for s in r.json()]
    assert max(orari) == istante(giorno, time(18, 0)), "l'ultima ora utile è 18:00–19:00"
    assert istante(giorno, time(19, 0)) not in orari


async def test_il_portale_rifiuta_le_19(
    client, booking_config, client_tokens, collaborator, service, giorno,
):
    inizio = istante(giorno, time(19, 0))
    r = await client.post("/api/public/appointments", headers=auth(client_tokens), json={
        "client_id": 0,
        "collaborator_id": collaborator.id,
        "start_time": inizio.isoformat(),
        "end_time": (inizio + timedelta(hours=1)).isoformat(),
        "service_ids": [service.id],
    })
    assert r.status_code == 409, r.text


async def test_il_salone_prenota_fra_le_19_e_le_20(
    client, booking_config, admin_tokens, collaborator, service, other_client, giorno,
):
    inizio = istante(giorno, time(19, 0))
    r = await client.post("/api/admin/appointments", headers=auth(admin_tokens), json={
        "client_id": other_client.id,
        "collaborator_id": collaborator.id,
        "start_time": inizio.isoformat(),
        "end_time": (inizio + timedelta(hours=1)).isoformat(),
        "service_ids": [service.id],
    })
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "confirmed"
