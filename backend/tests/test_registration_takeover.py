"""
Registrarsi col numero di un'altra persona non dà accesso alla sua scheda.

La registrazione collegava l'account a un'anagrafica esistente cercandola per
`telefono OPPURE email`, e riscriveva `account_id` senza guardare se fosse già
occupato — il tutto **prima** che l'indirizzo fosse verificato.

In un salone di quartiere il cellulare di una cliente è la cosa meno segreta
che ci sia, quindi bastava conoscerlo per:
  - farsi consegnare tutto il suo storico appuntamenti (date, servizi, prezzi,
    note interne) leggendo il codice sulla PROPRIA casella;
  - cancellarle gli appuntamenti e prenotare a suo nome;
  - staccarla dalla sua stessa anagrafica — questa parte senza nemmeno
    verificare l'email, cioè da un endpoint del tutto anonimo.

Ora l'aggancio avviene in `verify-email`, sull'indirizzo appena dimostrato, e
solo su un'anagrafica che non appartiene già a qualcun altro.
"""
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.client import Client, ClientAccount
from app.services.email_verification import issue_code
from tests.conftest import auth

REGISTER = "/api/public/auth/register"
VERIFY = "/api/public/auth/verify-email"
PASSWORD = "una-password-lunga-abbastanza"

TELEFONO_VITTIMA = "+393334445566"


def _registrazione(email, phone=TELEFONO_VITTIMA, nome="Malintenzionato"):
    return {
        "first_name": nome,
        "last_name": "Test",
        "phone": phone,
        "email": email,
        "password": PASSWORD,
        "birth_date": "1990-01-01",
    }


async def _codice(db, email: str) -> str:
    """Il codice reale, come lo leggerebbe chi possiede quella casella."""
    account = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == email)
    )).scalar_one()
    code = issue_code(account)
    await db.commit()
    return code


@pytest_asyncio.fixture
async def vittima(db) -> Client:
    """Una cliente seguita in salone: telefono in scheda, nessun account online."""
    c = Client(
        first_name="Anna",
        last_name="Vittima",
        phone=TELEFONO_VITTIMA,
        email="anna.vittima@nsh-test.it",
        birth_date=date(1985, 4, 20),
        notes="Preferisce il pomeriggio",
    )
    db.add(c)
    await db.commit()
    return c


class TestIlNumeroDiUnAltroNonBasta:
    async def test_registrarsi_col_suo_telefono_non_aggancia_la_sua_scheda(
        self, client, db, vittima
    ):
        resp = await client.post(REGISTER, json=_registrazione("attaccante@example.com"))
        assert resp.status_code == 201, resp.text

        await db.refresh(vittima)
        assert vittima.account_id is None, "la scheda della vittima è stata agganciata"

    async def test_neanche_dopo_aver_verificato_la_propria_email(
        self, client, db, vittima
    ):
        await client.post(REGISTER, json=_registrazione("attaccante@example.com"))
        code = await _codice(db, "attaccante@example.com")

        resp = await client.post(
            VERIFY, json={"email": "attaccante@example.com", "code": code}
        )
        assert resp.status_code == 200, resp.text

        await db.refresh(vittima)
        assert vittima.account_id is None, "agganciata alla verifica invece che alla registrazione"

    async def test_lo_storico_della_vittima_resta_suo(
        self, client, db, vittima, collaborator, service
    ):
        """Il bottino dell'attacco: gli appuntamenti di un'altra persona."""
        from datetime import datetime, timedelta, timezone

        from app.models.appointment import Appointment, AppointmentStatus

        quando = datetime.now(timezone.utc) + timedelta(days=3)
        db.add(Appointment(
            client_id=vittima.id,
            collaborator_id=collaborator.id,
            start_time=quando,
            end_time=quando + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
            visit_notes="Nota interna del salone",
        ))
        await db.commit()

        await client.post(REGISTER, json=_registrazione("attaccante@example.com"))
        code = await _codice(db, "attaccante@example.com")
        tokens = (await client.post(
            VERIFY, json={"email": "attaccante@example.com", "code": code}
        )).json()

        resp = await client.get("/api/public/appointments", headers=auth(tokens))
        assert resp.status_code == 200
        assert resp.json() == [], "ha letto gli appuntamenti di un'altra persona"

    async def test_la_vittima_non_perde_la_propria_anagrafica(
        self, client, db, vittima
    ):
        """La variante distruttiva: partiva senza verificare nulla."""
        await client.post(REGISTER, json=_registrazione("attaccante@example.com"))

        await db.refresh(vittima)
        assert vittima.account_id is None
        assert vittima.email == "anna.vittima@nsh-test.it", "email sovrascritta"
        assert vittima.notes == "Preferisce il pomeriggio"

    async def test_una_scheda_gia_di_qualcuno_non_viene_riassegnata(
        self, client, db, vittima
    ):
        """Due persone possono condividere un indirizzo (una coppia, madre e
        figlia): chi arriva secondo non eredita la scheda del primo."""
        prima = (await client.post(
            REGISTER, json=_registrazione("condivisa@nsh-test.it", nome="Prima")
        ))
        assert prima.status_code == 201
        code = await _codice(db, "condivisa@nsh-test.it")
        await client.post(VERIFY, json={"email": "condivisa@nsh-test.it", "code": code})

        agganciata = (await db.execute(
            select(Client).where(Client.email == "condivisa@nsh-test.it")
        )).scalars().all()
        assert len(agganciata) == 1
        account_id_prima = agganciata[0].account_id
        assert account_id_prima is not None

        # Una seconda persona si registra con lo stesso indirizzo. L'account
        # esistente non è verificato? Lo è. Quindi la registrazione va rifiutata
        # del tutto — ma anche se passasse, la scheda non cambia proprietario.
        seconda = await client.post(
            REGISTER, json=_registrazione("condivisa@nsh-test.it", nome="Seconda")
        )
        assert seconda.status_code == 400

        agganciata = (await db.execute(
            select(Client).where(Client.email == "condivisa@nsh-test.it")
        )).scalars().all()
        assert agganciata[0].account_id == account_id_prima


class TestIlCollegamentoLegittimoFunzionaAncora:
    """La funzionalità esiste per un motivo vero: non duplicare l'anagrafica di
    una cliente già seguita in salone. Deve continuare a valere, ma sull'unico
    dato che a quel punto è dimostrato."""

    async def test_l_email_verificata_aggancia_la_scheda_del_salone(
        self, client, db, vittima
    ):
        resp = await client.post(
            REGISTER,
            json=_registrazione("anna.vittima@nsh-test.it", phone="+393339998877", nome="Anna"),
        )
        assert resp.status_code == 201, resp.text

        # Prima della verifica non è ancora successo niente.
        await db.refresh(vittima)
        assert vittima.account_id is None

        code = await _codice(db, "anna.vittima@nsh-test.it")
        assert (await client.post(
            VERIFY, json={"email": "anna.vittima@nsh-test.it", "code": code}
        )).status_code == 200

        await db.refresh(vittima)
        assert vittima.account_id is not None, "il collegamento legittimo non avviene più"

        righe = (await db.execute(
            select(Client).where(Client.email == "anna.vittima@nsh-test.it")
        )).scalars().all()
        assert len(righe) == 1, "la registrazione ha lasciato un duplicato"
        assert righe[0].id == vittima.id, "ha tenuto la riga sbagliata"
        assert righe[0].notes == "Preferisce il pomeriggio", "persa la storia del salone"

    async def test_i_campi_vuoti_del_salone_vengono_riempiti(
        self, client, db
    ):
        senza = Client(first_name="Chiara", last_name="Esempio", email="chiara@nsh-test.it")
        db.add(senza)
        await db.commit()

        await client.post(
            REGISTER,
            json=_registrazione("chiara@nsh-test.it", phone="+393341112233", nome="Chiara"),
        )
        code = await _codice(db, "chiara@nsh-test.it")
        await client.post(VERIFY, json={"email": "chiara@nsh-test.it", "code": code})

        await db.refresh(senza)
        assert senza.phone == "+393341112233"
        assert senza.birth_date == date(1990, 1, 1)

    async def test_quello_che_il_salone_ha_scritto_vince(self, client, db):
        con_dati = Client(
            first_name="Chiara", last_name="Esempio",
            email="chiara@nsh-test.it",
            phone="+393350000000", birth_date=date(1975, 6, 1),
        )
        db.add(con_dati)
        await db.commit()

        await client.post(
            REGISTER,
            json=_registrazione("chiara@nsh-test.it", phone="+393341112233", nome="Chiara"),
        )
        code = await _codice(db, "chiara@nsh-test.it")
        await client.post(VERIFY, json={"email": "chiara@nsh-test.it", "code": code})

        await db.refresh(con_dati)
        assert con_dati.phone == "+393350000000"
        assert con_dati.birth_date == date(1975, 6, 1)

    async def test_senza_scheda_in_salone_si_crea_la_propria(self, client, db):
        await client.post(REGISTER, json=_registrazione("nuova@nsh-test.it", nome="Nuova"))
        code = await _codice(db, "nuova@nsh-test.it")
        assert (await client.post(
            VERIFY, json={"email": "nuova@nsh-test.it", "code": code}
        )).status_code == 200

        riga = (await db.execute(
            select(Client).where(Client.email == "nuova@nsh-test.it")
        )).scalar_one()
        assert riga.account_id is not None
        assert riga.first_name == "Nuova"

    async def test_una_riga_con_appuntamenti_non_viene_cancellata(
        self, client, db, collaborator, service
    ):
        """Chi si registra e verifica una settimana dopo: nel frattempo il salone
        può aver prenotato sulla riga nuova, vedendola in elenco."""
        from datetime import datetime, timedelta, timezone

        from app.models.appointment import Appointment, AppointmentStatus

        salone = Client(first_name="Rita", last_name="Esempio", email="rita@nsh-test.it")
        db.add(salone)
        await db.commit()

        await client.post(REGISTER, json=_registrazione("rita@nsh-test.it", nome="Rita"))

        stub = (await db.execute(
            select(Client).where(Client.email == "rita@nsh-test.it", Client.account_id.isnot(None))
        )).scalar_one()
        quando = datetime.now(timezone.utc) + timedelta(days=2)
        db.add(Appointment(
            client_id=stub.id, collaborator_id=collaborator.id,
            start_time=quando, end_time=quando + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
        ))
        await db.commit()

        code = await _codice(db, "rita@nsh-test.it")
        await client.post(VERIFY, json={"email": "rita@nsh-test.it", "code": code})

        righe = (await db.execute(
            select(Client).where(Client.email == "rita@nsh-test.it")
        )).scalars().all()
        assert len(righe) == 2, "ha cancellato una riga che aveva un appuntamento"
