"""
L'elenco completo degli appuntamenti.

Richiesta di Flavia (2026-08-04), che l'aveva messa come facoltativa: oggi
esistono solo il calendario, che mostra una giornata alla volta, e «In
attesa», che mostra un solo stato. Per rispondere a «quando è venuta l'ultima
volta?» non c'era nessuna schermata.

`GET /appointments` esisteva già con data, collaboratore e stato. Qui si
aggiungono le tre cose che servono a un elenco storico e mancavano: la
ricerca per cliente, il filtro per cliente e l'ordine invertito.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.appointment import (
    Appointment, AppointmentService, AppointmentStatus, AppointmentOrigin,
)
from app.models.client import Client
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

BASE = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def storico(db, collaborator, service):
    """Tre clienti, quattro visite in giorni diversi."""
    clienti = [
        Client(first_name="Anna", last_name="Verdi", phone="+393331110001"),
        Client(first_name="Bruno", last_name="Rossi", phone="+393331110002"),
        Client(first_name="Carla", last_name="Verdi", phone="+393339990003"),
    ]
    for c in clienti:
        db.add(c)
    await db.flush()

    piano = [
        (clienti[0], 0, AppointmentStatus.completed),
        (clienti[1], 1, AppointmentStatus.completed),
        (clienti[2], 2, AppointmentStatus.cancelled),
        (clienti[0], 3, AppointmentStatus.confirmed),
    ]
    appuntamenti = []
    for cliente, giorni, stato in piano:
        start = BASE + timedelta(days=giorni)
        a = Appointment(
            client_id=cliente.id,
            collaborator_id=collaborator.id,
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=stato,
            origin=AppointmentOrigin.salon,
        )
        db.add(a)
        await db.flush()
        db.add(AppointmentService(
            appointment_id=a.id, service_id=service.id, price_snapshot=30.0
        ))
        appuntamenti.append(a)
    await db.commit()
    return {"clienti": clienti, "appuntamenti": appuntamenti}


async def elenco(client, tokens, **params):
    resp = await client.get(
        "/api/admin/appointments", headers=auth(tokens), params=params
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestRicercaPerCliente:
    async def test_per_nome(self, client, admin_tokens, storico):
        corpo = await elenco(client, admin_tokens, search="Bruno")
        assert corpo["total"] == 1
        assert corpo["items"][0]["client_name"] == "Bruno Rossi"

    async def test_per_cognome_prende_tutte_le_omonime(
        self, client, admin_tokens, storico
    ):
        corpo = await elenco(client, admin_tokens, search="Verdi")
        assert corpo["total"] == 3  # due di Anna, una di Carla

    async def test_per_telefono(self, client, admin_tokens, storico):
        """Al banco spesso si ha in mano solo il numero."""
        corpo = await elenco(client, admin_tokens, search="9990003")
        assert corpo["total"] == 1
        assert corpo["items"][0]["client_name"] == "Carla Verdi"

    async def test_nome_e_cognome_insieme(self, client, admin_tokens, storico):
        """Nessuna colonna contiene «Anna Verdi»: è la concatenazione a
        doverlo trovare, ed è il modo in cui un nome viene digitato."""
        corpo = await elenco(client, admin_tokens, search="Anna Verdi")
        assert corpo["total"] == 2

    async def test_non_distingue_maiuscole(self, client, admin_tokens, storico):
        assert (await elenco(client, admin_tokens, search="rOsSi"))["total"] == 1

    async def test_una_lettera_sola_viene_rifiutata(
        self, client, admin_tokens, storico
    ):
        """Una lettera restituirebbe mezzo archivio: non è una ricerca."""
        resp = await client.get(
            "/api/admin/appointments", headers=auth(admin_tokens), params={"search": "a"}
        )
        assert resp.status_code == 422


class TestFiltriEOrdine:
    async def test_filtro_per_cliente(self, client, admin_tokens, storico):
        anna = storico["clienti"][0]
        corpo = await elenco(client, admin_tokens, client_id=anna.id)
        assert corpo["total"] == 2
        assert {i["client_id"] for i in corpo["items"]} == {anna.id}

    async def test_ordine_invertito(self, client, admin_tokens, storico):
        """L'elenco storico parte da ieri e va all'indietro."""
        corpo = await elenco(client, admin_tokens, order="desc")
        date = [i["start_time"] for i in corpo["items"]]
        assert date == sorted(date, reverse=True)

    async def test_il_default_resta_crescente(self, client, admin_tokens, storico):
        """Il calendario legge da qui e leggeva già una giornata in avanti:
        cambiare il default lo romperebbe in silenzio."""
        corpo = await elenco(client, admin_tokens)
        date = [i["start_time"] for i in corpo["items"]]
        assert date == sorted(date)

    async def test_ordine_inventato_rifiutato(self, client, admin_tokens, storico):
        resp = await client.get(
            "/api/admin/appointments", headers=auth(admin_tokens),
            params={"order": "casuale"},
        )
        assert resp.status_code == 422

    async def test_i_filtri_si_sommano(self, client, admin_tokens, storico):
        corpo = await elenco(
            client, admin_tokens, search="Verdi", status="completed"
        )
        assert corpo["total"] == 1
        assert corpo["items"][0]["client_name"] == "Anna Verdi"

    async def test_la_ricerca_conta_solo_le_righe_filtrate(
        self, client, admin_tokens, storico
    ):
        """Il totale serve alla paginazione: contato sulla query senza filtro
        direbbe che ci sono altre pagine, e la seconda sarebbe vuota."""
        corpo = await elenco(client, admin_tokens, search="Bruno", page_size=1)
        assert corpo["total"] == 1
        assert corpo["pages"] == 1


class TestPermessi:
    async def test_il_collaboratore_puo_leggere_l_elenco(
        self, client, collab_tokens, storico
    ):
        """Stesso permesso del calendario, che mostra già gli stessi
        appuntamenti — solo un giorno alla volta."""
        corpo = await elenco(client, collab_tokens)
        assert corpo["total"] == 4

    async def test_la_cliente_non_ci_arriva(self, client, client_tokens, storico):
        resp = await client.get(
            "/api/admin/appointments", headers=auth(client_tokens)
        )
        assert resp.status_code in (401, 403)
