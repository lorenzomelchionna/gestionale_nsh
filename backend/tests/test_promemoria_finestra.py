"""Quando parte il promemoria.

Prima: ogni 15 minuti il worker cercava gli appuntamenti che iniziano fra
**24 ore esatte**, con una finestra larga 15 minuti. Due buchi:

1. **Chi prenota con meno di 24 ore di anticipo non riceveva mai niente.**
   L'appuntamento nasceva già «dentro» le 24 ore, quindi non passava mai per
   la fetta «fra 24 ore». Trovato il 2026-09-23: Flavia prenota per il giorno
   stesso, arriva la conferma, il promemoria no. In un salone le prenotazioni
   per oggi e domani sono le più comuni.
2. **Un giro saltato era un promemoria perso.** La finestra era larga quanto
   l'intervallo fra due giri: se il worker ripartiva — un rilascio — gli
   appuntamenti di quei 15 minuti non ricomparivano più.

Ora: promemoria a ogni appuntamento confermato che inizia **entro** le
prossime N ore e non l'ha ancora ricevuto (il flag impedisce i doppioni), ma
**non nella prima ora dopo la conferma** — altrimenti chi prenota per oggi
riceverebbe due messaggi a un quarto d'ora di distanza, e il secondo si paga.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentStatus
from app.models.client import Client

pytestmark = pytest.mark.asyncio


def _adesso() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def canali(monkeypatch):
    """Conta cosa sarebbe partito, senza mandare niente."""
    from app.utils import notifications as notif

    inviati = {"promemoria": 0, "conferma": 0}

    async def promemoria(*a, **kw):
        inviati["promemoria"] += 1

    async def conferma(*a, **kw):
        inviati["conferma"] += 1

    monkeypatch.setattr(notif.email_util, "send_appointment_reminder", promemoria)
    monkeypatch.setattr(notif.wa_util, "send_reminder_message", promemoria)
    monkeypatch.setattr(notif.email_util, "send_booking_confirmation_email", conferma)
    monkeypatch.setattr(notif.wa_util, "send_booking_confirmation", conferma)
    monkeypatch.setattr(notif, "_wa_enabled", lambda cfg: True)
    return inviati


async def _appuntamento(
    db, client_account, collaborator, *, fra: timedelta,
    conferma_fa: timedelta | None = None,
    status: AppointmentStatus = AppointmentStatus.confirmed,
    promemoria_gia_mandato: bool = False,
) -> int:
    cliente = (await db.execute(
        select(Client).where(Client.account_id == client_account.id)
    )).scalar_one()
    cliente.phone = "+393331112222"
    cliente.email = "cliente@example.com"

    inizio = _adesso() + fra
    appt = Appointment(
        client_id=cliente.id,
        collaborator_id=collaborator.id,
        start_time=inizio,
        end_time=inizio + timedelta(minutes=30),
        status=status,
        reminder_sent=promemoria_gia_mandato,
        confirmation_sent_at=None if conferma_fa is None else _adesso() - conferma_fa,
    )
    db.add(appt)
    await db.commit()
    return appt.id


async def _giro_del_worker():
    from app.tasks import reminders
    await reminders._async_send_reminders()


async def _promemoria_segnato(db, appt_id: int) -> bool:
    db.expire_all()
    appt = (await db.execute(select(Appointment).where(Appointment.id == appt_id))).scalar_one()
    return appt.reminder_sent


class TestPrenotazioniRavvicinate:
    async def test_prenotazione_per_oggi_riceve_il_promemoria(
        self, db, client_account, collaborator, booking_config, canali
    ):
        """Il caso di Flavia: appuntamento fra 5 ore, conferma partita 2 ore fa."""
        appt = await _appuntamento(
            db, client_account, collaborator,
            fra=timedelta(hours=5), conferma_fa=timedelta(hours=2),
        )
        await _giro_del_worker()

        assert canali["promemoria"] > 0
        assert await _promemoria_segnato(db, appt)

    async def test_non_parte_nella_prima_ora_dopo_la_conferma(
        self, db, client_account, collaborator, booking_config, canali
    ):
        """Due messaggi a un quarto d'ora di distanza sono uno di troppo."""
        appt = await _appuntamento(
            db, client_account, collaborator,
            fra=timedelta(hours=5), conferma_fa=timedelta(minutes=10),
        )
        await _giro_del_worker()

        assert canali["promemoria"] == 0
        assert not await _promemoria_segnato(db, appt)

    async def test_prenotazione_troppo_vicina_nessun_promemoria(
        self, db, client_account, collaborator, booking_config, canali
    ):
        """Prenotata per fra 30 minuti: la conferma è appena arrivata, e
        un'ora dopo l'appuntamento è già iniziato. Niente promemoria."""
        await _appuntamento(
            db, client_account, collaborator,
            fra=timedelta(minutes=30), conferma_fa=timedelta(minutes=5),
        )
        await _giro_del_worker()

        assert canali["promemoria"] == 0


class TestFinestra:
    async def test_un_giro_saltato_non_perde_il_promemoria(
        self, db, client_account, collaborator, booking_config, canali
    ):
        """Fra 23 ore: la vecchia finestra (24h–24h15) l'avrebbe persa per
        sempre se il giro giusto fosse saltato."""
        appt = await _appuntamento(
            db, client_account, collaborator, fra=timedelta(hours=23),
        )
        await _giro_del_worker()

        assert await _promemoria_segnato(db, appt)

    async def test_oltre_le_24_ore_aspetta(
        self, db, client_account, collaborator, booking_config, canali
    ):
        appt = await _appuntamento(
            db, client_account, collaborator, fra=timedelta(hours=30),
        )
        await _giro_del_worker()

        assert canali["promemoria"] == 0
        assert not await _promemoria_segnato(db, appt)

    async def test_non_si_ripete(
        self, db, client_account, collaborator, booking_config, canali
    ):
        await _appuntamento(
            db, client_account, collaborator,
            fra=timedelta(hours=5), promemoria_gia_mandato=True,
        )
        await _giro_del_worker()

        assert canali["promemoria"] == 0

    async def test_appuntamento_gia_iniziato_nessun_promemoria(
        self, db, client_account, collaborator, booking_config, canali
    ):
        await _appuntamento(
            db, client_account, collaborator, fra=-timedelta(minutes=10),
        )
        await _giro_del_worker()

        assert canali["promemoria"] == 0

    async def test_in_attesa_di_conferma_nessun_promemoria(
        self, db, client_account, collaborator, booking_config, canali
    ):
        await _appuntamento(
            db, client_account, collaborator,
            fra=timedelta(hours=5), status=AppointmentStatus.pending,
        )
        await _giro_del_worker()

        assert canali["promemoria"] == 0


class TestLaConfermaSiSegnaQuandoParte:
    """La prima ora si conta da quando la conferma è **partita**, non da quando
    l'appuntamento è nato: una prenotazione online resta «in attesa» anche un
    giorno, e viene confermata dopo."""

    async def test_segnata_all_invio(
        self, db, client_account, collaborator, canali
    ):
        from app.tasks import reminders

        appt_id = await _appuntamento(
            db, client_account, collaborator, fra=timedelta(hours=5),
        )
        prima = _adesso()
        await reminders._async_send_booking_confirmation(appt_id)

        db.expire_all()
        appt = (await db.execute(select(Appointment).where(Appointment.id == appt_id))).scalar_one()
        assert canali["conferma"] > 0
        assert appt.confirmation_sent_at is not None
        assert appt.confirmation_sent_at >= prima

    async def test_non_segnata_se_non_parte_niente(
        self, db, client_account, collaborator, canali
    ):
        """Un appuntamento passato non riceve conferma: segnarla comunque
        bloccherebbe per un'ora un promemoria per niente."""
        from app.tasks import reminders

        appt_id = await _appuntamento(
            db, client_account, collaborator, fra=-timedelta(days=1),
        )
        await reminders._async_send_booking_confirmation(appt_id)

        db.expire_all()
        appt = (await db.execute(select(Appointment).where(Appointment.id == appt_id))).scalar_one()
        assert canali["conferma"] == 0
        assert appt.confirmation_sent_at is None
