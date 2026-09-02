"""
I messaggi che parte il salone devono usare un template approvato da Meta.

WhatsApp divide i messaggi in due categorie, e la differenza non è di stile:
dentro le 24 ore da un messaggio della cliente si può scrivere quel che si
vuole, fuori si può mandare **solo** testo che Meta ha già approvato. Un
messaggio libero fuori finestra viene rifiutato con l'errore 63016.

Conferme, promemoria, auguri e reset password partono tutti a freddo — nessuno
di loro nasce da un messaggio della cliente — quindi in produzione sono tutti
nella seconda categoria. In Sandbox funzionavano lo stesso perché il `join`
apre una sessione, ed è precisamente il motivo per cui il problema non si
vedeva: la Sandbox è più permissiva del posto in cui il codice deve girare.

Quello che questi test tengono fermo:
  - i quattro automatici mandano `ContentSid`, non `Body`, quando il template
    è configurato;
  - le variabili finiscono nelle posizioni giuste — sbagliare l'ordine manda
    alla cliente l'ora al posto del nome, e non se ne accorge nessuno finché
    non lo legge lei;
  - senza SID configurato si continua col testo libero, che è ciò che tiene
    in piedi la Sandbox mentre Meta approva;
  - la chat resta testo libero, perché è l'unico canale che sta dentro la
    finestra per costruzione.
"""
import json

import pytest

from app.config import settings
from app.utils import whatsapp

pytestmark = pytest.mark.asyncio


class Spia:
    """Raccoglie il payload invece di chiamare Twilio."""

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
    return s


@pytest.fixture
def twilio_configurato(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC-test")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "token-test")
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "whatsapp:+390123456789")


class TestSceltaFraTemplateETestoLibero:
    async def test_con_il_sid_manda_il_template(self, spia):
        await whatsapp.send_whatsapp_template(
            "+393330000001", "HX-conferma", {"1": "Giulia"}, ripiego="ciao"
        )
        assert spia.ultimo["ContentSid"] == "HX-conferma"
        assert "Body" not in spia.ultimo, "col template il Body non deve partire"

    async def test_senza_sid_ripiega_sul_testo_libero(self, spia):
        """Il caso Sandbox e il tempo in cui Meta sta ancora approvando."""
        await whatsapp.send_whatsapp_template(
            "+393330000001", "", {"1": "Giulia"}, ripiego="ciao Giulia"
        )
        assert spia.ultimo == {"Body": "ciao Giulia"}

    async def test_le_variabili_partono_come_json_posizionale(self, spia):
        """Meta vuole `{{1}}`, `{{2}}`: il formato è suo, non nostro."""
        await whatsapp.send_whatsapp_template(
            "+393330000001",
            "HX-x",
            {"1": "Giulia", "2": "25/07/2026"},
            ripiego="—",
        )
        assert json.loads(spia.ultimo["ContentVariables"]) == {
            "1": "Giulia", "2": "25/07/2026",
        }

    async def test_gli_accenti_non_diventano_escape(self, spia):
        """`ensure_ascii=False`: con l'escape la cliente leggerebbe
        `Perch\\u00e9` al posto del suo nome o del servizio."""
        await whatsapp.send_whatsapp_template(
            "+393330000001", "HX-x", {"1": "Niccolò"}, ripiego="—"
        )
        assert "Niccolò" in spia.ultimo["ContentVariables"]


class TestIQuattroAutomatici:
    """Ognuno deve passare dal suo template, con le sue variabili in ordine."""

    async def test_conferma(self, spia, monkeypatch, db, booking_config, collaborator, client_account):
        from datetime import datetime, timedelta, timezone
        from app.models.appointment import Appointment
        from sqlalchemy import select
        from app.models.client import Client

        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_CONFERMA", "HX-conferma")
        scheda = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        quando = datetime.now(timezone.utc) + timedelta(days=2)
        appuntamento = Appointment(
            client_id=scheda.id, collaborator_id=collaborator.id,
            start_time=quando, end_time=quando + timedelta(hours=1),
        )
        db.add(appuntamento)
        await db.flush()
        appuntamento.client = scheda
        appuntamento.collaborator = collaborator

        await whatsapp.send_booking_confirmation(appuntamento, booking_config)

        assert spia.ultimo["ContentSid"] == "HX-conferma"
        variabili = json.loads(spia.ultimo["ContentVariables"])
        assert variabili["1"] == scheda.first_name
        assert variabili["2"] == quando.strftime("%d/%m/%Y")
        assert variabili["3"] == quando.strftime("%H:%M")
        assert collaborator.first_name in variabili["4"]

    async def test_promemoria(self, spia, monkeypatch, db, booking_config, collaborator, client_account):
        """Quello che parte più spesso di tutti: uno per ogni appuntamento."""
        from datetime import datetime, timedelta, timezone
        from app.models.appointment import Appointment
        from sqlalchemy import select
        from app.models.client import Client

        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_PROMEMORIA", "HX-promemoria")
        scheda = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        quando = datetime.now(timezone.utc) + timedelta(days=1)
        appuntamento = Appointment(
            client_id=scheda.id, collaborator_id=collaborator.id,
            start_time=quando, end_time=quando + timedelta(hours=1),
        )
        db.add(appuntamento)
        await db.flush()
        appuntamento.client = scheda
        appuntamento.collaborator = collaborator

        await whatsapp.send_reminder_message(appuntamento, booking_config)

        assert spia.ultimo["ContentSid"] == "HX-promemoria"
        variabili = json.loads(spia.ultimo["ContentVariables"])
        assert variabili["1"] == scheda.first_name
        assert variabili["2"] == quando.strftime("%d/%m/%Y")
        assert variabili["3"] == quando.strftime("%H:%M")

    async def test_conferma_e_promemoria_usano_template_diversi(
        self, spia, monkeypatch, db, booking_config, collaborator, client_account
    ):
        """Sono due testi diversi e due approvazioni Meta diverse: scambiarli
        manderebbe «confermata» il giorno prima e «ti ricordiamo» alla
        prenotazione. Un copia-incolla fra le due funzioni è esattamente il
        modo in cui succederebbe."""
        from datetime import datetime, timedelta, timezone
        from app.models.appointment import Appointment
        from sqlalchemy import select
        from app.models.client import Client

        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_CONFERMA", "HX-conferma")
        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_PROMEMORIA", "HX-promemoria")
        scheda = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        quando = datetime.now(timezone.utc) + timedelta(days=1)
        appuntamento = Appointment(
            client_id=scheda.id, collaborator_id=collaborator.id,
            start_time=quando, end_time=quando + timedelta(hours=1),
        )
        db.add(appuntamento)
        await db.flush()
        appuntamento.client = scheda
        appuntamento.collaborator = collaborator

        await whatsapp.send_booking_confirmation(appuntamento, booking_config)
        await whatsapp.send_reminder_message(appuntamento, booking_config)

        usati = [json.loads(c[1]["ContentVariables"]) and c[1]["ContentSid"]
                 for c in spia.chiamate]
        assert usati == ["HX-conferma", "HX-promemoria"]

    async def test_compleanno(self, spia, monkeypatch, other_client):
        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_COMPLEANNO", "HX-auguri")
        other_client.phone = "+393330000003"

        await whatsapp.send_birthday_message(other_client)

        assert spia.ultimo["ContentSid"] == "HX-auguri"
        assert json.loads(spia.ultimo["ContentVariables"]) == {
            "1": other_client.first_name
        }

    async def test_reset_password(self, spia, monkeypatch):
        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_RESET_PASSWORD", "HX-reset")

        await whatsapp.send_password_reset_message(
            "+393330000004", "Giulia", "https://www.newstylehair.it/r/abc"
        )

        assert spia.ultimo["ContentSid"] == "HX-reset"
        variabili = json.loads(spia.ultimo["ContentVariables"])
        assert variabili["1"] == "Giulia"
        assert variabili["2"] == "https://www.newstylehair.it/r/abc"

    async def test_nessuno_dei_quattro_manda_body_col_template(
        self, spia, monkeypatch, other_client
    ):
        """La regressione che conta: se uno tornasse a `Body`, in produzione
        smetterebbe di partire senza che nessun test se ne accorga."""
        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_COMPLEANNO", "HX-auguri")
        monkeypatch.setattr(settings, "TWILIO_TEMPLATE_RESET_PASSWORD", "HX-reset")
        other_client.phone = "+393330000003"

        await whatsapp.send_birthday_message(other_client)
        await whatsapp.send_password_reset_message("+393330000004", "X", "https://x.it")

        for _, contenuto in spia.chiamate:
            assert "Body" not in contenuto
            assert "ContentSid" in contenuto


class TestQuelloCheResta:
    async def test_il_messaggio_libero_resta_libero(self, spia, other_client):
        """Un testo scritto a mano non può essere pre-approvato: per
        definizione non esiste un template che lo contenga."""
        other_client.phone = "+393330000003"
        await whatsapp.send_custom_message_wa(other_client, "Ciao {nome}, siamo aperti!")

        assert "Body" in spia.ultimo
        assert "ContentSid" not in spia.ultimo
        assert other_client.first_name in spia.ultimo["Body"]

    async def test_senza_twilio_non_parte_niente(self, monkeypatch, other_client):
        """Comportamento di sempre: senza credenziali si avvisa e si tace,
        non si solleva — una notifica non spedita non deve far fallire la
        prenotazione che l'ha generata."""
        monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "")
        monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "")
        other_client.phone = "+393330000003"

        await whatsapp.send_birthday_message(other_client)  # non solleva

    async def test_il_numero_viene_normalizzato(self, twilio_configurato, monkeypatch):
        """`_invia` è ora condivisa fra testo e template: la normalizzazione
        del numero deve valere per entrambi, non solo per il ramo vecchio."""
        catturato = {}

        class FintaRisposta:
            status_code = 201
            text = "{}"

        class FintoClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, **kw):
                catturato.update(kw["data"])
                return FintaRisposta()

        monkeypatch.setattr(whatsapp.httpx, "AsyncClient", lambda: FintoClient())

        await whatsapp.send_whatsapp_template(
            "393330000005", "HX-x", {"1": "a"}, ripiego="—"  # senza il +
        )
        assert catturato["To"] == "whatsapp:+393330000005"
