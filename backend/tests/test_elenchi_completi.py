"""Gli elenchi paginati, letti pagina per pagina, danno ogni riga una volta.

Segnalazione di Flavia del 2026-10-08: «li carico faccio salva e non escono,
si è fermato a 20». I prodotti venivano salvati, ma il magazzino chiedeva
solo la prima pagina — 20 righe — e il ventunesimo in ordine alfabetico non
compariva. Lo stesso, senza che nessuno se ne accorgesse, per la Cassa e le
Spese (50 per pagina, e i totali si sommano nel browser) e per il calendario
(200 appuntamenti).

La correzione vera sta nel frontend, che adesso legge tutte le pagine
(`tutteLePagine` in `services/api.ts`). Qui il pezzo che la rende corretta:
leggere tutte le pagine dà tutte le righe **solo se l'ordine è totale**.
Con righe a pari merito sulla chiave d'ordinamento — stesso nome, stessa
data, stessa ora d'inizio, cosa normalissima in un salone — Postgres può
metterle in un ordine diverso a ogni `OFFSET`, e la stessa riga finisce su
due pagine mentre un'altra su nessuna. Per questo ogni elenco ha l'`id` come
ultimo criterio, e qui le righe sono tutte a pari merito apposta.
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models.appointment import Appointment, AppointmentStatus
from app.models.client import Client
from app.models.expense import Expense
from app.models.payment import Payment, PaymentMethod
from app.models.product import Product
from app.models.service import Service
from app.utils.tempo import istante
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio

QUANTE = 23
PER_PAGINA = 5


async def _tutte_le_pagine(client, tokens, url, params=None):
    """Come il frontend: la prima pagina, poi tutte le altre."""
    ids, page = [], 1
    while True:
        r = await client.get(url, headers=auth(tokens), params={
            **(params or {}), "page": page, "page_size": PER_PAGINA,
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
        ids += [x["id"] for x in corpo["items"]]
        if page >= corpo["pages"]:
            return ids, corpo["total"]
        page += 1


def _una_volta_ciascuna(letti, attesi):
    assert len(letti) == len(set(letti)), "una riga è comparsa su due pagine"
    assert set(letti) == set(attesi), "una riga non è comparsa su nessuna pagina"


async def test_i_prodotti_oltre_il_ventesimo(client, db, admin_tokens):
    """Il caso di Flavia: più di 20 prodotti, tutti con lo stesso nome."""
    prodotti = [
        Product(name="Shampoo", purchase_price=5, sale_price=10, category="Rivendita")
        for _ in range(QUANTE)
    ]
    db.add_all(prodotti)
    await db.commit()

    letti, totale = await _tutte_le_pagine(client, admin_tokens, "/api/admin/products")
    assert totale == QUANTE
    _una_volta_ciascuna(letti, [p.id for p in prodotti])


async def test_gli_incassi_della_giornata(client, db, admin_tokens):
    """Salvati nella stessa transazione: `now()` dà a tutti la stessa data."""
    incassi = [Payment(amount=10, method=PaymentMethod.cash) for _ in range(QUANTE)]
    db.add_all(incassi)
    await db.commit()

    letti, _ = await _tutte_le_pagine(client, admin_tokens, "/api/admin/payments")
    _una_volta_ciascuna(letti, [p.id for p in incassi])


async def test_le_spese_dello_stesso_giorno(client, db, admin_tokens):
    oggi = date.today()
    spese = [
        Expense(description="Caffè", amount=1, category="Varie", date=oggi)
        for _ in range(QUANTE)
    ]
    db.add_all(spese)
    await db.commit()

    letti, _ = await _tutte_le_pagine(client, admin_tokens, "/api/admin/expenses")
    _una_volta_ciascuna(letti, [s.id for s in spese])


async def test_i_servizi(client, db, admin_tokens):
    servizi = [
        Service(name="Piega", price=20, duration_slots=1, category="Piega")
        for _ in range(QUANTE)
    ]
    db.add_all(servizi)
    await db.commit()

    letti, _ = await _tutte_le_pagine(client, admin_tokens, "/api/admin/services")
    _una_volta_ciascuna(letti, [s.id for s in servizi])


async def test_le_clienti_omonime(client, db, admin_tokens):
    clienti = [
        Client(first_name="Maria", last_name="Rossi", phone=f"+39333000{i:04d}")
        for i in range(QUANTE)
    ]
    db.add_all(clienti)
    await db.commit()

    letti, _ = await _tutte_le_pagine(client, admin_tokens, "/api/admin/clients")
    _una_volta_ciascuna(letti, [c.id for c in clienti])


async def test_gli_appuntamenti_alla_stessa_ora(
    client, db, admin_tokens, collaborator, other_client,
):
    """Il calendario: tante clienti che cominciano tutte alle 9."""
    giorno = giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=3)).date()
    inizio = istante(giorno, time(9, 0))
    appuntamenti = [
        Appointment(
            client_id=other_client.id, collaborator_id=collaborator.id,
            start_time=inizio, end_time=inizio + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
        )
        for _ in range(QUANTE)
    ]
    db.add_all(appuntamenti)
    await db.commit()

    letti, _ = await _tutte_le_pagine(client, admin_tokens, "/api/admin/appointments", {
        "date_from": f"{giorno}T00:00:00", "date_to": f"{giorno}T23:59:59",
    })
    _una_volta_ciascuna(letti, [a.id for a in appuntamenti])
