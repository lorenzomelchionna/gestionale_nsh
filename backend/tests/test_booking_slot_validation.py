"""
Il portale non può scegliersi l'orario che vuole.

Prima di questi test l'endpoint pubblico validava servizi e collaboratore ma
prendeva `start_time` ed `end_time` così come arrivavano dal browser. Il
frontend li calcola bene, quindi non si notava nulla — ma il frontend non è la
convalida, e la stessa chiamata fatta con curl poteva scrivere in agenda un
appuntamento fuori orario, nel passato, sopra quello di un'altra cliente, o
lungo un giorno intero.

Quest'ultimo è il caso che conta: una richiesta `pending` occupa già lo slot
(è giusto che lo faccia), quindi bastava riempire il calendario di prenotazioni
00:00–23:59 per far rispondere "nessuna disponibilità" a chiunque, finché il
salone non ripuliva a mano.
"""
from datetime import datetime, time, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.public.booking import MAX_PENDING_PER_CLIENT
from app.models.appointment import Appointment, AppointmentStatus
from tests.conftest import auth

# Il fixture `collaborator` lavora lun–sab 09:00–19:00, e `service` dura
# 2 slot da 30 minuti = un'ora.
TOMORROW = (datetime.now(timezone.utc) + timedelta(days=1)).date()


def _at(hour: int, minute: int = 0, day=None) -> datetime:
    return datetime.combine(day or TOMORROW, time(hour, minute), tzinfo=timezone.utc)


async def _book(http, tokens, collaborator, service_ids, start, end, expect=201):
    resp = await http.post(
        "/api/public/appointments",
        headers=auth(tokens),
        json={
            "client_id": 0,
            "collaborator_id": collaborator.id,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "service_ids": service_ids,
        },
    )
    assert resp.status_code == expect, f"atteso {expect}, ottenuto {resp.status_code}: {resp.text}"
    return resp


@pytest_asyncio.fixture
async def second_service(db):
    """Un servizio da un solo slot, per verificare la somma delle durate."""
    from app.models.service import Service

    svc = Service(
        name="Barba test", price=15.0, duration_slots=1,
        category="Barba", bookable_online=True, is_active=True,
    )
    db.add(svc)
    await db.commit()
    return svc


@pytest_asyncio.fixture
async def collaborator_two_services(db, collaborator, second_service):
    from app.models.collaborator import CollaboratorService

    db.add(CollaboratorService(collaborator_id=collaborator.id, service_id=second_service.id))
    await db.commit()
    return collaborator


@pytest_asyncio.fixture
async def working_day(db, collaborator):
    """Un giorno in cui il collaboratore lavora davvero.

    TOMORROW può cadere di domenica, quando il fixture non ha orario: in quel
    caso gli slot sarebbero vuoti per un motivo che non c'entra col test.
    """
    day = TOMORROW
    while day.weekday() == 6:  # domenica: il fixture non lavora
        day += timedelta(days=1)
    return day


class TestSoloGliSlotOfferti:
    async def test_uno_slot_libero_si_prenota(
        self, client, booking_config, client_tokens, collaborator, service, working_day
    ):
        start = _at(10, 0, working_day)
        await _book(client, client_tokens, collaborator, [service.id], start, start + timedelta(hours=1))

    async def test_fuori_orario_di_lavoro_e_rifiutato(
        self, client, booking_config, client_tokens, collaborator, service, working_day
    ):
        """Le 3 di notte non compaiono in nessuna lista di disponibilità."""
        start = _at(3, 0, working_day)
        await _book(
            client, client_tokens, collaborator, [service.id],
            start, start + timedelta(hours=1), expect=409,
        )

    async def test_un_orario_nel_passato_e_rifiutato(
        self, client, booking_config, client_tokens, collaborator, service
    ):
        start = datetime.now(timezone.utc) - timedelta(days=2)
        await _book(
            client, client_tokens, collaborator, [service.id],
            start, start + timedelta(hours=1), expect=409,
        )

    async def test_un_orario_non_allineato_agli_slot_e_rifiutato(
        self, client, booking_config, client_tokens, collaborator, service, working_day
    ):
        """10:17 non è l'inizio di nessuno slot da 30 minuti."""
        start = _at(10, 17, working_day)
        await _book(
            client, client_tokens, collaborator, [service.id],
            start, start + timedelta(hours=1), expect=409,
        )

    async def test_troppo_avanti_nel_futuro_e_rifiutato(
        self, client, db, booking_config, client_tokens, collaborator, service
    ):
        far = datetime.now(timezone.utc) + timedelta(days=booking_config.max_advance_days + 10)
        while far.weekday() == 6:
            far += timedelta(days=1)
        start = _at(10, 0, far.date())
        await _book(
            client, client_tokens, collaborator, [service.id],
            start, start + timedelta(hours=1), expect=400,
        )

    async def test_non_si_prenota_sopra_un_appuntamento_esistente(
        self, client, booking_config, client_tokens, collaborator, service, working_day
    ):
        start = _at(11, 0, working_day)
        await _book(client, client_tokens, collaborator, [service.id], start, start + timedelta(hours=1))
        # Stesso slot, stesso collaboratore: il primo lo occupa già anche se
        # è solo `pending`.
        await _book(
            client, client_tokens, collaborator, [service.id],
            start, start + timedelta(hours=1), expect=409,
        )


class TestLaDurataLaDecideIlServer:
    async def test_un_end_time_lunghissimo_viene_ignorato(
        self, client, db, booking_config, client_tokens, collaborator, service, working_day
    ):
        """Il caso che svuotava il calendario: 00:00–23:59 in una richiesta sola."""
        start = _at(10, 0, working_day)
        await _book(
            client, client_tokens, collaborator, [service.id],
            start, start + timedelta(hours=13),  # fine dichiarata dal client
        )
        appt = (await db.execute(select(Appointment))).scalar_one()
        # Due slot da 30 minuti: la durata del servizio, non quella dichiarata.
        assert appt.end_time - appt.start_time == timedelta(hours=1)

    async def test_un_end_time_prima_dello_start_viene_ignorato(
        self, client, db, booking_config, client_tokens, collaborator, service, working_day
    ):
        start = _at(12, 0, working_day)
        await _book(
            client, client_tokens, collaborator, [service.id],
            start, start - timedelta(hours=5),
        )
        appt = (await db.execute(select(Appointment))).scalar_one()
        assert appt.end_time > appt.start_time

    async def test_due_servizi_sommano_la_durata(
        self, client, db, booking_config, client_tokens, collaborator_two_services,
        service, second_service, working_day,
    ):
        start = _at(14, 0, working_day)
        await _book(
            client, client_tokens, collaborator_two_services,
            [service.id, second_service.id], start, start + timedelta(minutes=1),
        )
        appt = (await db.execute(select(Appointment))).scalar_one()
        # 2 slot + 1 slot = 3 × 30 minuti.
        assert appt.end_time - appt.start_time == timedelta(minutes=90)

    async def test_lo_slot_occupato_riflette_la_durata_reale(
        self, client, booking_config, client_tokens, collaborator, service, working_day
    ):
        """Se l'orario di fine fosse quello dichiarato, la disponibilità
        successiva sarebbe calcolata su un appuntamento inesistente."""
        start = _at(15, 0, working_day)
        await _book(
            client, client_tokens, collaborator, [service.id],
            start, start + timedelta(hours=4),
        )
        resp = await client.get(
            "/api/public/availability",
            params={
                "service_id": service.id,
                "collaborator_id": collaborator.id,
                "target_date": working_day.isoformat(),
            },
        )
        liberi = resp.json()
        assert _at(16, 0, working_day).isoformat() in liberi, "ha bloccato ore che non gli spettano"
        assert _at(15, 0, working_day).isoformat() not in liberi, "non ha bloccato la propria ora"


class TestTettoAlleRichiesteInAttesa:
    async def test_oltre_il_tetto_si_viene_fermati(
        self, client, booking_config, client_tokens, collaborator, service, working_day
    ):
        ore = [10, 11, 12, 13, 14, 15]
        for i in range(MAX_PENDING_PER_CLIENT):
            start = _at(ore[i], 0, working_day)
            await _book(client, client_tokens, collaborator, [service.id], start, start + timedelta(hours=1))

        start = _at(ore[MAX_PENDING_PER_CLIENT], 0, working_day)
        resp = await _book(
            client, client_tokens, collaborator, [service.id],
            start, start + timedelta(hours=1), expect=429,
        )
        assert "attesa" in resp.json()["detail"]

    async def test_una_richiesta_confermata_non_conta_piu(
        self, client, db, booking_config, client_tokens, collaborator, service, working_day
    ):
        """Il tetto guarda le richieste senza risposta, non gli appuntamenti."""
        ore = [10, 11, 12, 13]
        for i in range(MAX_PENDING_PER_CLIENT):
            start = _at(ore[i], 0, working_day)
            await _book(client, client_tokens, collaborator, [service.id], start, start + timedelta(hours=1))

        prima = (await db.execute(
            select(Appointment).order_by(Appointment.id)
        )).scalars().first()
        prima.status = AppointmentStatus.confirmed
        await db.commit()

        start = _at(ore[MAX_PENDING_PER_CLIENT], 0, working_day)
        await _book(client, client_tokens, collaborator, [service.id], start, start + timedelta(hours=1))
