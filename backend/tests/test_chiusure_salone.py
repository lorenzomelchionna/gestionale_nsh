"""Chiusure del salone per data: ferie, ponti, festività in cui non apre.

Prima c'erano solo i giorni chiusi della settimana, e il portale li
rispettava solo perché i collaboratori quel giorno non lavorano. Una data
singola — Natale, Santo Stefano di sabato, le ferie d'agosto — si poteva
chiudere solo inserendo un'assenza a ogni collaboratore, e il 26 dicembre
2026 cade di sabato. Serviva un modo di chiudere il salone in un punto solo
(2026-11-20). Quanto avanti si prenota resta «Anticipo massimo» nelle
impostazioni.

Quello che i test tengono fermo:
  - un giorno chiuso non ha orari su **nessuna** strada del portale —
    calendario del mese, elenco degli orari, prenotazione — e nemmeno fra i
    suggerimenti del gestionale;
  - gli estremi sono compresi, il giorno dopo si riapre;
  - togliere le chiusure riapre;
  - una chiusura con la fine prima dell'inizio non si salva.

Nessuna festività è chiusa di default: il salone non è detto che chiuda
(scelta di Lorenzo, 2026-11-20).
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest

from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio

SETTINGS = "/api/admin/settings/booking"
CALENDAR = "/api/public/availability/calendar"


def _giorno(n: int) -> date:
    """Un giorno lavorativo fra `n` giorni (il collaboratore lavora lun–sab)."""
    return giorno_lavorativo(date.today() + timedelta(days=n))


async def _chiudi(client, admin_tokens, chiusure):
    r = await client.put(
        SETTINGS, headers=auth(admin_tokens), json={"closed_dates": chiusure}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _orari(client, collaborator, service, giorno):
    r = await client.get("/api/public/availability", params={
        "service_id": service.id, "collaborator_id": collaborator.id,
        "target_date": giorno.isoformat(),
    })
    assert r.status_code == 200, r.text
    return r.json()


class TestImpostazioni:
    async def test_si_salvano_e_si_rileggono(self, client, admin_tokens, booking_config):
        salvate = await _chiudi(client, admin_tokens, [
            {"dal": "2026-12-25", "al": "2026-12-26", "nota": "Natale"},
            {"dal": "2027-08-10", "al": "2027-08-24", "nota": "Ferie"},
        ])
        assert salvate["closed_dates"] == [
            {"dal": "2026-12-25", "al": "2026-12-26", "nota": "Natale"},
            {"dal": "2027-08-10", "al": "2027-08-24", "nota": "Ferie"},
        ]
        letto = await client.get(SETTINGS, headers=auth(admin_tokens))
        assert letto.json()["closed_dates"] == salvate["closed_dates"]

    async def test_di_default_non_ce_niente(self, client, admin_tokens, booking_config):
        letto = await client.get(SETTINGS, headers=auth(admin_tokens))
        assert letto.json()["closed_dates"] == []

    async def test_un_salvataggio_senza_chiusure_non_le_tocca(
        self, client, admin_tokens, booking_config
    ):
        """La pagina manda solo i campi che cambia: cambiare l'anticipo
        minimo non deve cancellare le ferie."""
        await _chiudi(client, admin_tokens, [{"dal": "2026-12-25", "al": "2026-12-25"}])
        r = await client.put(SETTINGS, headers=auth(admin_tokens), json={"min_advance_hours": 3})
        assert r.json()["closed_dates"] == [{"dal": "2026-12-25", "al": "2026-12-25", "nota": ""}]

    async def test_fine_prima_dell_inizio_rifiutata(self, client, admin_tokens, booking_config):
        r = await client.put(SETTINGS, headers=auth(admin_tokens), json={
            "closed_dates": [{"dal": "2026-12-26", "al": "2026-12-25"}],
        })
        assert r.status_code == 422

    async def test_nota_troppo_lunga_rifiutata(self, client, admin_tokens, booking_config):
        r = await client.put(SETTINGS, headers=auth(admin_tokens), json={
            "closed_dates": [{"dal": "2026-12-25", "al": "2026-12-25", "nota": "x" * 81}],
        })
        assert r.status_code == 422

    async def test_il_collaboratore_non_puo(self, client, collab_tokens, booking_config):
        r = await client.put(SETTINGS, headers=auth(collab_tokens), json={
            "closed_dates": [{"dal": "2026-12-25", "al": "2026-12-25"}],
        })
        assert r.status_code == 403


class TestPortale:
    async def test_il_calendario_li_da_vuoti_estremi_compresi(
        self, client, admin_tokens, booking_config, collaborator, service
    ):
        inizio = _giorno(20)
        fine = giorno_lavorativo(inizio + timedelta(days=1))
        dopo = giorno_lavorativo(fine + timedelta(days=1))
        prima = inizio - timedelta(days=1)
        await _chiudi(client, admin_tokens, [
            {"dal": inizio.isoformat(), "al": fine.isoformat(), "nota": "Ferie"},
        ])
        r = await client.get(CALENDAR, params={
            "service_id": service.id, "collaborator_id": collaborator.id,
            "start_date": prima.isoformat(), "end_date": dopo.isoformat(),
        })
        assert r.status_code == 200, r.text
        slot = {d["date"]: d["slots"] for d in r.json()}
        assert slot[inizio.isoformat()] == 0
        assert slot[fine.isoformat()] == 0
        assert slot[dopo.isoformat()] > 0, "il giorno dopo la chiusura deve riaprire"

    async def test_l_elenco_orari_e_vuoto(
        self, client, admin_tokens, booking_config, collaborator, service
    ):
        giorno = _giorno(15)
        assert await _orari(client, collaborator, service, giorno), "prima della chiusura ci sono orari"
        await _chiudi(client, admin_tokens, [{"dal": giorno.isoformat(), "al": giorno.isoformat()}])
        assert await _orari(client, collaborator, service, giorno) == []

    async def test_non_si_prenota(
        self, client, admin_tokens, client_tokens, booking_config, collaborator, service
    ):
        giorno = _giorno(15)
        await _chiudi(client, admin_tokens, [{"dal": giorno.isoformat(), "al": giorno.isoformat()}])
        inizio = datetime.combine(giorno, time(10, 0), tzinfo=timezone.utc)
        r = await client.post("/api/public/appointments", headers=auth(client_tokens), json={
            "client_id": 0, "collaborator_id": collaborator.id,
            "start_time": inizio.isoformat(),
            "end_time": (inizio + timedelta(hours=1)).isoformat(),
            "service_ids": [service.id],
        })
        assert r.status_code == 409, r.text

    async def test_togliere_la_chiusura_riapre(
        self, client, admin_tokens, booking_config, collaborator, service
    ):
        giorno = _giorno(15)
        await _chiudi(client, admin_tokens, [{"dal": giorno.isoformat(), "al": giorno.isoformat()}])
        assert await _orari(client, collaborator, service, giorno) == []
        await _chiudi(client, admin_tokens, [])
        assert await _orari(client, collaborator, service, giorno)


class TestGestionale:
    async def test_niente_suggerimenti_nel_giorno_chiuso(
        self, client, admin_tokens, booking_config, collaborator
    ):
        giorno = _giorno(15)
        params = {"collaborator_id": collaborator.id, "target_date": giorno.isoformat(), "duration_slots": 2}
        prima = await client.get("/api/admin/availability", headers=auth(admin_tokens), params=params)
        assert prima.json(), "prima della chiusura ci sono orari"
        await _chiudi(client, admin_tokens, [{"dal": giorno.isoformat(), "al": giorno.isoformat()}])
        dopo = await client.get("/api/admin/availability", headers=auth(admin_tokens), params=params)
        assert dopo.status_code == 200
        assert dopo.json() == []
