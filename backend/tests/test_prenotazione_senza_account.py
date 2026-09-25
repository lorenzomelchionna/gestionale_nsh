"""Prenotare dal portale senza account: nome, cognome, numero e codice WhatsApp.

Il codice è l'unico controllo su un endpoint che chiunque può chiamare, quindi
la maggior parte di questi test dice cosa deve **rifiutare**: un codice
sbagliato, riusato, scaduto, esaurito; troppi codici allo stesso numero. Poi
dove finisce la prenotazione — la scheda giusta, e non quella di chi ha solo
lo stesso numero.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.models.appointment import Appointment, AppointmentOrigin, AppointmentStatus
from app.models.client import Client
from app.models.guest_phone_code import GuestPhoneCode
from app.services import guest_verification
from app.services.verification_codes import MAX_ATTEMPTS
from tests.conftest import giorno_lavorativo

pytestmark = pytest.mark.asyncio

CODE = "/api/public/guest/code"
BOOK = "/api/public/guest/appointments"
AVAILABILITY = "/api/public/availability"

PHONE = "+393471112233"
CHI = {"first_name": "Giulia", "last_name": "Esposito", "phone": "347 111 2233"}


@pytest.fixture
def whatsapp(monkeypatch):
    """I codici che sarebbero partiti su WhatsApp."""
    import app.api.public.guest as guest_api

    inviati: list[tuple[str, str]] = []

    async def finto_invio(to_phone, code):
        inviati.append((to_phone, code))

    monkeypatch.setattr(guest_api, "send_verification_code_whatsapp", finto_invio)
    return inviati


async def _orari(client, collaborator, service):
    giorno = giorno_lavorativo(date.today() + timedelta(days=2))
    r = await client.get(AVAILABILITY, params={
        "service_id": service.id, "collaborator_id": collaborator.id,
        "target_date": giorno.isoformat(),
    })
    assert r.status_code == 200, r.text
    return r.json()


async def _codice(client, whatsapp, **chi) -> str:
    r = await client.post(CODE, json={**CHI, **chi})
    assert r.status_code == 200, r.text
    assert r.json() == {"whatsapp_sent": True}
    return whatsapp[-1][1]


def _prenotazione(collaborator, service, inizio, code, **chi):
    return {
        **CHI, **chi, "code": code,
        "collaborator_id": collaborator.id,
        "start_time": inizio,
        "service_ids": [service.id],
    }


async def _via_il_tempo(db, phone=PHONE):
    """Come se l'ultimo codice fosse partito più di un minuto fa."""
    await db.execute(
        update(GuestPhoneCode)
        .where(GuestPhoneCode.phone == phone)
        .values(last_sent_at=datetime.now(timezone.utc) - timedelta(minutes=2))
    )
    await db.commit()


class TestCodice:
    async def test_arriva_al_numero_normalizzato(self, client, booking_config, whatsapp):
        await _codice(client, whatsapp)
        assert whatsapp[-1][0] == PHONE

    async def test_non_si_salva_in_chiaro(self, client, db, booking_config, whatsapp):
        code = await _codice(client, whatsapp)
        riga = (await db.execute(
            select(GuestPhoneCode).where(GuestPhoneCode.phone == PHONE)
        )).scalar_one()
        assert riga.code_hash and code not in riga.code_hash

    async def test_un_secondo_codice_subito_dopo_viene_rifiutato(
        self, client, booking_config, whatsapp
    ):
        await _codice(client, whatsapp)
        r = await client.post(CODE, json=CHI)
        assert r.status_code == 429
        assert len(whatsapp) == 1

    async def test_tetto_giornaliero_per_numero(self, client, db, booking_config, whatsapp):
        for _ in range(guest_verification.MAX_SENDS_PER_WINDOW):
            await _codice(client, whatsapp)
            await _via_il_tempo(db)
        r = await client.post(CODE, json=CHI)
        assert r.status_code == 429
        assert "domani" in r.json()["detail"]
        assert len(whatsapp) == guest_verification.MAX_SENDS_PER_WINDOW

    async def test_prenotazioni_chiuse_niente_codice(self, client, db, booking_config, whatsapp):
        booking_config.is_enabled = False
        await db.commit()
        r = await client.post(CODE, json=CHI)
        assert r.status_code == 403
        assert whatsapp == []

    async def test_invio_fallito_lo_dice(self, client, booking_config, monkeypatch):
        import app.api.public.guest as guest_api

        async def rotto(to_phone, code):
            raise RuntimeError("Twilio giù")

        monkeypatch.setattr(guest_api, "send_verification_code_whatsapp", rotto)
        r = await client.post(CODE, json=CHI)
        assert r.status_code == 200
        assert r.json() == {"whatsapp_sent": False}

    async def test_numero_non_valido(self, client, booking_config, whatsapp):
        r = await client.post(CODE, json={**CHI, "phone": "12"})
        assert r.status_code == 422
        assert whatsapp == []


class TestPrenotazione:
    async def test_crea_scheda_e_richiesta_in_attesa(
        self, client, db, booking_config, collaborator, service, whatsapp
    ):
        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)

        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "pending"

        scheda = (await db.execute(select(Client).where(Client.phone == PHONE))).scalar_one()
        assert (scheda.first_name, scheda.last_name) == ("Giulia", "Esposito")
        assert scheda.account_id is None and scheda.email is None

        appt = (await db.execute(
            select(Appointment).where(Appointment.client_id == scheda.id)
        )).scalar_one()
        assert appt.status == AppointmentStatus.pending
        assert appt.origin == AppointmentOrigin.online

    async def test_codice_sbagliato_rifiutato_e_contato(
        self, client, db, booking_config, collaborator, service, whatsapp
    ):
        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        sbagliato = "000000" if code != "000000" else "111111"

        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], sbagliato))
        assert r.status_code == 400
        assert f"Tentativi rimasti: {MAX_ATTEMPTS - 1}" in r.json()["detail"]

        # Il tentativo resta contato anche se la richiesta è fallita.
        riga = (await db.execute(
            select(GuestPhoneCode).where(GuestPhoneCode.phone == PHONE)
        )).scalar_one()
        await db.refresh(riga)
        assert riga.attempts == 1
        assert (await db.execute(select(Appointment))).first() is None

    async def test_tentativi_esauriti(self, client, booking_config, collaborator, service, whatsapp):
        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        sbagliato = "000000" if code != "000000" else "111111"
        for _ in range(MAX_ATTEMPTS):
            await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], sbagliato))

        # Anche quello giusto, ormai, non passa.
        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 400
        assert "Troppi tentativi" in r.json()["detail"]

    async def test_un_codice_vale_una_prenotazione(
        self, client, booking_config, collaborator, service, whatsapp
    ):
        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 201, r.text

        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[-1], code))
        assert r.status_code == 400

    async def test_codice_scaduto(self, client, db, booking_config, collaborator, service, whatsapp):
        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        await db.execute(
            update(GuestPhoneCode)
            .where(GuestPhoneCode.phone == PHONE)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await db.commit()
        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 400
        assert "scaduto" in r.json()["detail"]

    async def test_il_codice_e_del_numero(self, client, booking_config, collaborator, service, whatsapp):
        """Il codice arrivato a un numero non prenota a nome di un altro."""
        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        r = await client.post(BOOK, json=_prenotazione(
            collaborator, service, orari[0], code, phone="+393479998877",
        ))
        assert r.status_code == 400

    async def test_orario_occupato_non_brucia_il_codice(
        self, client, booking_config, collaborator, service, whatsapp
    ):
        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        # Un orario che non esiste nella giornata: 409 prima di guardare il codice.
        fuori = datetime.fromisoformat(orari[0]).replace(hour=3).isoformat()
        r = await client.post(BOOK, json=_prenotazione(collaborator, service, fuori, code))
        assert r.status_code == 409

        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 201, r.text

    async def test_troppe_in_attesa_non_brucia_il_codice(
        self, client, db, booking_config, collaborator, service, whatsapp
    ):
        from app.api.public.booking import MAX_PENDING_PER_CLIENT

        orari = await _orari(client, collaborator, service)
        # Ogni servizio dura un'ora: orari a due slot di distanza non si toccano.
        liberi = orari[::2]
        for inizio in liberi[:MAX_PENDING_PER_CLIENT]:
            code = await _codice(client, whatsapp)
            await _via_il_tempo(db)
            r = await client.post(BOOK, json=_prenotazione(collaborator, service, inizio, code))
            assert r.status_code == 201, r.text

        code = await _codice(client, whatsapp)
        r = await client.post(BOOK, json=_prenotazione(
            collaborator, service, liberi[MAX_PENDING_PER_CLIENT], code,
        ))
        assert r.status_code == 429

        # Rifiutata per un motivo che col codice non c'entra: il codice resta buono.
        riga = (await db.execute(
            select(GuestPhoneCode).where(GuestPhoneCode.phone == PHONE)
        )).scalar_one()
        await db.refresh(riga)
        assert riga.code_hash is not None


class TestSchedaGiusta:
    async def test_riusa_la_scheda_del_salone_con_nome_scritto_diverso(
        self, client, db, booking_config, collaborator, service, whatsapp
    ):
        salone = Client(first_name="GIULIA ", last_name="Espòsito", phone=PHONE, notes="allergica")
        db.add(salone)
        await db.commit()

        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 201, r.text

        schede = (await db.execute(select(Client).where(Client.phone == PHONE))).scalars().all()
        assert [s.id for s in schede] == [salone.id]

    async def test_stesso_numero_altro_nome_scheda_nuova(
        self, client, db, booking_config, collaborator, service, whatsapp
    ):
        """Madre e figlia col fisso di casa: la prenotazione della figlia non
        finisce nello storico della madre."""
        madre = Client(first_name="Anna", last_name="Esposito", phone=PHONE)
        db.add(madre)
        await db.commit()

        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 201, r.text

        appt = (await db.execute(select(Appointment))).scalar_one()
        assert appt.client_id != madre.id

    async def test_preferisce_la_scheda_con_account(
        self, client, db, booking_config, collaborator, service, whatsapp
    ):
        from app.models.client import ClientAccount

        # Quella senza account è la più vecchia: se vincesse l'età, vincerebbe lei.
        db.add(Client(first_name="Giulia", last_name="Esposito", phone=PHONE))
        await db.flush()
        account = ClientAccount(
            email="giulia@nsh-test.it", password_hash="x",
            email_verified=True, phone_verified=True,
        )
        db.add(account)
        await db.flush()
        registrata = Client(
            first_name="Giulia", last_name="Esposito", phone=PHONE, account_id=account.id,
        )
        db.add(registrata)
        await db.commit()

        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 201, r.text

        appt = (await db.execute(select(Appointment))).scalar_one()
        assert appt.client_id == registrata.id

    async def test_scheda_disattivata_non_si_riusa(
        self, client, db, booking_config, collaborator, service, whatsapp
    ):
        tolta = Client(first_name="Giulia", last_name="Esposito", phone=PHONE, is_active=False)
        db.add(tolta)
        await db.commit()

        orari = await _orari(client, collaborator, service)
        code = await _codice(client, whatsapp)
        r = await client.post(BOOK, json=_prenotazione(collaborator, service, orari[0], code))
        assert r.status_code == 201, r.text

        appt = (await db.execute(select(Appointment))).scalar_one()
        assert appt.client_id != tolta.id
