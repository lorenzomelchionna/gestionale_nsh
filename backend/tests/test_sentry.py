"""
Cosa parte verso Sentry, che è un servizio esterno.

L'SDK di Sentry per default allega a ogni errore il corpo della richiesta e le
variabili locali di ogni riga dello stack. In questo gestionale vuol dire nomi,
telefoni e note delle clienti, e nel login la password in chiaro. Questi test
fanno girare l'SDK vero con un trasporto finto, provocano un errore dentro
una richiesta che porta tutte quelle cose, e controllano l'evento che sarebbe
partito.
"""
import json

import pytest
import sentry_sdk
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sentry_sdk.transport import Transport

from app import osservabilita
from app.config import settings
from app.main import app

TELEFONO = "+393331234567"
EMAIL = "mario.rossi@gmail.com"
PASSWORD = "Segretissima-123"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJhLWZpbnRh"


class TrasportoFinto(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.eventi: list[dict] = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.eventi.append(json.loads(item.get_bytes()))


async def _esplode(telefono: str, request: Request):
    corpo = await request.json()
    password = corpo["password"]  # noqa: F841 — una variabile locale col segreto
    raise RuntimeError(f"duplicato: Key (email)=({EMAIL}) telefono {telefono} token {JWT}")


@pytest.fixture
def rotta_che_esplode():
    """Aggiunta solo per il test e tolta subito: resta fuori dalla matrice
    dei permessi, che controlla ogni rotta dell'app."""
    app.router.add_api_route("/__prova_sentry/{telefono}", _esplode, methods=["POST"])
    rotta = app.router.routes[-1]
    yield
    app.router.routes.remove(rotta)


@pytest.fixture
def sentry(monkeypatch, rotta_che_esplode):
    """L'SDK vero, con le opzioni di produzione e un trasporto che trattiene."""
    trasporto = TrasportoFinto()
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://chiave@esempio.invalid/1")
    monkeypatch.setattr(osservabilita, "_visti", {})
    originale = sentry_sdk.init

    def init(**opzioni):
        return originale(transport=trasporto, **opzioni)

    monkeypatch.setattr(sentry_sdk, "init", init)
    assert osservabilita.avvia_sentry("backend") is True
    yield trasporto
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # spento: nessun DSN


async def _provoca(_client):
    # Un client suo: quello dei test rilancia le eccezioni dell'app invece di
    # restituire il 500, e qui serve il percorso vero fino alla risposta.
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
                           base_url="http://test") as client:
        r = await client.post(
            f"/__prova_sentry/{TELEFONO}?cerca=Rossi",
            json={"password": PASSWORD, "note": "allergica alla tinta", "email": EMAIL},
            headers={"Authorization": f"Bearer {JWT}", "Cookie": "sessione=abc"},
        )
    assert r.status_code == 500
    sentry_sdk.flush()


class TestCosaParte:
    async def test_un_errore_arriva(self, client, sentry):
        await _provoca(client)
        assert sentry.eventi, "nessun evento: Sentry non vede gli errori dell'API"
        evento = sentry.eventi[0]
        assert evento["release"].endswith(osservabilita.__version__)
        assert evento["tags"]["servizio"] == "backend"

    async def test_nessun_dato_personale_o_segreto(self, client, sentry):
        await _provoca(client)
        tutto = json.dumps(sentry.eventi)
        for vietato in (TELEFONO, "3331234567", EMAIL, PASSWORD, JWT, "allergica", "Rossi", "sessione=abc"):
            assert vietato not in tutto, f"{vietato!r} è finito nell'evento"

    async def test_niente_corpo_ne_variabili_locali(self, client, sentry):
        await _provoca(client)
        evento = sentry.eventi[0]
        assert "data" not in evento.get("request", {})
        for ecc in evento["exception"]["values"]:
            for frame in (ecc.get("stacktrace") or {}).get("frames", []):
                assert "vars" not in frame

    async def test_il_messaggio_resta_leggibile(self, client, sentry):
        """Mascherato, non cancellato: si deve ancora capire cos'è successo."""
        await _provoca(client)
        tutto = json.dumps(sentry.eventi)
        assert "duplicato" in tutto
        assert "m***i@gmail.com" in tutto


def test_lo_stesso_errore_non_consuma_la_quota(monkeypatch):
    monkeypatch.setattr(osservabilita, "_visti", {})
    evento = {"exception": {"values": [{"type": "X", "stacktrace": {"frames": [{"module": "m", "lineno": 1}]}}]}}
    partiti = [osservabilita.prepara_evento(json.loads(json.dumps(evento))) for _ in range(20)]
    assert sum(e is not None for e in partiti) == osservabilita.MAX_PER_ERRORE

    altro = {"exception": {"values": [{"type": "Y", "stacktrace": {"frames": [{"module": "m", "lineno": 2}]}}]}}
    assert osservabilita.prepara_evento(altro) is not None, "un errore diverso deve passare"


def test_senza_dsn_resta_spento(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", None)
    assert osservabilita.avvia_sentry("backend") is False


@pytest.mark.parametrize("testo, atteso", [
    ("chiamato 1234 volte", "chiamato 1234 volte"),          # numeri piccoli restano
    ("appuntamento 2026-11-22", "appuntamento 2026-11-22"),  # le date restano
    ("tel 333 123 4567", "tel 33***4567"),
    ("login fallito password=Segreta1 utente 3", "login fallito password=«omesso» utente 3"),
])
def test_telefoni_mascherati_il_resto_no(testo, atteso):
    assert osservabilita.ripulisci(testo) == atteso
