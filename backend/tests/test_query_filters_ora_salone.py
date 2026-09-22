"""
I filtri per data dell'agenda e degli incassi leggevano ore del salone come
se fossero UTC.

`CalendarPage.tsx`, `AppointmentsPage.tsx` e `CashPage.tsx` mandano
`date_from`/`date_to` come stringhe senza fuso — `"2026-06-22T00:00:00"` —
scritte dal browser nel fuso di chi lavora in salone (Roma). FastAPI le
legge come `datetime` **senza fuso**, e passate così com'sono a una colonna
`timestamptz`, il driver le interpreta secondo il fuso **del processo**
Python — non quello della sessione Postgres, non UTC per definizione:
misurato qui, forzando `TZ=UTC` e `TZ=Europe/Rome` sullo stesso codice e
vedendo il confine spostarsi di due ore.

Su Railway il processo non ha `TZ` impostata, quindi il container gira nel
fuso di default (UTC): un filtro per "22 giugno" scritto da un browser a
Roma diventava una finestra UTC, spostata di un'ora o due rispetto a quella
che l'utente intendeva — la stessa famiglia di difetto già chiusa altrove
in questo file (vedi `tempo.py`), qui sui filtri invece che sugli slot.

I test bloccano `TZ` esplicitamente sul processo di test (via
`istante_da_ingresso`, che non dipende affatto dal fuso del processo) e
usano un istante costruito ad arte: le 23:00 UTC del 21 giugno sono le
01:00 del 22 giugno a Roma (CEST, +2) — "ieri" in UTC, "oggi" a Roma.
"""
import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentOrigin, AppointmentStatus
from app.models.client import Client
from app.models.payment import Payment, PaymentMethod

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def fuso_del_processo_fisso_a_utc():
    """Il difetto qui dentro dipende dal fuso *del processo*, non da una
    costante del codice — misurato sopra, cambia risultato fra `TZ=UTC` e
    `TZ=Europe/Rome` sullo stesso identico codice. Railway non ha `TZ`
    impostata, quindi gira nel fuso di default del container (UTC); il Mac
    di chi sviluppa di solito è Europe/Rome, che per puro caso **coincide**
    col fuso del salone e nasconderebbe il difetto. Si fissa `TZ=UTC` solo
    per la durata di questi test, non per l'ambiente della suite, così il
    test misura la stessa cosa ovunque giri e non lascia lo stato cambiato
    per i test che vengono dopo nello stesso processo."""
    precedente = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    yield
    if precedente is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = precedente
    time.tzset()

# 23:00 UTC del 21 giugno = 01:00 del 22 giugno a Roma (CEST, +2).
ISTANTE_TARDA_NOTTE = datetime(2026, 6, 21, 23, 0, 0, tzinfo=timezone.utc)


class TestFiltroAppuntamentiUsaIlGiornoDelSalone:
    async def test_appuntamento_di_prima_mattina_a_roma_e_nel_22_giugno(
        self, client, db, admin_tokens, client_account, collaborator
    ):
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        db.add(Appointment(
            client_id=cliente.id, collaborator_id=collaborator.id,
            start_time=ISTANTE_TARDA_NOTTE, end_time=ISTANTE_TARDA_NOTTE + timedelta(hours=1),
            status=AppointmentStatus.confirmed, origin=AppointmentOrigin.salon,
        ))
        await db.commit()

        # Come CalendarPage.tsx/AppointmentsPage.tsx costruiscono il filtro
        # per una giornata: stringa senza fuso, cifre di orologio di Roma.
        resp = await client.get(
            "/api/admin/appointments",
            params={"date_from": "2026-06-22T00:00:00", "date_to": "2026-06-22T23:59:59"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert resp.status_code == 200
        trovati = [a["id"] for a in resp.json()["items"]]
        assert len(trovati) == 1, (
            "un appuntamento delle 01:00 a Roma deve comparire nel filtro per "
            "il 22 giugno (il suo giorno a Roma), non sparire perché in UTC è "
            "ancora il 21"
        )

    async def test_non_compare_nel_giorno_prima_solo_perche_la_finestra_si_e_allargata(
        self, client, db, admin_tokens, client_account, collaborator
    ):
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        db.add(Appointment(
            client_id=cliente.id, collaborator_id=collaborator.id,
            start_time=ISTANTE_TARDA_NOTTE, end_time=ISTANTE_TARDA_NOTTE + timedelta(hours=1),
            status=AppointmentStatus.confirmed, origin=AppointmentOrigin.salon,
        ))
        await db.commit()

        resp = await client.get(
            "/api/admin/appointments",
            params={"date_from": "2026-06-21T00:00:00", "date_to": "2026-06-21T23:59:59"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == [], (
            "l'appuntamento è del 22 giugno a Roma: il filtro per il 21 non "
            "deve trovarlo"
        )


class TestFiltroIncassiUsaIlGiornoDelSalone:
    async def test_incasso_di_prima_mattina_a_roma_e_nel_22_giugno(
        self, client, db, admin_tokens, client_account
    ):
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        db.add(Payment(
            client_id=cliente.id, amount=25.0,
            method=PaymentMethod.cash, date=ISTANTE_TARDA_NOTTE,
        ))
        await db.commit()

        # Come CashPage.tsx costruisce il filtro.
        resp = await client.get(
            "/api/admin/payments",
            params={"date_from": "2026-06-22T00:00:00", "date_to": "2026-06-22T23:59:59"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert resp.status_code == 200
        totale = sum(p["amount"] for p in resp.json()["items"])
        assert totale == pytest.approx(25.0), (
            "un incasso delle 01:00 a Roma deve comparire nella cassa del 22 "
            "giugno (il suo giorno a Roma)"
        )
