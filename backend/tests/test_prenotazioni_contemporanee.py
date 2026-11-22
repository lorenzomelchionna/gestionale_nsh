"""
Due clienti, stesso collaboratore, stesso orario, nello stesso istante.

`valida_prenotazione` legge gli slot liberi e `registra_prenotazione` scrive
l'appuntamento, in due momenti distinti. Senza niente in mezzo, due richieste
contemporanee leggevano entrambe lo slot libero e venivano registrate
entrambe: due richieste «in attesa» sullo stesso posto, e il salone si
accorgeva del doppione solo confermando.

Le richieste reali arrivano a pochi millisecondi l'una dall'altra, troppo
pochi perché un test le faccia scontrare ogni volta. Per questo la lettura
degli slot qui è rallentata: senza blocco, la seconda richiesta legge mentre
la prima sta ancora aspettando di scrivere, che è esattamente la corsa da
escludere. Con il blocco la seconda aspetta il commit della prima e poi
trova l'orario occupato.
"""
import asyncio
from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.api.public import booking
from app.models.appointment import Appointment
from tests.conftest import auth, giorno_lavorativo

GIORNO = giorno_lavorativo((datetime.now(timezone.utc) + timedelta(days=2)).date())
RITARDO = 0.3


@pytest.fixture
def lettura_lenta(monkeypatch):
    """Allarga la finestra fra lettura degli slot e scrittura."""
    originale = booking.get_available_slots

    async def lenta(*args, **kwargs):
        slots = await originale(*args, **kwargs)
        await asyncio.sleep(RITARDO)
        return slots

    monkeypatch.setattr(booking, "get_available_slots", lenta)


def _richiesta(collaboratore, servizio, ora: int):
    inizio = datetime.combine(GIORNO, time(ora, 0), tzinfo=timezone.utc)
    return {
        "client_id": 0,
        "collaborator_id": collaboratore.id,
        "start_time": inizio.isoformat(),
        "end_time": (inizio + timedelta(hours=1)).isoformat(),
        "service_ids": [servizio.id],
    }


async def _quanti(db, collaboratore) -> int:
    return (await db.execute(
        select(func.count()).select_from(Appointment)
        .where(Appointment.collaborator_id == collaboratore.id)
    )).scalar_one()


async def test_stesso_orario_una_sola_passa(
    client, db, booking_config, client_tokens, collaborator, service, lettura_lenta,
):
    corpo = _richiesta(collaborator, service, 10)
    risposte = await asyncio.gather(*(
        client.post("/api/public/appointments", headers=auth(client_tokens), json=corpo)
        for _ in range(2)
    ))

    stati = sorted(r.status_code for r in risposte)
    assert stati == [201, 409], [r.text for r in risposte]
    assert "non è più disponibile" in next(r for r in risposte if r.status_code == 409).text
    assert await _quanti(db, collaborator) == 1


async def test_orari_diversi_passano_entrambi(
    client, db, booking_config, client_tokens, collaborator, service, lettura_lenta,
):
    """Il blocco mette in fila, non rifiuta: due orari che non si toccano,
    sullo stesso collaboratore e giorno, vanno registrati tutti e due."""
    risposte = await asyncio.gather(
        client.post("/api/public/appointments", headers=auth(client_tokens),
                    json=_richiesta(collaborator, service, 10)),
        client.post("/api/public/appointments", headers=auth(client_tokens),
                    json=_richiesta(collaborator, service, 13)),
    )

    assert [r.status_code for r in risposte] == [201, 201], [r.text for r in risposte]
    assert await _quanti(db, collaborator) == 2
