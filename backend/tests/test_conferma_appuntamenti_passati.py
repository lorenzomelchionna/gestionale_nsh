"""Nessuna conferma per un appuntamento già passato.

La conferma parte da `create_appointment` lato gestionale e dal passaggio
`pending → confirmed`, e finora non guardava la data. Per l'uso normale non si
notava: si confermano appuntamenti futuri. Si nota quando il salone **carica
lo storico** — ogni riga inserita manda alla cliente una conferma per una data
trascorsa, via email e WhatsApp.

Non è solo rumore. I template utility fuori dalla finestra di 24 ore si
pagano, e una raffica di messaggi inattesi è esattamente ciò che fa segnalare
un numero WhatsApp — su un numero appena attivato, senza storico a difenderlo,
è il modo più rapido per rovinarne la reputazione.

La guardia sta in `notify_booking_confirmation` e non nell'endpoint: così vale
per ogni chiamante, presente e futuro, invece che per quello che è venuto in
mente oggi.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentStatus
from app.models.client import Client
from app.utils.tempo import adesso

pytestmark = pytest.mark.asyncio


async def _appuntamento(db, client_account, collaborator, quando) -> Appointment:
    cliente = (await db.execute(
        select(Client).where(Client.account_id == client_account.id)
    )).scalar_one()
    cliente.phone = "+393331112222"
    cliente.email = "cliente@example.com"
    await db.flush()

    appt = Appointment(
        client_id=cliente.id,
        collaborator_id=collaborator.id,
        start_time=quando,
        end_time=quando + timedelta(minutes=30),
        status=AppointmentStatus.confirmed,
    )
    db.add(appt)
    await db.commit()
    await db.refresh(appt, ["client", "collaborator"])
    return appt


@pytest.fixture
def canali(monkeypatch):
    """Registra cosa sarebbe partito, senza far partire niente."""
    from app.utils import notifications as notif

    inviati = {"email": 0, "whatsapp": 0}

    async def email(*a, **kw):
        inviati["email"] += 1

    async def whatsapp(*a, **kw):
        inviati["whatsapp"] += 1

    monkeypatch.setattr(notif.email_util, "send_booking_confirmation_email", email)
    monkeypatch.setattr(notif.wa_util, "send_booking_confirmation", whatsapp)
    monkeypatch.setattr(notif, "_wa_enabled", lambda cfg: True)
    return inviati


class TestPassato:
    async def test_un_appuntamento_di_ieri_non_manda_niente(
        self, db, client_account, collaborator, canali
    ):
        from app.utils.notifications import notify_booking_confirmation

        appt = await _appuntamento(
            db, client_account, collaborator, adesso() - timedelta(days=1)
        )
        await notify_booking_confirmation(db, appt)

        assert canali == {"email": 0, "whatsapp": 0}

    async def test_nemmeno_di_un_minuto_fa(
        self, db, client_account, collaborator, canali
    ):
        """Il confine è «passato», non «ieri»: un orario appena trascorso è
        comunque una conferma che arriva dopo."""
        from app.utils.notifications import notify_booking_confirmation

        appt = await _appuntamento(
            db, client_account, collaborator, adesso() - timedelta(minutes=1)
        )
        await notify_booking_confirmation(db, appt)

        assert canali == {"email": 0, "whatsapp": 0}


class TestFuturo:
    async def test_un_appuntamento_futuro_manda_ancora(
        self, db, client_account, collaborator, canali
    ):
        """La guardia non deve spegnere il caso normale, che è la ragione per
        cui la conferma esiste."""
        from app.utils.notifications import notify_booking_confirmation

        appt = await _appuntamento(
            db, client_account, collaborator, adesso() + timedelta(days=2)
        )
        await notify_booking_confirmation(db, appt)

        assert canali == {"email": 1, "whatsapp": 1}
