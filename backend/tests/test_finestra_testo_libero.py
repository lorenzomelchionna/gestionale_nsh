"""Conferme e promemoria come testo libero quando la cliente ha appena scritto.

WhatsApp fa pagare due cose diverse per lo stesso messaggio. Un template
approvato si può mandare sempre e costa ~0,035 $; il testo libero si può
mandare solo entro 24 ore dall'ultimo messaggio della cliente e costa la sola
tariffa Twilio, ~0,005 $. Dal 1/10 all'11/11 sono partiti 78 template a
clienti che avevano scritto da meno di 24 ore — la cliente chiede un orario in
chat, il salone lo inserisce, parte la conferma.

Quello che questi test tengono fermo:
  - dentro la finestra parte `Body`, fuori `ContentSid`: il risparmio c'è
    solo se la scelta è giusta, e la scelta sbagliata nell'altro verso costa
    di più — un testo libero fuori finestra Twilio lo accetta e la consegna
    fallisce dopo (63016), cioè la cliente non riceve niente e nessuno lo sa;
  - il margine: a finestra che sta per chiudersi si paga il template;
  - il testo libero è parola per parola quello approvato, con le stesse
    variabili, così la cliente non vede differenze;
  - senza chat (mai scritto, o chat eliminata dal salone) si va di template.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.appointment import Appointment, AppointmentStatus
from app.models.chat import Conversation
from app.models.client import Client
from app.services.chat import MARGINE_FINESTRA, finestra_aperta
from app.utils import whatsapp
from app.utils.tempo import ora_salone

pytestmark = pytest.mark.asyncio

NUMERO = "+393330000002"  # quello della scheda di `client_account`


class Spia:
    def __init__(self):
        self.chiamate: list[tuple[str, dict]] = []

    async def __call__(self, to_phone: str, contenuto: dict) -> None:
        self.chiamate.append((to_phone, contenuto))

    @property
    def ultimo(self) -> dict:
        return self.chiamate[-1][1]


@pytest.fixture
def spia(monkeypatch) -> Spia:
    s = Spia()
    monkeypatch.setattr(whatsapp, "_invia", s)
    monkeypatch.setattr(settings, "TWILIO_TEMPLATE_CONFERMA", "HX-conferma")
    monkeypatch.setattr(settings, "TWILIO_TEMPLATE_PROMEMORIA", "HX-promemoria")
    return s


@pytest.fixture
def niente_email(monkeypatch):
    from app.utils import notifications as notif

    async def muta(*a, **kw):
        return None

    monkeypatch.setattr(notif.email_util, "send_booking_confirmation_email", muta)
    monkeypatch.setattr(notif.email_util, "send_appointment_reminder", muta)
    monkeypatch.setattr(notif, "_wa_enabled", lambda cfg: True)


async def _chat(db, phone: str, scritto_fa: timedelta | None) -> Conversation:
    conv = Conversation(
        phone=phone,
        last_inbound_at=None if scritto_fa is None else datetime.now(timezone.utc) - scritto_fa,
    )
    db.add(conv)
    await db.commit()
    return conv


async def _appuntamento(db, client_account, collaborator, fra=timedelta(days=1)) -> Appointment:
    cliente = (await db.execute(
        select(Client).where(Client.account_id == client_account.id)
    )).scalar_one()
    quando = datetime.now(timezone.utc) + fra
    appt = Appointment(
        client_id=cliente.id, collaborator_id=collaborator.id,
        start_time=quando, end_time=quando + timedelta(minutes=30),
        status=AppointmentStatus.confirmed,
    )
    db.add(appt)
    await db.commit()
    await db.refresh(appt, ["client", "collaborator"])
    return appt


class TestFinestraAperta:
    async def test_senza_chat_e_chiusa(self, db):
        assert await finestra_aperta(db, NUMERO) is False

    async def test_chat_senza_messaggi_in_entrata_e_chiusa(self, db):
        await _chat(db, NUMERO, None)
        assert await finestra_aperta(db, NUMERO) is False

    async def test_scritto_un_ora_fa_e_aperta(self, db):
        await _chat(db, NUMERO, timedelta(hours=1))
        assert await finestra_aperta(db, NUMERO) is True

    async def test_scritto_ieri_e_chiusa(self, db):
        await _chat(db, NUMERO, timedelta(hours=25))
        assert await finestra_aperta(db, NUMERO) is False

    async def test_finestra_che_sta_per_chiudersi_conta_come_chiusa(self, db):
        """Mancano 5 minuti: meno del margine, si paga il template."""
        await _chat(db, NUMERO, timedelta(hours=24) - timedelta(minutes=5))
        assert MARGINE_FINESTRA > timedelta(minutes=5)
        assert await finestra_aperta(db, NUMERO) is False

    async def test_appena_dentro_il_margine_e_aperta(self, db):
        await _chat(db, NUMERO, timedelta(hours=24) - MARGINE_FINESTRA - timedelta(minutes=5))
        assert await finestra_aperta(db, NUMERO) is True

    async def test_il_numero_della_scheda_viene_normalizzato(self, db):
        """Sulla scheda il numero può avere spazi, la chat lo tiene in E.164."""
        await _chat(db, NUMERO, timedelta(hours=1))
        assert await finestra_aperta(db, "+39 333 000 0002") is True

    async def test_un_altro_numero_non_apre_la_finestra(self, db):
        await _chat(db, NUMERO, timedelta(hours=1))
        assert await finestra_aperta(db, "+393339999999") is False

    @pytest.mark.parametrize("vuoto", [None, ""])
    async def test_senza_numero_e_chiusa(self, db, vuoto):
        assert await finestra_aperta(db, vuoto) is False


class TestTestoCompilato:
    async def test_e_identico_al_template_approvato(self):
        testo = whatsapp._compila(
            whatsapp.TESTO_APPROVATO_CONFERMA,
            {"1": "Giulia", "2": "12/11/2026", "3": "15:00", "4": "Flavia Rossi"},
        )
        assert testo == (
            "Ciao Giulia! La tua prenotazione da New Style Hair è confermata "
            "per il 12/11/2026 alle 15:00 con Flavia Rossi. A presto!"
        )

    async def test_un_valore_con_un_segnaposto_non_viene_riscritto(self):
        testo = whatsapp._compila("{{1}} e {{2}}", {"1": "{{2}}", "2": "X"})
        assert testo == "{{2}} e X"


class TestSceltaNelLivelloWhatsapp:
    async def test_in_finestra_parte_il_testo_libero(self, spia):
        await whatsapp.send_whatsapp_template(
            NUMERO, "HX-x", {"1": "Giulia"}, ripiego="—",
            approvato="Ciao {{1}}!", finestra_aperta=True,
        )
        assert spia.ultimo == {"Body": "Ciao Giulia!"}

    async def test_fuori_finestra_parte_il_template(self, spia):
        await whatsapp.send_whatsapp_template(
            NUMERO, "HX-x", {"1": "Giulia"}, ripiego="—",
            approvato="Ciao {{1}}!", finestra_aperta=False,
        )
        assert spia.ultimo["ContentSid"] == "HX-x"
        assert "Body" not in spia.ultimo

    async def test_senza_testo_approvato_resta_il_template(self, spia):
        """Il codice di verifica non passa un testo approvato: resta template."""
        await whatsapp.send_whatsapp_template(
            NUMERO, "HX-x", {"1": "123456"}, ripiego="—", finestra_aperta=True,
        )
        assert spia.ultimo["ContentSid"] == "HX-x"


class TestDallaNotificaAlMessaggio:
    """Il percorso vero: `notify_*` legge la chat e sceglie il formato."""

    async def test_conferma_a_chi_ha_scritto_da_poco(
        self, spia, niente_email, db, booking_config, collaborator, client_account
    ):
        from app.utils.notifications import notify_booking_confirmation

        await _chat(db, NUMERO, timedelta(hours=2))
        appt = await _appuntamento(db, client_account, collaborator)
        assert await notify_booking_confirmation(db, appt) is True

        inizio = ora_salone(appt.start_time)
        nome_collab = f"{collaborator.first_name} {collaborator.last_name}"
        assert spia.ultimo == {"Body": (
            f"Ciao Giulia! La tua prenotazione da New Style Hair è confermata "
            f"per il {inizio:%d/%m/%Y} alle {inizio:%H:%M} con {nome_collab}. A presto!"
        )}

    async def test_conferma_a_chi_non_ha_mai_scritto(
        self, spia, niente_email, db, booking_config, collaborator, client_account
    ):
        from app.utils.notifications import notify_booking_confirmation

        appt = await _appuntamento(db, client_account, collaborator)
        await notify_booking_confirmation(db, appt)
        assert spia.ultimo["ContentSid"] == "HX-conferma"

    async def test_promemoria_a_chi_ha_scritto_da_poco(
        self, spia, niente_email, db, booking_config, collaborator, client_account
    ):
        from app.utils.notifications import notify_appointment_reminder

        await _chat(db, NUMERO, timedelta(hours=3))
        appt = await _appuntamento(db, client_account, collaborator)
        assert await notify_appointment_reminder(db, appt) is True

        inizio = ora_salone(appt.start_time)
        nome_collab = f"{collaborator.first_name} {collaborator.last_name}"
        assert spia.ultimo == {"Body": (
            f"Ciao Giulia! Ti ricordiamo il tuo appuntamento da New Style Hair "
            f"il {inizio:%d/%m/%Y} alle {inizio:%H:%M} con {nome_collab}. A presto!"
        )}

    async def test_promemoria_a_chi_ha_scritto_due_giorni_fa(
        self, spia, niente_email, db, booking_config, collaborator, client_account
    ):
        from app.utils.notifications import notify_appointment_reminder

        await _chat(db, NUMERO, timedelta(days=2))
        appt = await _appuntamento(db, client_account, collaborator)
        await notify_appointment_reminder(db, appt)
        assert spia.ultimo["ContentSid"] == "HX-promemoria"
