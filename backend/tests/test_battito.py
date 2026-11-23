"""
Il battito del worker (`app/battito.py`): il giro dei promemoria dice a un
servizio esterno che beat e worker girano. Un guasto che non solleva errori
(beat fermo, worker appeso) diventa così un allarme invece di un silenzio.
"""
import httpx
import pytest

from app import battito
from app.config import settings
from app.tasks import reminders

URL = "https://uptime.esempio.invalid/api/v1/heartbeat/abc123"


@pytest.fixture
def chiamate(monkeypatch):
    fatte: list[str] = []

    def get(url, timeout):
        fatte.append(url)
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(settings, "HEARTBEAT_URL", URL)
    monkeypatch.setattr(battito.httpx, "get", get)
    return fatte


def test_giro_riuscito_batte(monkeypatch, chiamate):
    monkeypatch.setattr(reminders, "_run_async", lambda coro: coro.close())
    reminders.send_appointment_reminders()
    assert chiamate == [URL]


def test_giro_fallito_segnala_subito(monkeypatch, chiamate):
    def esplode(coro):
        coro.close()
        raise RuntimeError("db giù")

    monkeypatch.setattr(reminders, "_run_async", esplode)
    with pytest.raises(RuntimeError):
        reminders.send_appointment_reminders()
    assert chiamate == [URL + "/fail"]


def test_senza_url_non_chiama_niente(monkeypatch):
    monkeypatch.setattr(settings, "HEARTBEAT_URL", None)
    monkeypatch.setattr(battito.httpx, "get", lambda *a, **k: pytest.fail("chiamato"))
    battito.batti()


def test_servizio_irraggiungibile_non_rompe_e_non_scrive_l_url(monkeypatch, caplog):
    def giu(url, timeout):
        raise httpx.ConnectError(f"impossibile raggiungere {url}")

    monkeypatch.setattr(settings, "HEARTBEAT_URL", URL)
    monkeypatch.setattr(battito.httpx, "get", giu)
    battito.batti()
    assert any(r.getMessage() == "battito non inviato" for r in caplog.records)
    assert "abc123" not in caplog.text
