"""La documentazione dell'API non è pubblica fuori dallo sviluppo.

Fino al 2026-11-10 `/docs` e `/openapi.json` rispondevano 200 in produzione:
la mappa di tutte le rotte a disposizione di chiunque. La suite gira con
`APP_ENV=test`, cioè come la produzione da questo punto di vista.
"""
import pytest

from app.main import app, documentazione_api

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("percorso", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
async def test_chiusa_fuori_dallo_sviluppo(client, percorso):
    r = await client.get(percorso)
    assert r.status_code == 404, (percorso, r.status_code)


@pytest.mark.parametrize("ambiente", ["production", "test", "staging", ""])
async def test_solo_development_la_apre(ambiente):
    assert documentazione_api(ambiente) == {"docs_url": None, "redoc_url": None, "openapi_url": None}


async def test_in_sviluppo_resta():
    """Vuoto = i default di FastAPI: `/docs`, `/redoc`, `/openapi.json`."""
    assert documentazione_api("development") == {}


async def test_lo_schema_si_genera_ancora():
    """Chiusa la rotta, non lo schema: serve a chi lo chiede da codice."""
    assert app.openapi()["info"]["title"].startswith("New Style Hair")


async def test_le_altre_rotte_non_cambiano(client):
    assert (await client.get("/health")).status_code == 200
