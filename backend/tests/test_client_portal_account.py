"""
L'accesso al portale creato dal salone, per una cliente iscritta al banco.

Prima di questa rotta un account esisteva solo se la cliente se lo faceva da
sola. Chi veniva iscritta in salone restava una riga di anagrafica senza
`account_id`: nessuna password, nessun modo di entrare.

La cosa che questi test tengono ferma più di ogni altra è che **la password
non sia un valore fisso**. Una password uguale per tutte le clienti — l'idea
di partenza era `0000` — non è una password: chiunque conosca l'indirizzo
email di una cliente entrerebbe nel suo account, e in un salone di quartiere
un indirizzo email non è un segreto. `test_due_clienti_non_ricevono_la_stessa`
è la regressione contro il ritorno di quell'idea.

L'altra metà è che l'account creato sia **davvero utilizzabile**: creare un
account che poi il login rifiuta sarebbe peggio che non crearlo, perché
l'operatore detta una password e la cliente sbatte contro un errore che
nessuno dei due sa spiegare.
"""
import logging

import pytest
from sqlalchemy import select

from app.models.client import Client, ClientAccount
from app.models.user import User, UserRole
from app.schemas.client import MIN_CLIENT_PASSWORD
from app.services import portal_account
from app.utils.auth import hash_password
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


async def _crea(http, tokens, client_id: int):
    return await http.post(
        f"/api/admin/clients/{client_id}/portal-account", headers=auth(tokens)
    )


class TestCreazione:
    async def test_crea_l_account_e_lo_collega_alla_scheda(
        self, client, db, admin_tokens, other_client
    ):
        resp = await _crea(client, admin_tokens, other_client.id)
        assert resp.status_code == 201, resp.text

        corpo = resp.json()
        assert corpo["email"] == other_client.email
        assert corpo["temp_password"]

        await db.refresh(other_client)
        assert other_client.account_id is not None

        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.id == other_client.account_id)
        )).scalar_one()
        assert account.email == other_client.email

    async def test_la_password_restituita_fa_entrare_davvero(
        self, client, db, admin_tokens, other_client
    ):
        """Il punto della funzione.

        Non «esiste una riga in `client_accounts`», ma «l'operatore detta questa
        password al banco e la cliente entra». Fra le due c'è `email_verified`:
        senza, il login risponde 403 e la password consegnata non apre niente.
        """
        resp = await _crea(client, admin_tokens, other_client.id)
        password = resp.json()["temp_password"]

        login = await client.post(
            "/api/public/auth/login",
            json={"email": other_client.email, "password": password},
        )
        assert login.status_code == 200, login.text
        assert login.json()["access_token"]

    async def test_entra_anche_dalla_schermata_unica(
        self, client, admin_tokens, other_client
    ):
        """Le due porte d'ingresso devono dire la stessa cosa: se una accetta
        l'account e l'altra lo rifiuta, la cliente sbaglia schermata e nessuno
        capisce perché."""
        resp = await _crea(client, admin_tokens, other_client.id)
        password = resp.json()["temp_password"]

        login = await client.post(
            "/api/auth/login",
            json={"email": other_client.email, "password": password},
        )
        assert login.status_code == 200, login.text
        assert login.json()["audience"] == "client"

    async def test_l_hash_a_database_non_e_la_password(
        self, client, db, admin_tokens, other_client
    ):
        resp = await _crea(client, admin_tokens, other_client.id)
        password = resp.json()["temp_password"]

        await db.refresh(other_client)
        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.id == other_client.account_id)
        )).scalar_one()
        assert account.password_hash != password


class TestLaPasswordNonEFissa:
    """La regressione che conta: il ritorno di una password uguale per tutte."""

    async def test_due_clienti_non_ricevono_la_stessa(
        self, client, db, admin_tokens, other_client
    ):
        seconda = Client(
            first_name="Seconda", last_name="Test", email="seconda@nsh-test.it"
        )
        db.add(seconda)
        await db.commit()

        una = (await _crea(client, admin_tokens, other_client.id)).json()["temp_password"]
        due = (await _crea(client, admin_tokens, seconda.id)).json()["temp_password"]

        assert una != due

    async def test_ne_genera_molte_e_sono_tutte_diverse(self):
        """Cento estrazioni: una collisione qui vorrebbe dire che il generatore
        pesca da un insieme minuscolo, che è la stessa malattia della password
        fissa con un vestito diverso."""
        estratte = {portal_account.genera_password() for _ in range(100)}
        assert len(estratte) == 100

    async def test_rispetta_il_minimo_del_portale(self):
        """Se la generata fosse più corta del minimo, la cliente si troverebbe
        con una password che il portale stesso rifiuta di farle riusare."""
        assert len(portal_account.genera_password()) >= MIN_CLIENT_PASSWORD

    @pytest.mark.parametrize("ambiguo", ["0", "O", "1", "I", "L"])
    async def test_niente_caratteri_che_si_sbagliano_a_dettarli(self, ambiguo):
        """Questa password viene letta ad alta voce al banco o al telefono.
        `0`/`O` e `1`/`I`/`L` si sbagliano sempre, e una password sbagliata di
        un carattere è indistinguibile da una password sbagliata e basta."""
        assert ambiguo not in portal_account.ALFABETO


class TestQuandoRifiuta:
    async def test_cliente_che_ha_gia_un_account(
        self, client, db, admin_tokens, client_account
    ):
        scheda = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        resp = await _crea(client, admin_tokens, scheda.id)
        assert resp.status_code == 400
        assert "già un accesso" in resp.json()["detail"]

    async def test_cliente_senza_email(self, client, db, admin_tokens):
        """Senza indirizzo non c'è niente con cui entrare: `ClientAccount.email`
        è la chiave del login."""
        senza = Client(first_name="Senza", last_name="Email", phone="+393330000009")
        db.add(senza)
        await db.commit()

        resp = await _crea(client, admin_tokens, senza.id)
        assert resp.status_code == 400
        assert "email" in resp.json()["detail"].lower()

        await db.refresh(senza)
        assert senza.account_id is None

    async def test_email_gia_usata_dallo_staff(self, client, db, admin_tokens):
        """Staff e clienti entrano dalla stessa schermata, che cerca prima fra
        lo staff: due account sullo stesso indirizzo renderebbero il login
        ambiguo, e la cliente non entrerebbe mai."""
        db.add(User(
            email="doppia@nsh-test.it",
            password_hash=await hash_password("staff-password-lunga"),
            role=UserRole.collaborator,
        ))
        scheda = Client(first_name="Doppia", last_name="Test", email="doppia@nsh-test.it")
        db.add(scheda)
        await db.commit()

        resp = await _crea(client, admin_tokens, scheda.id)
        assert resp.status_code == 400
        assert "staff" in resp.json()["detail"].lower()

        await db.refresh(scheda)
        assert scheda.account_id is None

    async def test_email_gia_usata_da_un_altro_account_cliente(
        self, client, db, admin_tokens, client_account
    ):
        """Due schede con lo stesso indirizzo: l'account esiste già su quella
        vecchia. `ClientAccount.email` è unique, quindi senza questo controllo
        arriverebbe un 500 dal database invece di una frase leggibile."""
        gemella = Client(
            first_name="Gemella", last_name="Test", email=client_account.email
        )
        db.add(gemella)
        await db.commit()

        resp = await _crea(client, admin_tokens, gemella.id)
        assert resp.status_code == 400
        assert "già un account" in resp.json()["detail"]

        await db.refresh(gemella)
        assert gemella.account_id is None

    async def test_un_rifiuto_non_lascia_account_orfani(
        self, client, db, admin_tokens, client_account
    ):
        """Il rifiuto deve arrivare **prima** di scrivere: un account creato e
        poi non collegato resterebbe a occupare l'indirizzo per sempre."""
        prima = (await db.execute(select(ClientAccount))).scalars().all()

        gemella = Client(
            first_name="Gemella", last_name="Test", email=client_account.email
        )
        db.add(gemella)
        await db.commit()
        await _crea(client, admin_tokens, gemella.id)

        dopo = (await db.execute(select(ClientAccount))).scalars().all()
        assert len(dopo) == len(prima)

    async def test_cliente_inesistente(self, client, admin_tokens):
        resp = await _crea(client, admin_tokens, 999999)
        assert resp.status_code == 404


class TestPermessi:
    async def test_un_collaboratore_non_puo(
        self, client, collab_tokens, other_client
    ):
        """Stessa famiglia del reset e della fusione: crea una credenziale
        valida per l'account di un'altra persona, che è un'altra cosa dal
        leggerne la scheda — quella è `staff`."""
        resp = await _crea(client, collab_tokens, other_client.id)
        assert resp.status_code == 403

    async def test_senza_token_non_si_entra(self, client, other_client):
        resp = await client.post(
            f"/api/admin/clients/{other_client.id}/portal-account"
        )
        assert resp.status_code == 401

    async def test_un_collaboratore_respinto_non_crea_niente(
        self, client, db, collab_tokens, other_client
    ):
        await _crea(client, collab_tokens, other_client.id)
        await db.refresh(other_client)
        assert other_client.account_id is None


class TestRegistro:
    async def test_la_password_non_finisce_nei_log(
        self, client, db, caplog, admin_tokens, other_client
    ):
        """Esce una volta nella risposta HTTP e basta. Nei log non deve
        comparire: un registro è un archivio che resta, e una password che ci
        finisce dentro sopravvive a chiunque l'abbia cambiata."""
        with caplog.at_level(logging.DEBUG):
            resp = await _crea(client, admin_tokens, other_client.id)

        password = resp.json()["temp_password"]
        tutto = " ".join(
            f"{r.getMessage()} {r.__dict__}" for r in caplog.records
        )
        assert password not in tutto

    async def test_scrive_che_l_account_e_nato_dal_gestionale(
        self, client, caplog, admin_tokens, other_client
    ):
        """Stesso nome di evento della registrazione dal portale, con `tipo` a
        distinguerle: chi cerca «quando è nato questo account» ha una riga sola
        da cercare, non due a seconda di chi l'ha creato."""
        with caplog.at_level(logging.INFO):
            await _crea(client, admin_tokens, other_client.id)

        registrazioni = [
            r for r in caplog.records
            if getattr(r, "evento", None) == "registrazione"
        ]
        assert registrazioni
        assert any(getattr(r, "tipo", None) == "creato_da_admin" for r in registrazioni)
