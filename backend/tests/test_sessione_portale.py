"""La sessione delle clienti si rinnova, come quella dello staff.

Segnalazione del 2026-10-13 (screenshot del portale): «Invia richiesta» →
«Token non valido». Il token d'accesso dura 30 minuti; il login dava anche un
refresh token da 7 giorni, ma il portale lo buttava e non c'era nessuna rotta
per usarlo. Dopo mezz'ora la cliente risultava collegata e ogni richiesta
tornava 401: fra l'11 e il 13/10 sette prenotazioni rifiutate così.

Qui la rotta di rinnovo: che rinnovi una cliente vera, e che non diventi una
porta di servizio — niente token dello staff, niente access token usati come
refresh, niente rinnovo per un account che al login verrebbe respinto.
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.config import settings
from app.utils.auth import create_refresh_token
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

RINNOVO = "/api/public/auth/refresh"
MIEI = "/api/public/appointments"


def _scaduto(account_id: int) -> str:
    """Un access token cliente vero, ma scaduto da un minuto."""
    return jwt.encode(
        {"sub": str(account_id), "type": "client",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )


class TestRinnovo:
    async def test_il_caso_della_segnalazione(self, client, client_account, client_tokens):
        """Token scaduto → 401; rinnovo → si torna dentro senza rifare il login."""
        r = await client.get(MIEI, headers={"Authorization": f"Bearer {_scaduto(client_account.id)}"})
        assert r.status_code == 401

        r = await client.post(RINNOVO, json={"refresh_token": client_tokens["refresh_token"]})
        assert r.status_code == 200, r.text
        nuovi = r.json()

        r = await client.get(MIEI, headers=auth(nuovi))
        assert r.status_code == 200, r.text

    async def test_si_rinnova_anche_dopo(self, client, client_tokens):
        """Il refresh che torna è a sua volta un refresh cliente valido."""
        primo = (await client.post(RINNOVO, json={"refresh_token": client_tokens["refresh_token"]})).json()
        r = await client.post(RINNOVO, json={"refresh_token": primo["refresh_token"]})
        assert r.status_code == 200, r.text

    async def test_il_token_rinnovato_non_vale_per_lo_staff(self, client, client_tokens):
        nuovi = (await client.post(RINNOVO, json={"refresh_token": client_tokens["refresh_token"]})).json()
        r = await client.get("/api/admin/clients", headers=auth(nuovi))
        assert r.status_code == 401


class TestNonEUnaPortaDiServizio:
    async def test_refresh_dello_staff_no(self, client, admin_tokens):
        r = await client.post(RINNOVO, json={"refresh_token": admin_tokens["refresh_token"]})
        assert r.status_code == 401

    async def test_refresh_dello_staff_con_l_id_di_una_cliente_no(self, client, client_account):
        """Il caso che conta: gli id di `users` e `client_accounts` si
        sovrappongono, quindi un refresh dello staff col numero giusto
        troverebbe un account cliente vero. Lo ferma il tipo, non l'id."""
        staff = create_refresh_token(client_account.id, {"role": "admin"})
        r = await client.post(RINNOVO, json={"refresh_token": staff})
        assert r.status_code == 401

    async def test_access_token_al_posto_del_refresh_no(self, client, client_tokens):
        r = await client.post(RINNOVO, json={"refresh_token": client_tokens["access_token"]})
        assert r.status_code == 401

    async def test_spazzatura_no(self, client):
        r = await client.post(RINNOVO, json={"refresh_token": "non-un-jwt"})
        assert r.status_code == 401

    @pytest.mark.parametrize("campo", ["is_active", "email_verified", "phone_verified"])
    async def test_account_che_al_login_verrebbe_respinto(
        self, client, db, client_account, client_tokens, campo,
    ):
        setattr(client_account, campo, False)
        await db.commit()
        r = await client.post(RINNOVO, json={"refresh_token": client_tokens["refresh_token"]})
        assert r.status_code == 401

    async def test_il_refresh_cliente_resta_fuori_dallo_scambio_staff(self, client, client_tokens):
        """L'altra metà della stessa regola, già vera prima: va tenuta."""
        r = await client.post("/api/admin/auth/refresh", json={"refresh_token": client_tokens["refresh_token"]})
        assert r.status_code == 401
