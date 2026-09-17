"""
L'ora scritta nei messaggi è quella dell'orologio del salone.

Il difetto che questi test chiudono è arrivato alle clienti per mesi: gli
appuntamenti sono istanti in UTC, i messaggi li formattavano con `strftime`
senza convertire, e così ogni conferma e ogni promemoria annunciavano un
orario **due ore prima** di quello in agenda (una d'inverno).

Non era visibile da nessuna schermata: calendario, portale e area personale
convertono nel fuso del browser, quindi mostravano l'ora giusta. L'unico posto
in cui compariva l'ora sbagliata era il messaggio, cioè l'unico che il salone
non legge.

Il caso del cambio dell'ora è qui perché è l'unico momento in cui uno scarto
fisso — «togli due ore» — darebbe la risposta sbagliata, e perché capita due
volte l'anno senza che nessuno se ne ricordi.
"""
from datetime import date, datetime, time, timezone
from types import SimpleNamespace

import pytest

from app.utils import email as email_util
from app.utils import whatsapp as wa_util
from app.utils.tempo import istante, minuti_salone, ora_salone


def _appuntamento(quando: datetime):
    return SimpleNamespace(
        client=SimpleNamespace(first_name="Giulia", phone="+393330000001",
                               email="giulia@nsh-test.it"),
        collaborator=SimpleNamespace(first_name="Flavia", last_name="Romolo"),
        start_time=quando,
        end_time=quando,
        appointment_services=[],
    )


class TestConversione:
    def test_le_nove_in_salone_sono_le_sette_utc_d_estate(self):
        assert istante(date(2026, 7, 15), time(9, 0)) == datetime(
            2026, 7, 15, 7, 0, tzinfo=timezone.utc
        )

    def test_le_nove_in_salone_sono_le_otto_utc_d_inverno(self):
        """Lo scarto non è una costante: a gennaio l'Italia è su UTC+1."""
        assert istante(date(2026, 1, 15), time(9, 0)) == datetime(
            2026, 1, 15, 8, 0, tzinfo=timezone.utc
        )

    def test_andata_e_ritorno(self):
        quando = istante(date(2026, 7, 15), time(9, 0))
        letto = ora_salone(quando)
        assert (letto.hour, letto.minute) == (9, 0)
        assert minuti_salone(quando) == 9 * 60

    def test_un_valore_senza_fuso_viene_letto_come_utc(self):
        """È ciò che restituisce asyncpg per le colonne `timestamptz`, quindi
        il caso normale in produzione."""
        letto = ora_salone(datetime(2026, 7, 15, 7, 0))
        assert (letto.hour, letto.minute) == (9, 0)


class TestCambioOra:
    """I due giorni in cui uno scarto fisso sbaglierebbe."""

    def test_il_giorno_prima_e_il_giorno_dopo_hanno_scarti_diversi(self):
        prima = istante(date(2026, 3, 28), time(9, 0))   # ancora UTC+1
        dopo = istante(date(2026, 3, 30), time(9, 0))    # già UTC+2
        assert prima.astimezone(timezone.utc).hour == 8
        assert dopo.astimezone(timezone.utc).hour == 7

    def test_stessa_ora_di_orologio_a_cavallo_del_ritorno_all_ora_solare(self):
        prima = istante(date(2026, 10, 24), time(9, 0))  # UTC+2
        dopo = istante(date(2026, 10, 26), time(9, 0))   # UTC+1
        assert prima.astimezone(timezone.utc).hour == 7
        assert dopo.astimezone(timezone.utc).hour == 8

    def test_le_nove_restano_le_nove_in_entrambi_i_casi(self):
        """Il punto dal lato della cliente: comunque vada, legge «09:00»."""
        for giorno in (date(2026, 3, 28), date(2026, 3, 30),
                       date(2026, 10, 24), date(2026, 10, 26)):
            assert ora_salone(istante(giorno, time(9, 0))).strftime("%H:%M") == "09:00"


class TestMessaggi:
    """Quello che la cliente legge davvero."""

    pytestmark = pytest.mark.asyncio

    async def test_whatsapp_conferma_scrive_l_ora_del_salone(self, monkeypatch):
        catturato = {}

        async def finto(to_phone, content_sid, variabili, *, ripiego):
            catturato.update(variabili=variabili, ripiego=ripiego)

        monkeypatch.setattr(wa_util, "send_whatsapp_template", finto)
        # 15 luglio, le 09:00 in salone: a database sono le 07:00 UTC.
        appuntamento = _appuntamento(istante(date(2026, 7, 15), time(9, 0)))
        cfg = SimpleNamespace(whatsapp_booking_message=None)

        await wa_util.send_booking_confirmation(appuntamento, cfg)

        assert catturato["variabili"]["3"] == "09:00", "la cliente deve leggere 09:00"
        assert "09:00" in catturato["ripiego"]
        assert "07:00" not in catturato["ripiego"]

    async def test_whatsapp_promemoria_scrive_l_ora_del_salone(self, monkeypatch):
        catturato = {}

        async def finto(to_phone, content_sid, variabili, *, ripiego):
            catturato.update(variabili=variabili)

        monkeypatch.setattr(wa_util, "send_whatsapp_template", finto)
        appuntamento = _appuntamento(istante(date(2026, 1, 15), time(9, 0)))
        cfg = SimpleNamespace(whatsapp_reminder_message=None)

        await wa_util.send_reminder_message(appuntamento, cfg)

        assert catturato["variabili"]["3"] == "09:00", "anche d'inverno, con scarto di 1h"

    @pytest.mark.parametrize("giorno", [date(2026, 7, 15), date(2026, 1, 15)])
    async def test_l_email_di_conferma_scrive_l_ora_del_salone(self, monkeypatch, giorno):
        catturato = {}

        async def finto(to_email, subject, html_body, **kw):
            catturato.update(corpo=html_body)

        monkeypatch.setattr(email_util, "send_email", finto)
        appuntamento = _appuntamento(istante(giorno, time(9, 0)))

        await email_util.send_booking_confirmation_email(appuntamento)

        assert "09:00" in catturato["corpo"], "la cliente deve leggere 09:00"
        assert "07:00" not in catturato["corpo"]
        assert "08:00" not in catturato["corpo"]

    async def test_niente_scarto_fisso(self, monkeypatch):
        """La regressione contro la correzione sbagliata: sottrarre sempre due
        ore funziona d'estate e rompe d'inverno."""
        letti = []

        async def finto(to_email, subject, html_body, **kw):
            letti.append(html_body)

        monkeypatch.setattr(email_util, "send_email", finto)
        for giorno in (date(2026, 7, 15), date(2026, 1, 15)):
            await email_util.send_booking_confirmation_email(
                _appuntamento(istante(giorno, time(14, 30)))
            )

        assert all("14:30" in corpo for corpo in letti)
