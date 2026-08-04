"""
Le email non recapitano il markup di chi le ha innescate.

Ogni messaggio di `utils/email.py` è una f-string di HTML, quindi tutto ciò che
viene interpolato è markup finché qualcuno non lo escapa. Il punto scoperto era
`/register`: non richiede autenticazione, accetta `first_name` così com'è e lo
spedisce a un indirizzo scelto da chi chiama, dal mittente verificato del
salone. Cioè una primitiva per mandare HTML arbitrario con SPF e DKIM validi.

Questi test non passano dagli endpoint: intercettano `send_email`, che è il
punto dove il corpo è già stato costruito e non è ancora partito nulla.
"""
import pytest

from app.utils import email as email_util

# Il payload sta in una variabile sola: se un giorno cambia, cambia per tutti
# i mittenti insieme e nessun test resta indietro a controllare l'altro.
PAYLOAD = '<a href="https://phish.example">clicca qui</a>'
ATTESO = "&lt;a href=&quot;https://phish.example&quot;&gt;"


@pytest.fixture
def spedita(monkeypatch):
    """Cattura (destinatario, oggetto, corpo) invece di spedire."""
    box = []

    async def fake_send_email(to, subject, html_body):
        box.append((to, subject, html_body))

    monkeypatch.setattr(email_util, "send_email", fake_send_email)
    return box


class Finto:
    """Il minimo che i mittenti leggono, senza toccare il database."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _cliente(nome=PAYLOAD):
    return Finto(id=1, first_name=nome, last_name="Test", email="vittima@example.com", phone="+393330000001")


def _appuntamento(nome=PAYLOAD):
    from datetime import datetime, timezone

    return Finto(
        id=1,
        client=_cliente(nome),
        collaborator=Finto(first_name="Sofia", last_name="Test"),
        start_time=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
        notes=None,
        appointment_services=[],
    )


def _assert_pulita(box):
    assert box, "nessuna email prodotta"
    corpo = box[-1][2]
    assert PAYLOAD not in corpo, "il markup è passato intatto"
    assert ATTESO in corpo, "il testo non è stato escapato, è stato perso"


class TestIlPuntoScoperto:
    async def test_codice_di_verifica(self, spedita):
        """L'unico mittente innescabile da uno sconosciuto non autenticato."""
        await email_util.send_verification_code_email(
            "vittima@example.com", PAYLOAD, "123456", 15
        )
        _assert_pulita(spedita)

    async def test_reset_password(self, spedita):
        await email_util.send_password_reset_email(
            "vittima@example.com", PAYLOAD, "https://app.example/reset?token=abc"
        )
        _assert_pulita(spedita)


class TestGliAltriMittenti:
    """Alimentati dal database, quindi scrivibili solo dallo staff o dal
    register stesso — ma la regola vale per tutti, così non c'è da ricordarsi
    quale sia il mittente pericoloso di turno."""

    async def test_promemoria(self, spedita):
        await email_util.send_appointment_reminder(_appuntamento())
        _assert_pulita(spedita)

    async def test_conferma_prenotazione(self, spedita):
        await email_util.send_booking_confirmation_email(_appuntamento())
        _assert_pulita(spedita)

    async def test_auguri_di_compleanno(self, spedita):
        await email_util.send_birthday_greeting(_cliente())
        _assert_pulita(spedita)

    async def test_aggiornamento_stato(self, spedita):
        await email_util.send_booking_status_email(_appuntamento(), "Aggiornata")
        _assert_pulita(spedita)

    async def test_messaggio_personalizzato(self, spedita):
        await email_util.send_custom_message(_cliente(), "Oggetto", "Testo normale")
        _assert_pulita(spedita)

    async def test_avviso_allo_staff(self, spedita):
        """Già escapato prima di questo lavoro: qui si verifica che sia
        rimasto tale dopo aver unificato l'helper."""
        appt = _appuntamento(nome="Mario")
        appt.notes = PAYLOAD
        await email_util.send_new_booking_staff_email("salone@example.com", appt)
        _assert_pulita(spedita)


class TestIlCorpoScrittoDalloStaff:
    async def test_le_righe_restano_righe(self, spedita):
        """Escapare non deve togliere l'unica formattazione voluta: gli a capo
        digitati nella pagina Messaggi diventano `<br>`."""
        await email_util.send_custom_message(_cliente("Mario"), "Oggetto", "riga uno\nriga due")
        corpo = spedita[-1][2]
        assert "riga uno<br>riga due" in corpo

    async def test_il_markup_nel_corpo_non_passa(self, spedita):
        await email_util.send_custom_message(_cliente("Mario"), "Oggetto", PAYLOAD)
        _assert_pulita(spedita)
