"""
L'admin reimposta la password del portale di una cliente.

Il buco che chiude: una cliente che non entra più aveva una sola strada, il
`forgot-password` che manda un link all'indirizzo dell'account. Se è
l'indirizzo stesso a non essere più raggiungibile — casella persa, indirizzo
del lavoro precedente, dominio chiuso — quella strada non porta da nessuna
parte, e in salone non c'era niente da fare. Lo staff aveva già il suo
equivalente in `POST /api/admin/team/{user_id}/reset-password`.

Tre cose che questa rotta deve fare oltre a cambiare l'hash, e che sono la
ragione per cui i test qui sotto non si fermano al 204:
  - restare admin, non staff: dà accesso all'account di un'altra persona;
  - invalidare un link di reset già in volo, altrimenti chi ce l'ha in mano
    sovrascrive la password appena dettata al telefono;
  - rifiutare sugli account non verificati, dove cambiare la password non
    farebbe entrare comunque nessuno.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.client import Client, ClientAccount
from app.utils.auth import verify_password
from tests.conftest import CLIENT_PASSWORD, auth

pytestmark = pytest.mark.asyncio

NUOVA = "password-nuova-1234"


async def _scheda(db, account: ClientAccount) -> Client:
    return (await db.execute(
        select(Client).where(Client.account_id == account.id)
    )).scalar_one()


class TestReset:
    async def test_la_password_cambia_davvero(
        self, client, db, admin_tokens, client_account
    ):
        scheda = await _scheda(db, client_account)

        resp = await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": NUOVA},
        )
        assert resp.status_code == 204, resp.text

        await db.refresh(client_account)
        assert await verify_password(NUOVA, client_account.password_hash)
        assert not await verify_password(CLIENT_PASSWORD, client_account.password_hash)

    async def test_dopo_il_reset_la_cliente_entra(
        self, client, db, admin_tokens, client_account
    ):
        """Il punto della funzione: non l'hash nel database, il login che
        funziona quando l'operatore detta la password al telefono."""
        scheda = await _scheda(db, client_account)

        await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": NUOVA},
        )

        resp = await client.post(
            "/api/public/auth/login",
            json={"email": client_account.email, "password": NUOVA},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["access_token"]

    async def test_la_vecchia_password_non_entra_piu(
        self, client, db, admin_tokens, client_account
    ):
        scheda = await _scheda(db, client_account)
        await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": NUOVA},
        )

        resp = await client.post(
            "/api/public/auth/login",
            json={"email": client_account.email, "password": CLIENT_PASSWORD},
        )
        assert resp.status_code == 401

    async def test_un_link_di_reset_in_volo_viene_annullato(
        self, client, db, admin_tokens, client_account
    ):
        """Lo scenario vero: la cliente chiede il reset, non riceve la mail,
        telefona. Se il token restasse valido, chiunque avesse quel link —
        compresa una casella non più sua — potrebbe sovrascrivere subito
        dopo la password appena impostata."""
        client_account.reset_token = "token-ancora-buono"
        client_account.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.commit()

        scheda = await _scheda(db, client_account)
        await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": NUOVA},
        )

        await db.refresh(client_account)
        assert client_account.reset_token is None
        assert client_account.reset_token_expires is None

        # E il token non deve funzionare nemmeno passando dalla rotta pubblica.
        resp = await client.post(
            "/api/public/auth/reset-password",
            json={"token": "token-ancora-buono", "new_password": "un-altra-password"},
        )
        assert resp.status_code == 400

        await db.refresh(client_account)
        assert await verify_password(NUOVA, client_account.password_hash)


class TestRifiuti:
    async def test_account_non_verificato_rifiutato(
        self, client, db, admin_tokens, client_account
    ):
        """Cambiare la password qui non farebbe entrare nessuno: il login
        rifiuta comunque finché l'indirizzo non è verificato. Rifiutare con
        un messaggio è l'unico esito che non lascia l'operatore a chiedersi
        perché la password dettata non funziona."""
        client_account.email_verified = False
        await db.commit()
        scheda = await _scheda(db, client_account)

        resp = await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": NUOVA},
        )
        assert resp.status_code == 400
        assert "verificat" in resp.json()["detail"]

        await db.refresh(client_account)
        assert await verify_password(CLIENT_PASSWORD, client_account.password_hash)

    async def test_cliente_senza_account_portale_rifiutata(
        self, client, admin_tokens, other_client
    ):
        """`other_client` è una cliente da banco: esiste la scheda, non
        l'accesso online. Non c'è niente da reimpostare."""
        resp = await client.post(
            f"/api/admin/clients/{other_client.id}/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": NUOVA},
        )
        assert resp.status_code == 400
        assert "account" in resp.json()["detail"].lower()

    async def test_scheda_inesistente(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/clients/999999/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": NUOVA},
        )
        assert resp.status_code == 404

    async def test_password_troppo_corta_rifiutata(
        self, client, db, admin_tokens, client_account
    ):
        """Stesso minimo del portale: se qui fosse più basso, questa rotta
        sarebbe il modo di aggirare la regola."""
        scheda = await _scheda(db, client_account)

        resp = await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": "corta"},
        )
        assert resp.status_code == 422

        await db.refresh(client_account)
        assert await verify_password(CLIENT_PASSWORD, client_account.password_hash)


class TestPermessi:
    async def test_il_collaboratore_non_puo(
        self, client, db, collab_tokens, client_account
    ):
        """Non è una rotta di consultazione: dà a chi la chiama l'accesso
        all'account di un'altra persona. Sta con `admin` come il merge, non
        con `staff` come la lettura della scheda."""
        scheda = await _scheda(db, client_account)

        resp = await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            headers=auth(collab_tokens),
            json={"new_password": NUOVA},
        )
        assert resp.status_code == 403

        await db.refresh(client_account)
        assert await verify_password(CLIENT_PASSWORD, client_account.password_hash)

    async def test_la_cliente_non_puo_toccare_le_altre(
        self, client, db, client_tokens, client_account
    ):
        """Il token del portale non apre le rotte del gestionale, e questa
        meno delle altre."""
        scheda = await _scheda(db, client_account)

        resp = await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            headers=auth(client_tokens),
            json={"new_password": NUOVA},
        )
        assert resp.status_code in (401, 403)

    async def test_senza_token_rifiutata(self, client, db, client_account):
        scheda = await _scheda(db, client_account)
        resp = await client.post(
            f"/api/admin/clients/{scheda.id}/reset-password",
            json={"new_password": NUOVA},
        )
        assert resp.status_code in (401, 403)
