"""«Password dimenticata» dal portale, dall'inizio alla fine.

Fino al 2026-11-11 il backend mandava la mail ma il percorso non arrivava da
nessuna parte: nella pagina di accesso non c'era il pulsante, e il link
della mail puntava a `/booking/reset-password`, una pagina che il frontend
non aveva — il router la mandava alla home. Ogni pezzo funzionava da solo;
mancava che si toccassero. Per questo qui il percorso si prova intero: la
richiesta, il link che esce nella mail, il token preso **da quel link**, il
cambio, il login con la password nuova.

Due scelte che i test tengono ferme:
  - il token sta dopo `#`, non dopo `?`: la parte dopo `#` il browser non la
    manda al server, quindi aprire il link non scrive il token nel registro
    di nginx;
  - il percorso del link esiste fra le rotte del frontend, che è esattamente
    la cosa che si era rotta senza che nessun test se ne accorgesse.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select

from app.api.public.auth import PERCORSO_RESET
from app.config import settings
from app.models.client import ClientAccount
from tests.conftest import CLIENT_PASSWORD

pytestmark = pytest.mark.asyncio

FORGOT = "/api/public/auth/forgot-password"
RESET = "/api/public/auth/reset-password"
LOGIN = "/api/public/auth/login"
NUOVA = "una-password-nuova-lunga"

APP_TSX = Path(__file__).resolve().parents[2] / "frontend" / "src" / "App.tsx"


@pytest.fixture
def posta(monkeypatch) -> list[dict]:
    """Le mail di reset che sarebbero partite, al posto di Brevo."""
    from app.utils import notifications

    inviate: list[dict] = []

    async def finta(to_email, first_name, reset_url):
        inviate.append({"a": to_email, "nome": first_name, "url": reset_url})

    monkeypatch.setattr(notifications.email_util, "send_password_reset_email", finta)
    return inviate


def _token(url: str) -> str:
    frammento = urlsplit(url).fragment
    m = re.fullmatch(r"token=([A-Za-z0-9_-]+)", frammento)
    assert m, f"token non trovato nel frammento: {url!r}"
    return m.group(1)


class TestIlLink:
    async def test_la_mail_parte_con_un_link_alla_pagina_del_portale(
        self, client, client_account, posta
    ):
        resp = await client.post(FORGOT, json={"email": client_account.email})
        assert resp.status_code == 200
        assert len(posta) == 1
        assert posta[0]["a"] == client_account.email
        assert posta[0]["nome"] == "Giulia"

        url = urlsplit(posta[0]["url"])
        atteso = urlsplit(settings.FRONTEND_URL)
        assert (url.scheme, url.netloc) == (atteso.scheme, atteso.netloc)
        assert url.path == PERCORSO_RESET

    async def test_il_token_sta_nel_frammento_non_nella_query(
        self, client, client_account, posta
    ):
        """Dopo `#` non arriva al server: niente token nel log di nginx."""
        await client.post(FORGOT, json={"email": client_account.email})
        url = urlsplit(posta[0]["url"])
        assert url.query == ""
        assert url.fragment.startswith("token=")

    async def test_il_percorso_esiste_fra_le_rotte_del_frontend(self):
        """Il guasto vero: un link verso una pagina che il router non ha.

        `/booking` è la rotta madre e il figlio si scrive relativo, quindi
        si cerca `path="reset-password"` dentro il blocco di `/booking`.
        """
        if not APP_TSX.exists():
            pytest.skip("frontend non presente in questo checkout")
        sorgente = APP_TSX.read_text()
        madre, figlio = PERCORSO_RESET.rsplit("/", 1)
        blocco = sorgente[sorgente.index(f'path="{madre}"'):]
        blocco = blocco[:blocco.index("</Route>")]
        assert f'path="{figlio}"' in blocco, (
            f"{PERCORSO_RESET} non è fra le rotte di App.tsx: il link della mail "
            "porterebbe alla home"
        )

    async def test_indirizzo_sconosciuto_stessa_risposta_e_nessuna_mail(
        self, client, client_account, posta
    ):
        """Non deve dire a nessuno quali indirizzi hanno un account."""
        vero = await client.post(FORGOT, json={"email": client_account.email})
        falso = await client.post(FORGOT, json={"email": "nessuno@nsh-test.it"})
        assert falso.status_code == vero.status_code == 200
        assert falso.json() == vero.json()
        assert len(posta) == 1


class TestDalLinkAlLogin:
    async def test_percorso_completo(self, client, client_account, posta):
        await client.post(FORGOT, json={"email": client_account.email})
        token = _token(posta[0]["url"])

        resp = await client.post(RESET, json={"token": token, "new_password": NUOVA})
        assert resp.status_code == 200, resp.text

        entra = await client.post(LOGIN, json={"email": client_account.email, "password": NUOVA})
        assert entra.status_code == 200, entra.text
        assert entra.json()["access_token"]

        vecchia = await client.post(
            LOGIN, json={"email": client_account.email, "password": CLIENT_PASSWORD}
        )
        assert vecchia.status_code == 401

    async def test_il_link_vale_una_volta_sola(self, client, client_account, posta):
        await client.post(FORGOT, json={"email": client_account.email})
        token = _token(posta[0]["url"])
        await client.post(RESET, json={"token": token, "new_password": NUOVA})

        di_nuovo = await client.post(
            RESET, json={"token": token, "new_password": "un-altra-ancora-lunga"}
        )
        assert di_nuovo.status_code == 400

    async def test_una_nuova_richiesta_annulla_il_link_precedente(
        self, client, client_account, posta
    ):
        await client.post(FORGOT, json={"email": client_account.email})
        await client.post(FORGOT, json={"email": client_account.email})
        primo, secondo = _token(posta[0]["url"]), _token(posta[1]["url"])
        assert primo != secondo

        assert (await client.post(RESET, json={"token": primo, "new_password": NUOVA})).status_code == 400
        assert (await client.post(RESET, json={"token": secondo, "new_password": NUOVA})).status_code == 200

    async def test_link_scaduto(self, client, db, client_account, posta):
        await client.post(FORGOT, json={"email": client_account.email})
        token = _token(posta[0]["url"])

        account = (await db.execute(
            select(ClientAccount).where(ClientAccount.id == client_account.id)
        )).scalar_one()
        account.reset_token_expires = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()

        resp = await client.post(RESET, json={"token": token, "new_password": NUOVA})
        assert resp.status_code == 400
        assert "scadut" in resp.json()["detail"].lower()

    async def test_password_troppo_corta(self, client, client_account, posta):
        await client.post(FORGOT, json={"email": client_account.email})
        token = _token(posta[0]["url"])
        resp = await client.post(RESET, json={"token": token, "new_password": "corta"})
        assert resp.status_code == 422

        # Il link resta buono: la cliente corregge e riprova.
        assert (await client.post(RESET, json={"token": token, "new_password": NUOVA})).status_code == 200
