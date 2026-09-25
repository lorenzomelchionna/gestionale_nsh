"""Chi si registra ritrova le schede senza account con lo stesso numero e nome.

Le schede senza email — segnate dal salone, o nate da una prenotazione senza
account — non le trova il collegamento per indirizzo. Le trova questo, a una
condizione che è tutto il punto: il numero dev'essere **dimostrato** col
codice WhatsApp. Prima di quel codice, collegare per numero voleva dire
consegnare lo storico di una cliente a chiunque conoscesse il suo cellulare.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentStatus
from app.models.client import Client, ClientAccount
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

REGISTER = "/api/public/auth/register"
VERIFY = "/api/public/auth/verify-email"
VERIFY_PHONE = "/api/public/auth/verify-phone"
MY_APPOINTMENTS = "/api/public/appointments"

EMAIL = "maria.rossi@nsh-test.it"
PHONE = "+393401234567"


@pytest.fixture
def codici(monkeypatch):
    """Email e WhatsApp: i codici che sarebbero partiti, per canale."""
    import app.api.public.auth as auth_api

    inviati = {"email": [], "whatsapp": []}

    async def finta_email(to_email, first_name, code, ttl_minutes):
        inviati["email"].append(code)

    async def finto_whatsapp(to_phone, code):
        inviati["whatsapp"].append((to_phone, code))

    monkeypatch.setattr(auth_api, "send_verification_code_email", finta_email)
    monkeypatch.setattr(auth_api, "send_verification_code_whatsapp", finto_whatsapp)
    return inviati


def _registrazione(**campi):
    base = {
        "first_name": "Maria",
        "last_name": "Rossi",
        "phone": PHONE,
        "email": EMAIL,
        "password": "una-password-lunga-2026",
        "birth_date": "1990-04-12",
    }
    base.update(campi)
    return base


async def _registra_fino_al_telefono(client, codici, **campi) -> None:
    """Registrazione ed email confermata: manca solo il codice WhatsApp."""
    r = await client.post(REGISTER, json=_registrazione(**campi))
    assert r.status_code == 201, r.text
    r = await client.post(VERIFY, json={"email": EMAIL, "code": codici["email"][-1]})
    assert r.status_code == 200, r.text
    assert r.json()["phone_verification_required"] is True


async def _conferma_telefono(client, codici) -> dict:
    r = await client.post(VERIFY_PHONE, json={"email": EMAIL, "code": codici["whatsapp"][-1][1]})
    assert r.status_code == 200, r.text
    return r.json()


async def _scheda_del_salone(db, collaborator, service, **campi) -> Client:
    """Una cliente segnata dal salone con nome, cognome e telefono, e un appuntamento."""
    scheda = Client(**{"first_name": "Maria", "last_name": "Rossi", "phone": PHONE, **campi})
    db.add(scheda)
    await db.flush()
    inizio = datetime.now(timezone.utc) + timedelta(days=3)
    db.add(Appointment(
        client_id=scheda.id,
        collaborator_id=collaborator.id,
        start_time=inizio,
        end_time=inizio + timedelta(hours=1),
        status=AppointmentStatus.confirmed,
    ))
    await db.commit()
    return scheda


async def _account(db) -> ClientAccount:
    return (await db.execute(
        select(ClientAccount).where(ClientAccount.email == EMAIL)
    )).scalar_one()


class TestCollega:
    async def test_ritrova_gli_appuntamenti_segnati_dal_salone(
        self, client, db, booking_config, collaborator, service, codici
    ):
        salone = await _scheda_del_salone(db, collaborator, service, notes="Tinta 6.1")
        await _registra_fino_al_telefono(client, codici)
        token = await _conferma_telefono(client, codici)

        r = await client.get(MY_APPOINTMENTS, headers=auth(token))
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1

        # Sopravvive la scheda del salone, con le sue note, e prende quello
        # che la registrazione sapeva in più.
        await db.refresh(salone)
        account = await _account(db)
        assert salone.account_id == account.id
        assert salone.is_active
        assert salone.notes == "Tinta 6.1"
        assert salone.email == EMAIL
        assert salone.birth_date is not None

        attive = (await db.execute(
            select(Client).where(Client.account_id == account.id)
        )).scalars().all()
        assert [c.id for c in attive] == [salone.id]

    async def test_nome_scritto_diverso_collega_lo_stesso(
        self, client, db, booking_config, collaborator, service, codici
    ):
        salone = await _scheda_del_salone(db, collaborator, service, first_name="MARIA", last_name="Rossi ")
        await _registra_fino_al_telefono(client, codici, first_name="maria", last_name="rossi")
        await _conferma_telefono(client, codici)

        await db.refresh(salone)
        assert salone.account_id == (await _account(db)).id

    async def test_ritrova_la_prenotazione_fatta_senza_account(
        self, client, db, booking_config, collaborator, service, codici, monkeypatch
    ):
        import app.api.public.guest as guest_api

        codici_ospite: list[str] = []

        async def finto(to_phone, code):
            codici_ospite.append(code)

        monkeypatch.setattr(guest_api, "send_verification_code_whatsapp", finto)

        from datetime import date
        from tests.conftest import giorno_lavorativo
        giorno = giorno_lavorativo(date.today() + timedelta(days=2))
        orari = (await client.get("/api/public/availability", params={
            "service_id": service.id, "collaborator_id": collaborator.id,
            "target_date": giorno.isoformat(),
        })).json()

        chi = {"first_name": "Maria", "last_name": "Rossi", "phone": "340 123 4567"}
        assert (await client.post("/api/public/guest/code", json=chi)).status_code == 200
        r = await client.post("/api/public/guest/appointments", json={
            **chi, "code": codici_ospite[-1], "collaborator_id": collaborator.id,
            "start_time": orari[0], "service_ids": [service.id],
        })
        assert r.status_code == 201, r.text

        await _registra_fino_al_telefono(client, codici)
        token = await _conferma_telefono(client, codici)

        r = await client.get(MY_APPOINTMENTS, headers=auth(token))
        assert [a["status"] for a in r.json()] == ["pending"]


class TestNonCollega:
    async def test_senza_codice_whatsapp_non_collega(
        self, client, db, booking_config, collaborator, service, codici
    ):
        """Email confermata ma numero no: il numero è ancora solo digitato."""
        salone = await _scheda_del_salone(db, collaborator, service)
        await _registra_fino_al_telefono(client, codici)

        await db.refresh(salone)
        assert salone.account_id is None

    async def test_codice_whatsapp_sbagliato_non_collega(
        self, client, db, booking_config, collaborator, service, codici
    ):
        salone = await _scheda_del_salone(db, collaborator, service)
        await _registra_fino_al_telefono(client, codici)
        giusto = codici["whatsapp"][-1][1]
        r = await client.post(VERIFY_PHONE, json={
            "email": EMAIL, "code": "000000" if giusto != "000000" else "111111",
        })
        assert r.status_code == 400

        await db.refresh(salone)
        assert salone.account_id is None

    async def test_altro_nome_stesso_numero_non_collega(
        self, client, db, booking_config, collaborator, service, codici
    ):
        """Madre e figlia col fisso di casa: la figlia non eredita lo storico."""
        madre = await _scheda_del_salone(db, collaborator, service, first_name="Anna")
        await _registra_fino_al_telefono(client, codici)
        token = await _conferma_telefono(client, codici)

        await db.refresh(madre)
        assert madre.account_id is None
        r = await client.get(MY_APPOINTMENTS, headers=auth(token))
        assert r.json() == []

    async def test_scheda_con_account_non_si_tocca(
        self, client, db, booking_config, collaborator, service, codici
    ):
        altro = ClientAccount(
            email="altra@nsh-test.it", password_hash="x",
            email_verified=True, phone_verified=True,
        )
        db.add(altro)
        await db.flush()
        presa = await _scheda_del_salone(db, collaborator, service, account_id=altro.id)

        await _registra_fino_al_telefono(client, codici)
        await _conferma_telefono(client, codici)

        await db.refresh(presa)
        assert presa.account_id == altro.id

    async def test_scheda_disattivata_non_si_collega(
        self, client, db, booking_config, collaborator, service, codici
    ):
        tolta = await _scheda_del_salone(db, collaborator, service, is_active=False)
        await _registra_fino_al_telefono(client, codici)
        await _conferma_telefono(client, codici)

        await db.refresh(tolta)
        assert tolta.account_id is None


class TestPiuSchede:
    async def test_due_schede_del_salone_finiscono_nella_piu_vecchia(
        self, client, db, booking_config, collaborator, service, codici
    ):
        prima = await _scheda_del_salone(db, collaborator, service)
        seconda = await _scheda_del_salone(db, collaborator, service)
        await _registra_fino_al_telefono(client, codici)
        token = await _conferma_telefono(client, codici)

        await db.refresh(prima)
        await db.refresh(seconda)
        assert prima.account_id == (await _account(db)).id
        assert not seconda.is_active

        r = await client.get(MY_APPOINTMENTS, headers=auth(token))
        assert len(r.json()) == 2
