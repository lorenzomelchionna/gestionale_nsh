"""
Tempo di posa: durante la posa il collaboratore è libero.

Richiesta di Flavia (2026-08-04). Su una tinta ci sono tre fasi: si applica
il colore, la cliente resta in posa, poi si lava e si asciuga. In mezzo il
collaboratore non fa niente per lei — e finora l'agenda lo considerava
occupato per tutte e tre, quindi due ore di colore toglievano due ore di
disponibilità anche se il lavoro vero era un'ora.

`duration_slots` resta la durata totale, quella che vede la cliente. I due
campi nuovi dicono come si spezza:

    [ slots_before_processing ][ processing_slots ][ il resto ]
         occupato                   LIBERO            occupato
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentService, AppointmentStatus
from app.models.collaborator import CollaboratorService
from app.models.service import Service
from app.services.availability import busy_slot_offsets, get_available_slots
from tests.conftest import auth


def _finto(duration, posa=0, prima=0):
    """Il minimo che `busy_slot_offsets` legge, senza toccare il database."""
    return Service(
        name="x", price=1, category="x",
        duration_slots=duration, processing_slots=posa,
        slots_before_processing=prima,
    )


class TestQualiSlotOccupano:
    def test_senza_posa_occupa_tutto(self):
        """Il comportamento di sempre, che è anche il caso più comune."""
        assert busy_slot_offsets([_finto(3)]) == [0, 1, 2]

    def test_con_posa_salta_gli_slot_di_mezzo(self):
        # Tinta: 30' applicazione, 30' posa, 30' piega.
        assert busy_slot_offsets([_finto(3, posa=1, prima=1)]) == [0, 2]

    def test_posa_lunga(self):
        # 30' applicazione, 60' posa, 30' finitura.
        assert busy_slot_offsets([_finto(4, posa=2, prima=1)]) == [0, 3]

    def test_piu_servizi_si_accodano(self):
        """Colore con posa seguito da un servizio semplice: gli offset del
        secondo partono da dove finisce il primo, posa compresa."""
        assert busy_slot_offsets([_finto(3, posa=1, prima=1), _finto(2)]) == [0, 2, 3, 4]

    def test_una_posa_senza_lavoro_dopo_viene_ignorata(self):
        """Non sarebbe una posa: sarebbe un appuntamento più corto, e
        segnerebbe libero l'ultimo slot con la cliente ancora seduta."""
        assert busy_slot_offsets([_finto(2, posa=1, prima=1)]) == [0, 1]

    def test_nessun_servizio(self):
        assert busy_slot_offsets([]) == []


@pytest_asyncio.fixture
async def colore(db, collaborator) -> Service:
    """Tinta da 90 minuti: 30 di applicazione, 30 di posa, 30 di piega."""
    svc = Service(
        name="Colore con posa", price=60.0, category="Colore",
        duration_slots=3, slots_before_processing=1, processing_slots=1,
        bookable_online=True, is_active=True,
    )
    db.add(svc)
    await db.flush()
    db.add(CollaboratorService(collaborator_id=collaborator.id, service_id=svc.id))
    await db.commit()
    return svc


@pytest_asyncio.fixture
async def giorno_lavorativo(collaborator):
    d = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    while d.weekday() == 6:  # il fixture non lavora di domenica
        d += timedelta(days=1)
    return d


async def _prenota(db, client_id, collaborator_id, servizio, quando):
    appt = Appointment(
        client_id=client_id,
        collaborator_id=collaborator_id,
        start_time=quando,
        end_time=quando + timedelta(minutes=30 * servizio.duration_slots),
        status=AppointmentStatus.confirmed,
    )
    db.add(appt)
    await db.flush()
    db.add(AppointmentService(
        appointment_id=appt.id, service_id=servizio.id,
        price_snapshot=float(servizio.price),
    ))
    await db.commit()
    return appt


class TestLaPosaLiberaIlCollaboratore:
    async def test_un_altro_appuntamento_entra_nel_buco(
        self, db, booking_config, collaborator, colore, service, other_client, giorno_lavorativo
    ):
        """Il punto di tutta la funzionalità: mentre la tinta è in posa
        (10:30–11:00) il collaboratore può servire qualcun altro."""
        inizio = datetime.combine(giorno_lavorativo, time(10, 0), tzinfo=timezone.utc)
        await _prenota(db, other_client.id, collaborator.id, colore, inizio)

        # `service` dura 1 ora, quindi non ci sta nel buco da 30 minuti.
        # Serve un servizio da mezz'ora per verificare l'incastro.
        veloce = Service(
            name="Shampoo", price=10.0, category="Extra",
            duration_slots=1, bookable_online=True, is_active=True,
        )
        db.add(veloce)
        await db.commit()

        liberi = await get_available_slots(
            db, collaborator.id, giorno_lavorativo, 1,
            busy_offsets=busy_slot_offsets([veloce]),
        )
        orari = {s.strftime("%H:%M") for s in liberi}

        assert "10:30" in orari, "la posa non ha liberato lo slot"
        assert "10:00" not in orari, "l'applicazione dovrebbe occupare"
        assert "11:00" not in orari, "la piega dovrebbe occupare"

    async def test_senza_posa_il_buco_non_ce(
        self, db, booking_config, collaborator, service, other_client, giorno_lavorativo
    ):
        """Controprova: lo stesso appuntamento senza posa occupa tutto."""
        pieno = Service(
            name="Trattamento lungo", price=60.0, category="Colore",
            duration_slots=3, bookable_online=True, is_active=True,
        )
        db.add(pieno)
        await db.commit()

        inizio = datetime.combine(giorno_lavorativo, time(10, 0), tzinfo=timezone.utc)
        await _prenota(db, other_client.id, collaborator.id, pieno, inizio)

        liberi = await get_available_slots(db, collaborator.id, giorno_lavorativo, 1)
        orari = {s.strftime("%H:%M") for s in liberi}
        assert "10:30" not in orari
        assert "11:00" not in orari

    async def test_due_appuntamenti_con_posa_si_incastrano(
        self, db, booking_config, collaborator, colore, other_client, giorno_lavorativo
    ):
        """Due tinte sfalsate di mezz'ora: la seconda applica mentre la prima
        è in posa. È così che lavora davvero un salone."""
        inizio = datetime.combine(giorno_lavorativo, time(10, 0), tzinfo=timezone.utc)
        await _prenota(db, other_client.id, collaborator.id, colore, inizio)

        liberi = await get_available_slots(
            db, collaborator.id, giorno_lavorativo, colore.duration_slots,
            busy_offsets=busy_slot_offsets([colore]),
        )
        orari = {s.strftime("%H:%M") for s in liberi}
        assert "10:30" in orari, "la seconda tinta non riesce a incastrarsi"

    async def test_un_appuntamento_allungato_a_mano_occupa_tutto(
        self, db, booking_config, collaborator, colore, other_client, giorno_lavorativo
    ):
        """Se l'agenda allunga un appuntamento oltre la durata dei suoi
        servizi, il pattern non lo descrive più: si torna a occupare tutta la
        fascia. Meglio un buco sprecato che due clienti sulla stessa poltrona.
        """
        inizio = datetime.combine(giorno_lavorativo, time(10, 0), tzinfo=timezone.utc)
        appt = await _prenota(db, other_client.id, collaborator.id, colore, inizio)
        appt.end_time = inizio + timedelta(hours=3)  # allungato a mano
        await db.commit()

        liberi = await get_available_slots(db, collaborator.id, giorno_lavorativo, 1)
        orari = {s.strftime("%H:%M") for s in liberi}
        assert "10:30" not in orari, "ha usato il pattern su una fascia che non corrisponde"


class TestLaPosaAttraversoLApi:
    async def test_il_portale_offre_lo_slot_in_posa(
        self, client, db, booking_config, collaborator, colore, other_client, giorno_lavorativo
    ):
        inizio = datetime.combine(giorno_lavorativo, time(10, 0), tzinfo=timezone.utc)
        await _prenota(db, other_client.id, collaborator.id, colore, inizio)

        resp = await client.get(
            "/api/public/availability",
            params={
                "service_id": colore.id,
                "collaborator_id": collaborator.id,
                "target_date": giorno_lavorativo.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        orari = {s[11:16] for s in resp.json()}
        assert "10:30" in orari

    async def test_si_puo_prenotare_davvero_in_quello_slot(
        self, client, db, booking_config, client_tokens, collaborator, colore,
        other_client, giorno_lavorativo,
    ):
        """Che l'orario compaia nella lista non basta: la POST ha la sua
        validazione e deve arrivare alla stessa conclusione."""
        inizio = datetime.combine(giorno_lavorativo, time(10, 0), tzinfo=timezone.utc)
        await _prenota(db, other_client.id, collaborator.id, colore, inizio)

        quando = datetime.combine(giorno_lavorativo, time(10, 30), tzinfo=timezone.utc)
        resp = await client.post(
            "/api/public/appointments",
            headers=auth(client_tokens),
            json={
                "client_id": 0,
                "collaborator_id": collaborator.id,
                "start_time": quando.isoformat(),
                "end_time": (quando + timedelta(minutes=90)).isoformat(),
                "service_ids": [colore.id],
            },
        )
        assert resp.status_code == 201, resp.text


class TestLaValidazioneDelServizio:
    async def test_posa_senza_lavoro_prima_e_rifiutata(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/services", headers=auth(admin_tokens),
            json={
                "name": "Sbagliato", "price": 10, "category": "x",
                "duration_slots": 3, "slots_before_processing": 0, "processing_slots": 2,
            },
        )
        assert resp.status_code == 422
        assert "prima" in resp.text

    async def test_posa_che_non_lascia_lavoro_dopo_e_rifiutata(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/services", headers=auth(admin_tokens),
            json={
                "name": "Sbagliato", "price": 10, "category": "x",
                "duration_slots": 3, "slots_before_processing": 1, "processing_slots": 2,
            },
        )
        assert resp.status_code == 422
        assert "dopo la posa" in resp.text.lower()

    async def test_una_posa_valida_passa(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/services", headers=auth(admin_tokens),
            json={
                "name": "Colore", "price": 60, "category": "Colore",
                "duration_slots": 3, "slots_before_processing": 1, "processing_slots": 1,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["processing_slots"] == 1

    async def test_una_modifica_parziale_incoerente_e_rifiutata(
        self, client, db, admin_tokens, colore
    ):
        """Accorciare la durata lasciando la posa com'era: ogni singolo campo
        è legittimo, la coppia no. La regola va applicata dopo il merge."""
        resp = await client.put(
            f"/api/admin/services/{colore.id}", headers=auth(admin_tokens),
            json={"duration_slots": 2},
        )
        assert resp.status_code == 422
        assert "posa" in resp.text.lower()

    async def test_un_servizio_senza_posa_resta_valido(self, client, admin_tokens):
        """Non aver dichiarato niente non deve diventare un errore: sono i
        19 servizi che esistono già."""
        resp = await client.post(
            "/api/admin/services", headers=auth(admin_tokens),
            json={"name": "Taglio", "price": 20, "category": "Taglio", "duration_slots": 2},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["processing_slots"] == 0
