"""Modificare o annullare dal portale un appuntamento confermato.

Richiesta del 2026-10-13. Decisioni di Lorenzo:

- la cliente può cambiare **tutto** — servizi, collaboratore, giorno, ora;
- è una **richiesta**: l'appuntamento confermato resta valido finché il salone
  non accetta, e se rifiuta la cliente tiene il posto che aveva;
- modifica e annullamento solo entro il **preavviso** delle impostazioni
  (`min_cancel_hours`, lo stesso che valeva già per annullare);
- il salone viene **avvisato** di tutto: richieste di modifica, annullamenti,
  richieste ritirate. Prima l'annullamento dal portale non avvisava nessuno.

La richiesta è un appuntamento «in attesa» con `replaces_appointment_id`;
questi test fissano i due capi del filo: conferma → l'originale si annulla;
originale annullato → la richiesta si chiude.
"""
from datetime import datetime, time, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

import app.api.public.booking as booking_api
from app.models.appointment import (
    Appointment, AppointmentOrigin, AppointmentService, AppointmentStatus,
)
from app.models.client import Client
from app.models.collaborator import Collaborator, CollaboratorSchedule, CollaboratorService
from app.models.service import Service
from app.utils.tempo import istante
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
def avvisi(monkeypatch):
    """Gli avvisi allo staff che le rotte accodano, invece di Celery."""
    registro = []
    monkeypatch.setattr(booking_api, "_trigger_change_alert", lambda i: registro.append(("modifica", i)))
    monkeypatch.setattr(
        booking_api, "_trigger_cancellation_alert", lambda i, tipo: registro.append(("annullato", i, tipo)),
    )
    monkeypatch.setattr(booking_api, "_trigger_new_booking_alert", lambda i: registro.append(("nuova", i)))
    return registro


async def _cliente(db, client_account) -> Client:
    return (await db.execute(
        select(Client).where(Client.account_id == client_account.id)
    )).scalar_one()


def _giorno(giorni=5):
    return giorno_lavorativo(datetime.now(timezone.utc) + timedelta(days=giorni)).date()


async def _appuntamento(db, client, collaborator, service, giorno, ora=time(10, 0),
                        stato=AppointmentStatus.confirmed, **extra) -> Appointment:
    inizio = istante(giorno, ora)
    a = Appointment(
        client_id=client.id, collaborator_id=collaborator.id,
        start_time=inizio, end_time=inizio + timedelta(hours=1),
        status=stato, origin=AppointmentOrigin.online, **extra,
    )
    db.add(a)
    await db.flush()
    db.add(AppointmentService(appointment_id=a.id, service_id=service.id, price_snapshot=30.0))
    await db.commit()
    return a


@pytest_asyncio.fixture
async def confermato(db, booking_config, client_account, collaborator, service):
    return await _appuntamento(db, await _cliente(db, client_account), collaborator, service, _giorno())


@pytest_asyncio.fixture
async def altro_collab(db, service) -> Collaborator:
    c = Collaborator(first_name="Marco", last_name="Test", email="marco@nsh-test.it",
                     visible_online=True, is_active=True)
    db.add(c)
    await db.flush()
    for day in range(6):
        db.add(CollaboratorSchedule(collaborator_id=c.id, day_of_week=day,
                                    start_time=time(9, 0), end_time=time(19, 0), is_working=True))
    db.add(CollaboratorSchedule(collaborator_id=c.id, day_of_week=6, is_working=False))
    db.add(CollaboratorService(collaborator_id=c.id, service_id=service.id))
    await db.commit()
    return c


@pytest_asyncio.fixture
async def piega(db, collaborator, altro_collab) -> Service:
    s = Service(name="Piega", price=20, duration_slots=1, category="Piega",
                bookable_online=True, is_active=True)
    db.add(s)
    await db.flush()
    for c in (collaborator, altro_collab):
        db.add(CollaboratorService(collaborator_id=c.id, service_id=s.id))
    await db.commit()
    return s


def _url(a, azione="change"):
    return f"/api/public/appointments/{a.id}/{azione}"


def _corpo(collab, giorno, ora, servizi):
    return {
        "client_id": 0, "collaborator_id": collab.id,
        "start_time": istante(giorno, ora).isoformat(),
        "end_time": (istante(giorno, ora) + timedelta(hours=1)).isoformat(),
        "service_ids": [s.id for s in servizi],
    }


async def _stato(db, a):
    return (await db.execute(select(Appointment.status).where(Appointment.id == a.id))).scalar_one()


async def _richieste(db, a):
    return (await db.execute(
        select(Appointment).where(Appointment.replaces_appointment_id == a.id)
    )).scalars().all()


class TestRichiestaDiModifica:
    async def test_tutto_cambia_e_il_vecchio_resta(
        self, client, db, client_tokens, confermato, collaborator, altro_collab, service, piega, avvisi,
    ):
        """Servizi, collaboratore, giorno e ora: tutto insieme."""
        giorno = _giorno(7)
        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(altro_collab, giorno, time(15, 0), [service, piega]))
        assert r.status_code == 201, r.text
        nuova = r.json()
        assert nuova["status"] == "pending"
        assert nuova["replaces_appointment_id"] == confermato.id
        assert nuova["collaborator_id"] == altro_collab.id

        assert await _stato(db, confermato) == AppointmentStatus.confirmed
        assert avvisi == [("modifica", nuova["id"])], "al salone va l'avviso di modifica, non di prenotazione nuova"

    async def test_si_puo_slittare_sul_proprio_orario(
        self, client, db, client_tokens, confermato, collaborator, service, avvisi,
    ):
        """10:00–11:00 → 10:30 con la stessa persona: si sovrappone solo a sé
        stesso, e il proprio appuntamento non deve fare da ostacolo."""
        giorno = confermato.start_time.astimezone(timezone.utc)
        from app.utils.tempo import ora_salone
        giorno = ora_salone(confermato.start_time).date()
        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(collaborator, giorno, time(10, 30), [service]))
        assert r.status_code == 201, r.text

    async def test_cambiare_solo_i_servizi(
        self, client, db, client_tokens, confermato, collaborator, service, piega, avvisi,
    ):
        """Stessa ora, stessa persona, un servizio in più: è una modifica vera,
        non «uguale a prima»."""
        from app.utils.tempo import ora_salone
        giorno = ora_salone(confermato.start_time).date()
        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(collaborator, giorno, time(10, 0), [service, piega]))
        assert r.status_code == 201, r.text

    async def test_un_orario_preso_da_altri_no(
        self, client, db, client_tokens, confermato, collaborator, service, other_client, avvisi,
    ):
        giorno = _giorno(8)
        await _appuntamento(db, other_client, collaborator, service, giorno, time(11, 0))
        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(collaborator, giorno, time(11, 0), [service]))
        assert r.status_code == 409
        assert await _richieste(db, confermato) == []

    async def test_solo_appuntamenti_confermati(
        self, client, db, client_tokens, booking_config, client_account, collaborator, service, avvisi,
    ):
        attesa = await _appuntamento(db, await _cliente(db, client_account), collaborator, service,
                                     _giorno(), stato=AppointmentStatus.pending)
        r = await client.post(_url(attesa), headers=auth(client_tokens),
                              json=_corpo(collaborator, _giorno(9), time(12, 0), [service]))
        assert r.status_code == 400

    async def test_dentro_il_preavviso_no(
        self, client, db, client_tokens, booking_config, client_account, collaborator, service, avvisi,
    ):
        """Domani alle 10 con 24h di preavviso: troppo tardi, si telefona."""
        domani = await _appuntamento(
            db, await _cliente(db, client_account), collaborator, service,
            (datetime.now(timezone.utc) + timedelta(hours=20)).date(),
            ora=(datetime.now(timezone.utc) + timedelta(hours=20)).time().replace(second=0, microsecond=0),
        )
        r = await client.post(_url(domani), headers=auth(client_tokens),
                              json=_corpo(collaborator, _giorno(9), time(12, 0), [service]))
        assert r.status_code == 400
        assert "preavviso" in r.json()["detail"]

    async def test_una_sola_modifica_aperta(
        self, client, db, client_tokens, confermato, collaborator, service, avvisi,
    ):
        prima = await client.post(_url(confermato), headers=auth(client_tokens),
                                  json=_corpo(collaborator, _giorno(9), time(12, 0), [service]))
        assert prima.status_code == 201
        seconda = await client.post(_url(confermato), headers=auth(client_tokens),
                                    json=_corpo(collaborator, _giorno(9), time(15, 0), [service]))
        assert seconda.status_code == 409

    async def test_uguale_a_prima_no(self, client, db, client_tokens, confermato, collaborator, service, avvisi):
        from app.utils.tempo import ora_salone
        giorno = ora_salone(confermato.start_time).date()
        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(collaborator, giorno, time(10, 0), [service]))
        assert r.status_code == 400

    async def test_l_appuntamento_di_un_altra_no(
        self, client, db, client_tokens, booking_config, other_client, collaborator, service, avvisi,
    ):
        altrui = await _appuntamento(db, other_client, collaborator, service, _giorno())
        r = await client.post(_url(altrui), headers=auth(client_tokens),
                              json=_corpo(collaborator, _giorno(9), time(12, 0), [service]))
        assert r.status_code == 404
        assert await _richieste(db, altrui) == []


class TestIlSaloneDecide:
    async def _chiedi(self, client, client_tokens, confermato, collaborator, service):
        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(collaborator, _giorno(9), time(12, 0), [service]))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    async def test_accetta_e_il_vecchio_si_annulla(
        self, client, db, client_tokens, admin_tokens, confermato, collaborator, service, avvisi,
    ):
        nuova = await self._chiedi(client, client_tokens, confermato, collaborator, service)
        r = await client.post(f"/api/admin/appointments/{nuova}/confirm", headers=auth(admin_tokens))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "confirmed"
        assert await _stato(db, confermato) == AppointmentStatus.cancelled

    async def test_rifiuta_e_il_vecchio_resta(
        self, client, db, client_tokens, admin_tokens, confermato, collaborator, service, avvisi,
    ):
        nuova = await self._chiedi(client, client_tokens, confermato, collaborator, service)
        r = await client.post(f"/api/admin/appointments/{nuova}/reject", headers=auth(admin_tokens),
                              json={"reason": "Quel giorno siamo pieni"})
        assert r.status_code == 200, r.text
        assert await _stato(db, confermato) == AppointmentStatus.confirmed

    async def test_propone_un_altro_orario_e_la_cliente_accetta(
        self, client, db, client_tokens, admin_tokens, confermato, collaborator, service, avvisi,
    ):
        nuova = await self._chiedi(client, client_tokens, confermato, collaborator, service)
        altra = istante(_giorno(10), time(16, 0))
        r = await client.post(f"/api/admin/appointments/{nuova}/reschedule", headers=auth(admin_tokens),
                              json={"alternative_time": altra.isoformat()})
        assert r.status_code == 200, r.text
        r = await client.post(f"/api/public/appointments/{nuova}/accept-alternative", headers=auth(client_tokens))
        assert r.status_code == 200, r.text
        assert await _stato(db, confermato) == AppointmentStatus.cancelled

    async def test_la_lista_in_attesa_mostra_il_prima(
        self, client, db, client_tokens, admin_tokens, confermato, collaborator, service, avvisi,
    ):
        nuova = await self._chiedi(client, client_tokens, confermato, collaborator, service)
        r = await client.get("/api/admin/appointments/pending", headers=auth(admin_tokens))
        [riga] = [x for x in r.json() if x["id"] == nuova]
        assert riga["replaces_appointment_id"] == confermato.id
        assert datetime.fromisoformat(riga["replaces_start_time"]) == confermato.start_time
        assert riga["replaces_collaborator_name"] == "Sofia Test"
        assert riga["replaces_service_names"] == ["Taglio test"]

    async def test_l_originale_annullato_dal_salone_chiude_la_modifica(
        self, client, db, client_tokens, admin_tokens, confermato, collaborator, service, avvisi,
    ):
        nuova = await self._chiedi(client, client_tokens, confermato, collaborator, service)
        r = await client.post(f"/api/admin/appointments/{confermato.id}/cancel", headers=auth(admin_tokens),
                              json={"reason": "Chiusura straordinaria"})
        assert r.status_code == 200, r.text
        stato = (await db.execute(select(Appointment.status).where(Appointment.id == nuova))).scalar_one()
        assert stato == AppointmentStatus.cancelled

    @pytest.mark.parametrize("come", ["reject", "delete"])
    async def test_l_originale_rifiutato_o_eliminato_chiude_la_modifica(
        self, client, db, client_tokens, admin_tokens, confermato, collaborator, service, avvisi, come,
    ):
        nuova = await self._chiedi(client, client_tokens, confermato, collaborator, service)
        if come == "reject":
            r = await client.post(f"/api/admin/appointments/{confermato.id}/reject",
                                  headers=auth(admin_tokens), json={"reason": "x"})
        else:
            r = await client.delete(f"/api/admin/appointments/{confermato.id}", headers=auth(admin_tokens))
        assert r.status_code in (200, 204), r.text
        stato = (await db.execute(select(Appointment.status).where(Appointment.id == nuova))).scalar_one()
        assert stato == AppointmentStatus.cancelled

    async def test_non_si_conferma_una_modifica_di_un_appuntamento_finito(
        self, client, db, client_tokens, admin_tokens, confermato, collaborator, service, avvisi,
    ):
        """Il caso che il filo non copre da solo: l'originale chiuso per
        un'altra strada (qui: completato) mentre la modifica aspetta."""
        nuova = await self._chiedi(client, client_tokens, confermato, collaborator, service)
        confermato.status = AppointmentStatus.completed
        await db.commit()
        r = await client.post(f"/api/admin/appointments/{nuova}/confirm", headers=auth(admin_tokens))
        assert r.status_code == 409
        stato = (await db.execute(select(Appointment.status).where(Appointment.id == nuova))).scalar_one()
        assert stato == AppointmentStatus.pending


class TestAnnullareAvvisaIlSalone:
    async def test_annulla_un_confermato(self, client, db, client_tokens, confermato, avvisi):
        r = await client.post(_url(confermato, "cancel"), headers=auth(client_tokens))
        assert r.status_code == 200, r.text
        assert await _stato(db, confermato) == AppointmentStatus.cancelled
        assert avvisi == [("annullato", confermato.id, "confermato")]

    async def test_annullare_porta_via_la_modifica_aperta(
        self, client, db, client_tokens, confermato, collaborator, service, avvisi,
    ):
        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(collaborator, _giorno(9), time(12, 0), [service]))
        nuova = r.json()["id"]
        r = await client.post(_url(confermato, "cancel"), headers=auth(client_tokens))
        assert r.status_code == 200, r.text
        stato = (await db.execute(select(Appointment.status).where(Appointment.id == nuova))).scalar_one()
        assert stato == AppointmentStatus.cancelled

    async def test_ritirare_la_modifica_lascia_il_vecchio(
        self, client, db, client_tokens, confermato, collaborator, service, avvisi,
    ):
        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(collaborator, _giorno(9), time(12, 0), [service]))
        nuova = r.json()["id"]
        avvisi.clear()
        r = await client.post(f"/api/public/appointments/{nuova}/cancel", headers=auth(client_tokens))
        assert r.status_code == 200, r.text
        assert await _stato(db, confermato) == AppointmentStatus.confirmed
        assert avvisi == [("annullato", nuova, "modifica")]

    async def test_ritirare_una_richiesta_nuova(
        self, client, db, client_tokens, booking_config, client_account, collaborator, service, avvisi,
    ):
        attesa = await _appuntamento(db, await _cliente(db, client_account), collaborator, service,
                                     _giorno(), stato=AppointmentStatus.pending)
        r = await client.post(_url(attesa, "cancel"), headers=auth(client_tokens))
        assert r.status_code == 200, r.text
        assert avvisi == [("annullato", attesa.id, "richiesta")]

    async def test_dentro_il_preavviso_nessun_annullamento_e_nessun_avviso(
        self, client, db, client_tokens, booking_config, client_account, collaborator, service, avvisi,
    ):
        fra_poco = datetime.now(timezone.utc) + timedelta(hours=20)
        a = await _appuntamento(db, await _cliente(db, client_account), collaborator, service,
                                fra_poco.date(), ora=fra_poco.time().replace(second=0, microsecond=0))
        r = await client.post(_url(a, "cancel"), headers=auth(client_tokens))
        assert r.status_code == 400
        assert await _stato(db, a) == AppointmentStatus.confirmed
        assert avvisi == []


class TestOrariLiberiMentreSiSposta:
    AV = "/api/public/availability"

    async def _orari(self, client, confermato, collaborator, service, headers=None, sostituisce=True):
        from app.utils.tempo import ora_salone
        params = {"service_ids": service.id, "collaborator_id": collaborator.id,
                  "target_date": ora_salone(confermato.start_time).date().isoformat()}
        if sostituisce:
            params["sostituisce"] = confermato.id
        return await client.get(self.AV, params=params, headers=headers or {})

    async def test_il_proprio_orario_torna_libero(
        self, client, client_tokens, confermato, collaborator, service,
    ):
        senza = await self._orari(client, confermato, collaborator, service, sostituisce=False)
        assert confermato.start_time.isoformat() not in [datetime.fromisoformat(x).isoformat() for x in senza.json()]
        con = await self._orari(client, confermato, collaborator, service, headers=auth(client_tokens))
        assert con.status_code == 200, con.text
        assert confermato.start_time in [datetime.fromisoformat(x) for x in con.json()]

    async def test_senza_sessione_401(self, client, confermato, collaborator, service):
        r = await self._orari(client, confermato, collaborator, service)
        assert r.status_code == 401

    async def test_l_appuntamento_di_un_altra_no(
        self, client, db, client_tokens, booking_config, other_client, collaborator, service,
    ):
        altrui = await _appuntamento(db, other_client, collaborator, service, _giorno())
        r = await self._orari(client, altrui, collaborator, service, headers=auth(client_tokens))
        assert r.status_code == 404

    async def test_senza_sostituisce_resta_pubblica(self, client, confermato, collaborator, service):
        r = await self._orari(client, confermato, collaborator, service, sostituisce=False)
        assert r.status_code == 200


class TestLElencoDelPortale:
    async def test_scadenza_e_servizi(self, client, client_tokens, confermato, service):
        r = await client.get("/api/public/appointments", headers=auth(client_tokens))
        [a] = r.json()
        assert a["service_ids"] == [service.id]
        assert datetime.fromisoformat(a["change_deadline"]) == confermato.start_time - timedelta(hours=24)


class TestLeEmailAlloStaff:
    async def test_modifica_a_entrambi_i_collaboratori(
        self, client, db, client_tokens, admin_user, confermato, collaborator, altro_collab, service, avvisi,
        monkeypatch,
    ):
        from app.models.appointment import appointment_detail_loads
        from app.utils import email as email_util
        from app.utils.notifications import notify_staff_change_request

        r = await client.post(_url(confermato), headers=auth(client_tokens),
                              json=_corpo(altro_collab, _giorno(9), time(12, 0), [service]))
        nuova_id = r.json()["id"]
        inviate = []

        async def finta(to, subject, body):
            inviate.append((to, subject, body))
        monkeypatch.setattr(email_util, "send_email", finta)

        async def carica(i):
            return (await db.execute(
                select(Appointment).options(*appointment_detail_loads()).where(Appointment.id == i)
            )).scalar_one()
        db.expire_all()
        nuova, vecchia = await carica(nuova_id), await carica(confermato.id)
        destinatari = await notify_staff_change_request(db, nuova, vecchia)

        assert set(destinatari) == {admin_user.email, "sofia@nsh-test.it", "marco@nsh-test.it"}
        _, oggetto, corpo = inviate[0]
        assert oggetto.startswith("Richiesta di modifica")
        assert "Prima" in corpo and "Dopo" in corpo
        assert "Sofia Test" in corpo and "Marco Test" in corpo

    async def test_annullamento_con_nome_escapato(
        self, db, admin_user, booking_config, client_account, collaborator, service, monkeypatch,
    ):
        from app.models.appointment import appointment_detail_loads
        from app.utils import email as email_util
        from app.utils.notifications import notify_staff_client_cancellation

        cliente = await _cliente(db, client_account)
        cliente.first_name = "<b>Giulia</b>"
        await db.commit()
        a = await _appuntamento(db, cliente, collaborator, service, _giorno())
        inviate = []

        async def finta(to, subject, body):
            inviate.append(body)
        monkeypatch.setattr(email_util, "send_email", finta)
        a = (await db.execute(
            select(Appointment).options(*appointment_detail_loads()).where(Appointment.id == a.id)
        )).scalar_one()
        await notify_staff_client_cancellation(db, a, "confermato")
        assert inviate and "<b>Giulia</b>" not in inviate[0]
        assert "annullato un appuntamento confermato" in inviate[0]
