"""
L'appuntamento da salvare nel calendario, nella mail di conferma
(`app/utils/calendario.py`): un `.ics` allegato e un link per Google
Calendar. Dentro solo servizio, data, ora e salone.
"""
import base64
import json
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentService, AppointmentStatus
from app.models.client import Client
from app.utils import calendario
from app.utils import email as email_util
from app.utils.tempo import istante


def _appuntamento(giorno=date(2026, 1, 15), ora=time(9, 0), servizi=("Taglio donna",), **extra):
    inizio = istante(giorno, ora)
    return SimpleNamespace(
        id=42,
        start_time=inizio,
        end_time=inizio + timedelta(minutes=45),
        appointment_services=[SimpleNamespace(service=SimpleNamespace(name=n)) for n in servizi],
        client=SimpleNamespace(first_name="Giulia", last_name="Segreta", email="g@example.com"),
        collaborator=SimpleNamespace(first_name="Flavia", last_name="Romolo"),
        replaces_appointment_id=None,
        **extra,
    )


def _campi(ics: bytes) -> dict:
    """Le righe del file, ricomposte (le righe lunghe sono spezzate)."""
    testo = ics.decode("utf-8").replace("\r\n ", "")
    out = {}
    for riga in testo.split("\r\n"):
        if ":" in riga:
            k, v = riga.split(":", 1)
            out.setdefault(k, v)
    return out


class TestIlFile:
    def test_orari_in_utc_dall_ora_del_salone(self):
        # Le 9 a Melito d'inverno sono le 8 UTC; d'estate le 7.
        inverno = _campi(calendario.file_ics(_appuntamento(date(2026, 1, 15))))
        estate = _campi(calendario.file_ics(_appuntamento(date(2026, 7, 15))))
        assert inverno["DTSTART"] == "20260115T080000Z"
        assert inverno["DTEND"] == "20260115T084500Z"
        assert estate["DTSTART"] == "20260715T070000Z"

    def test_contenuto(self):
        c = _campi(calendario.file_ics(_appuntamento(servizi=("Taglio donna", "Piega"))))
        assert c["SUMMARY"] == "New Style Hair – Taglio donna + Piega"
        assert c["LOCATION"] == "Corso Italia\\, 32\\, 83030 Melito Irpino (AV)"
        assert c["UID"] == "appuntamento-42@newstylehair.it"
        assert c["METHOD"] == "PUBLISH"
        assert "ORGANIZER" not in c and "ATTENDEE" not in c, "è un evento, non un invito"

    def test_niente_nomi_di_persone(self):
        """Un calendario personale si condivide: né la cliente né il collaboratore."""
        testo = calendario.file_ics(_appuntamento()).decode("utf-8")
        for nome in ("Giulia", "Segreta", "Flavia", "Romolo", "g@example.com"):
            assert nome not in testo

    def test_formato(self):
        ics = calendario.file_ics(_appuntamento(servizi=("Colore; meches, e un nome molto lungo che supera la riga",)))
        righe = ics.split(b"\r\n")
        assert ics.endswith(b"\r\n") and b"\n" not in ics.replace(b"\r\n", b"")
        assert all(len(r) <= 75 for r in righe), "RFC 5545: righe al massimo di 75 byte"
        assert "Colore\\; meches\\, e un nome" in _campi(ics)["SUMMARY"]

    def test_accentate_non_spezzate_a_meta(self):
        ics = calendario.file_ics(_appuntamento(servizi=("è" * 60,)))
        ics.decode("utf-8")  # solleverebbe se un carattere fosse tagliato in due
        assert _campi(ics)["SUMMARY"].endswith("è" * 60)


def test_link_google():
    url = calendario.link_google(_appuntamento())
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://calendar.google.com/calendar/render?")
    assert q["action"] == ["TEMPLATE"]
    assert q["dates"] == ["20260115T080000Z/20260115T084500Z"]
    assert q["text"] == ["New Style Hair – Taglio donna"]
    assert "Melito Irpino" in q["location"][0]


class TestNellaMail:
    async def test_la_conferma_porta_allegato_e_link(self, monkeypatch):
        partite = []

        async def finta(to, subject, html_body, allegati=None):
            partite.append((html_body, allegati))

        monkeypatch.setattr(email_util, "send_email", finta)
        await email_util.send_booking_confirmation_email(_appuntamento())

        corpo, allegati = partite[0]
        assert [(n, t) for n, _, t in allegati] == [("appuntamento.ics", "text/calendar")]
        assert b"BEGIN:VEVENT" in allegati[0][1]
        assert f"/api/public/calendario/42/appuntamento.ics?f={calendario.firma(42)}" in corpo
        assert "calendar.google.com/calendar/render?action=TEMPLATE&amp;" in corpo, "link con & protetti nell'HTML"
        assert "Calendario del telefono o del computer" in corpo and ">Google Calendar</a>" in corpo
        assert "orario precedente" not in corpo

    async def test_un_cambio_dice_di_cancellare_il_vecchio(self, monkeypatch):
        partite = []

        async def finta(to, subject, html_body, allegati=None):
            partite.append(html_body)

        monkeypatch.setattr(email_util, "send_email", finta)
        a = _appuntamento()
        a.replaces_appointment_id = 7
        await email_util.send_booking_confirmation_email(a)
        assert "orario precedente" in partite[0]

    async def test_brevo_riceve_l_allegato_in_base64(self, monkeypatch):
        mandato = {}

        class Risposta:
            status_code = 201
            text = ""
            def json(self):
                return {"messageId": "x"}

        class Client:
            def __init__(self, *a, **k): ...
            async def __aenter__(self): return self
            async def __aexit__(self, *a): ...
            async def post(self, url, json=None, headers=None):
                mandato.update(json)
                return Risposta()

        monkeypatch.setattr(email_util.httpx, "AsyncClient", Client)
        await email_util._send_via_brevo("a@b.it", "s", "<p>x</p>", [("appuntamento.ics", b"BEGIN:VCALENDAR", "text/calendar")])
        assert mandato["attachment"] == [{"name": "appuntamento.ics", "content": base64.b64encode(b"BEGIN:VCALENDAR").decode()}]

    async def test_senza_allegati_brevo_non_riceve_il_campo(self, monkeypatch):
        mandato = {}

        class Risposta:
            status_code = 201
            text = ""
            def json(self):
                return {}

        class Client:
            def __init__(self, *a, **k): ...
            async def __aenter__(self): return self
            async def __aexit__(self, *a): ...
            async def post(self, url, json=None, headers=None):
                mandato.update(json)
                return Risposta()

        monkeypatch.setattr(email_util.httpx, "AsyncClient", Client)
        await email_util._send_via_brevo("a@b.it", "s", "<p>x</p>")
        assert "attachment" not in mandato


async def test_il_worker_carica_i_servizi_per_il_titolo(db, client_account, collaborator, service, monkeypatch):
    """Il task della conferma caricava solo cliente e collaboratore: in un
    contesto async leggere i servizi dopo avrebbe fatto saltare l'invio."""
    from app.tasks import reminders
    from app.utils import notifications as notif

    partite = []

    async def finta(to, subject, html_body, allegati=None):
        partite.append(allegati)

    monkeypatch.setattr(email_util, "send_email", finta)
    monkeypatch.setattr(notif, "_wa_enabled", lambda cfg: False)

    cliente = (await db.execute(select(Client).where(Client.account_id == client_account.id))).scalar_one()
    inizio = datetime.now(timezone.utc) + timedelta(days=2)
    a = Appointment(client_id=cliente.id, collaborator_id=collaborator.id, start_time=inizio,
                    end_time=inizio + timedelta(hours=1), status=AppointmentStatus.confirmed)
    db.add(a)
    await db.flush()
    db.add(AppointmentService(appointment_id=a.id, service_id=service.id, price_snapshot=float(service.price)))
    await db.commit()

    await reminders._async_send_booking_confirmation(a.id)

    assert partite, "conferma non partita"
    assert service.name.encode() in partite[0][0][1].replace(b"\r\n ", b"")


async def test_servizi_non_caricati_non_fermano_la_conferma(db, client_account, collaborator, service):
    """Un appuntamento letto senza i servizi: l'evento si chiama solo «New
    Style Hair», ma la conferma parte."""
    cliente = (await db.execute(select(Client).where(Client.account_id == client_account.id))).scalar_one()
    inizio = datetime.now(timezone.utc) + timedelta(days=2)
    a = Appointment(client_id=cliente.id, collaborator_id=collaborator.id, start_time=inizio,
                    end_time=inizio + timedelta(hours=1), status=AppointmentStatus.confirmed)
    db.add(a)
    await db.flush()
    db.add(AppointmentService(appointment_id=a.id, service_id=service.id, price_snapshot=float(service.price)))
    id_appuntamento = a.id
    await db.commit()
    db.expire_all()
    letto = (await db.execute(select(Appointment).where(Appointment.id == id_appuntamento))).scalar_one()

    assert _campi(calendario.file_ics(letto))["SUMMARY"] == "New Style Hair"
    assert "text=New+Style+Hair&" in calendario.link_google(letto)


async def test_se_il_calendario_fallisce_la_conferma_parte_senza(monkeypatch):
    partite = []

    async def finta(to, subject, html_body, allegati=None):
        partite.append((html_body, allegati))

    def rotto(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(email_util, "send_email", finta)
    monkeypatch.setattr(calendario, "file_ics", rotto)
    await email_util.send_booking_confirmation_email(_appuntamento())
    corpo, allegati = partite[0]
    assert allegati is None and "confermata" in corpo and "Google Calendar" not in corpo


# ── Il file servito dal pulsante «Calendario del telefono» ────────


async def _confermato(db, client_account, collaborator, service, stato=AppointmentStatus.confirmed):
    cliente = (await db.execute(select(Client).where(Client.account_id == client_account.id))).scalar_one()
    inizio = istante(date.today() + timedelta(days=3), time(10, 0))
    a = Appointment(client_id=cliente.id, collaborator_id=collaborator.id, start_time=inizio,
                    end_time=inizio + timedelta(minutes=45), status=stato)
    db.add(a)
    await db.flush()
    db.add(AppointmentService(appointment_id=a.id, service_id=service.id, price_snapshot=float(service.price)))
    await db.commit()
    return a.id


def _percorso(i):
    return f"/api/public/calendario/{i}/appuntamento.ics"


class TestIlFileDalLink:
    async def test_con_la_firma_giusta(self, client, db, client_account, collaborator, service):
        i = await _confermato(db, client_account, collaborator, service)
        f = await client.get(_percorso(i), params={"f": calendario.firma(i)})
        assert f.status_code == 200
        assert f.headers["content-type"].startswith("text/calendar")
        assert 'filename="appuntamento.ics"' in f.headers["content-disposition"]
        assert b"BEGIN:VEVENT" in f.content and service.name.encode() in f.content.replace(b"\r\n ", b"")
        assert b"Giulia" not in f.content, "niente nomi di persone"

    def test_il_link_della_mail_punta_qui(self, monkeypatch):
        monkeypatch.setattr(calendario.settings, "API_URL", "https://api.esempio.it/")
        a = SimpleNamespace(id=7)
        assert calendario.link_ics(a) == f"https://api.esempio.it{_percorso(7)}?f={calendario.firma(7)}"

    async def test_senza_firma_o_con_quella_di_un_altro(self, client, db, client_account, collaborator, service):
        i = await _confermato(db, client_account, collaborator, service)
        for f in (None, "", "0" * 32, calendario.firma(i + 1)):
            params = {} if f is None else {"f": f}
            assert (await client.get(_percorso(i), params=params)).status_code == 404

    async def test_un_id_che_non_esiste_risponde_come_una_firma_sbagliata(self, client):
        r = await client.get(_percorso(999999), params={"f": calendario.firma(999999)})
        assert r.status_code == 404

    async def test_annullato(self, client, db, client_account, collaborator, service):
        i = await _confermato(db, client_account, collaborator, service, AppointmentStatus.cancelled)
        r = await client.get(_percorso(i), params={"f": calendario.firma(i)})
        assert r.status_code == 410
        assert "annullato" in r.json()["detail"]

    def test_la_firma_dipende_dalla_chiave(self, monkeypatch):
        prima = calendario.firma(5)
        monkeypatch.setattr(calendario.settings, "SECRET_KEY", "un-altra-chiave-del-tutto-diversa-123")
        assert calendario.firma(5) != prima
