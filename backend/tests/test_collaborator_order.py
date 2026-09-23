"""L'ordine delle colonne del calendario lo sceglie il salone.

Richiesta di Flavia (2026-09-23): Vincenzo al centro. Guardandoci si è visto
che l'elenco dei collaboratori non aveva **nessun ORDER BY**: usciva
nell'ordine fisico delle righe, che Postgres non promette e che un UPDATE
rimescola — la riga modificata diventa una tupla nuova, e una scansione la
restituisce in fondo. Quindi l'ordine non era solo sbagliato ma instabile:
bastava correggere il telefono di un collaboratore per spostarne la colonna.
`TestStabile` fissa proprio quel caso.
"""
import pytest

from app.models.collaborator import Collaborator

from tests.conftest import auth

pytestmark = pytest.mark.asyncio


async def _crea(client, tokens, nome: str) -> int:
    r = await client.post(
        "/api/admin/collaborators",
        json={"first_name": nome, "last_name": "Test"},
        headers=auth(tokens),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _nomi_admin(client, tokens) -> list[str]:
    r = await client.get("/api/admin/collaborators", headers=auth(tokens))
    assert r.status_code == 200, r.text
    return [c["first_name"] for c in r.json()["items"]]


async def _nomi_portale(client) -> list[str]:
    r = await client.get("/api/public/collaborators")
    assert r.status_code == 200, r.text
    return [c["first_name"] for c in r.json()]


class TestRiordino:
    async def test_vincenzo_al_centro(self, client, admin_tokens):
        """Il caso della richiesta, con gli id nell'ordine della produzione."""
        flavia = await _crea(client, admin_tokens, "Flavia")
        raffaella = await _crea(client, admin_tokens, "Raffaella")
        vincenzo = await _crea(client, admin_tokens, "Vincenzo")

        r = await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [flavia, vincenzo, raffaella]},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 204, r.text
        assert await _nomi_admin(client, admin_tokens) == ["Flavia", "Vincenzo", "Raffaella"]

    async def test_il_portale_segue_lo_stesso_ordine(self, client, admin_tokens):
        """La cliente che sceglie con chi prenotare vede lo stesso ordine del
        calendario: due ordini diversi per le stesse tre persone sarebbero
        un'incoerenza che qualcuno prima o poi nota."""
        a = await _crea(client, admin_tokens, "Anna")
        b = await _crea(client, admin_tokens, "Bea")
        c = await _crea(client, admin_tokens, "Carla")

        await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [c, a, b]},
            headers=auth(admin_tokens),
        )
        assert await _nomi_portale(client) == ["Carla", "Anna", "Bea"]

    async def test_un_nuovo_collaboratore_va_in_fondo(self, client, admin_tokens):
        a = await _crea(client, admin_tokens, "Anna")
        b = await _crea(client, admin_tokens, "Bea")
        await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [b, a]},
            headers=auth(admin_tokens),
        )
        await _crea(client, admin_tokens, "Carla")
        assert await _nomi_admin(client, admin_tokens) == ["Bea", "Anna", "Carla"]


class TestStabile:
    async def test_modificare_un_collaboratore_non_ne_sposta_la_colonna(
        self, client, admin_tokens
    ):
        """Il difetto che c'era prima della richiesta: senza ORDER BY la riga
        aggiornata tornava in fondo all'elenco."""
        a = await _crea(client, admin_tokens, "Anna")
        await _crea(client, admin_tokens, "Bea")
        await _crea(client, admin_tokens, "Carla")

        r = await client.put(
            f"/api/admin/collaborators/{a}",
            json={"phone": "+393331112222"},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 200, r.text
        assert await _nomi_admin(client, admin_tokens) == ["Anna", "Bea", "Carla"]


class TestRifiuti:
    """Un elenco che non combacia viene rifiutato per intero: un ordine
    applicato a metà lascerebbe due collaboratori sulla stessa posizione."""

    async def test_elenco_incompleto(self, client, admin_tokens):
        a = await _crea(client, admin_tokens, "Anna")
        await _crea(client, admin_tokens, "Bea")
        r = await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [a]},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 400

    async def test_id_inesistente(self, client, admin_tokens):
        a = await _crea(client, admin_tokens, "Anna")
        r = await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [a, 99999]},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 400

    async def test_doppione(self, client, admin_tokens):
        a = await _crea(client, admin_tokens, "Anna")
        b = await _crea(client, admin_tokens, "Bea")
        r = await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [a, b, a]},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 400

    async def test_il_rifiuto_non_tocca_l_ordine(self, client, admin_tokens):
        a = await _crea(client, admin_tokens, "Anna")
        b = await _crea(client, admin_tokens, "Bea")
        await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [b, a, 99999]},
            headers=auth(admin_tokens),
        )
        assert await _nomi_admin(client, admin_tokens) == ["Anna", "Bea"]

    async def test_i_disattivati_fanno_parte_dell_elenco(self, client, admin_tokens):
        """Un collaboratore disattivato resta in anagrafica e può tornare:
        l'ordine lo comprende, altrimenti al suo ritorno finirebbe su una
        posizione già occupata."""
        a = await _crea(client, admin_tokens, "Anna")
        b = await _crea(client, admin_tokens, "Bea")
        await client.delete(f"/api/admin/collaborators/{b}", headers=auth(admin_tokens))

        r = await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [a]},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 400

        r = await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [b, a]},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 204


class TestPermessi:
    async def test_un_collaboratore_non_riordina(
        self, client, admin_tokens, collab_tokens
    ):
        a = await _crea(client, admin_tokens, "Anna")
        r = await client.put(
            "/api/admin/collaborators/order",
            json={"ids": [a]},
            headers=auth(collab_tokens),
        )
        assert r.status_code == 403
