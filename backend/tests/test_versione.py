"""La versione che il backend dichiara è quella del rilascio.

`scripts/release.py` la scrive in `app/version.py` e in
`frontend/package.json`; qui si controlla che `/health` e l'OpenAPI la
dicano, e che coincida con quella del frontend — la stessa cosa che fa il
job «Versione», ripetuta dove gira la suite del backend.
"""
import json
from pathlib import Path

import pytest

from app.main import app
from app.version import __version__

pytestmark = pytest.mark.asyncio


async def test_health_dice_la_versione(client):
    r = await client.get("/health")
    assert r.json() == {"status": "ok", "version": __version__}


async def test_openapi_dice_la_versione():
    assert app.version == __version__


async def test_coincide_col_frontend():
    pkg = Path(__file__).resolve().parents[2] / "frontend" / "package.json"
    assert json.loads(pkg.read_text())["version"] == __version__
