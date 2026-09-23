"""Una cliente al banco può non lasciare né email né telefono.

Dal portale servono entrambi — chi si registra da sola deve dimostrare di
possedere l'indirizzo e il numero, e senza non c'è niente da verificare. Dal
gestionale no: la cliente è davanti al banco, e pretendere un'email da chi non
ne ha significa inventarsela, che è peggio di lasciarla vuota.

Il file copre anche il completamento in un secondo momento, perché una scheda
che nasce senza contatti è utile solo se i contatti si possono aggiungere
quando arrivano.
"""
import pytest

from app.models.client import Client

from tests.conftest import auth


@pytest.mark.asyncio
class TestCreazioneDalGestionale:
    async def test_senza_email_ma_col_telefono(self, client, admin_tokens):
        r = await client.post(
            "/api/admin/clients",
            json={"first_name": "Rosa", "last_name": "Esposito", "phone": "3331234567"},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 201, r.text
        assert r.json()["email"] is None
        assert r.json()["phone"] == "+393331234567"

    async def test_senza_niente(self, client, admin_tokens):
        """Il caso che conta: la cliente di passaggio che lascia solo il nome."""
        r = await client.post(
            "/api/admin/clients",
            json={"first_name": "Anna", "last_name": "Verdi"},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 201, r.text
        assert r.json()["email"] is None
        assert r.json()["phone"] is None

    async def test_il_nome_resta_obbligatorio(self, client, admin_tokens):
        """Senza contatti la scheda regge, senza nome no: non la ritrova nessuno."""
        r = await client.post(
            "/api/admin/clients",
            json={"phone": "3331234567"},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 422

    async def test_email_scritta_male_resta_rifiutata(self, client, admin_tokens):
        """Facoltativa non vuol dire «qualunque cosa»: vuota sì, sbagliata no."""
        r = await client.post(
            "/api/admin/clients",
            json={"first_name": "Lia", "last_name": "Neri", "email": "chiocciola-assente"},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 422


@pytest.mark.asyncio
class TestCompletamentoSuccessivo:
    async def test_i_contatti_si_aggiungono_dopo(self, client, admin_tokens, db):
        creata = await client.post(
            "/api/admin/clients",
            json={"first_name": "Anna", "last_name": "Verdi"},
            headers=auth(admin_tokens),
        )
        cid = creata.json()["id"]

        r = await client.put(
            f"/api/admin/clients/{cid}",
            json={"email": "anna.verdi@example.com", "phone": "3339876543"},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "anna.verdi@example.com"
        assert r.json()["phone"] == "+393339876543"

        # Il nome non deve essere stato azzerato dall'aggiornamento parziale:
        # `ClientUpdate` ha i due campi facoltativi, quindi un PUT che non li
        # nomina potrebbe scriverci sopra `None` se non fosse per
        # `exclude_unset`.
        assert r.json()["first_name"] == "Anna"
        assert r.json()["last_name"] == "Verdi"

    async def test_un_aggiornamento_parziale_non_cancella_l_altro_contatto(
        self, client, admin_tokens
    ):
        """Aggiungere l'email non deve portar via il telefono già sulla scheda."""
        creata = await client.post(
            "/api/admin/clients",
            json={"first_name": "Rosa", "last_name": "Esposito", "phone": "3331234567"},
            headers=auth(admin_tokens),
        )
        cid = creata.json()["id"]

        r = await client.put(
            f"/api/admin/clients/{cid}",
            json={"email": "rosa@example.com"},
            headers=auth(admin_tokens),
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "rosa@example.com"
        assert r.json()["phone"] == "+393331234567"


@pytest.mark.asyncio
class TestIlPortaleInveceLiPretende:
    """La contropartita: da fuori i due campi restano obbligatori."""

    async def test_registrazione_senza_telefono_rifiutata(self, client):
        r = await client.post(
            "/api/public/auth/register",
            json={
                "first_name": "Anna", "last_name": "Verdi",
                "email": "anna@example.com", "password": "password-lunga",
                "birth_date": "1990-05-01",
            },
        )
        assert r.status_code == 422

    async def test_registrazione_senza_email_rifiutata(self, client):
        r = await client.post(
            "/api/public/auth/register",
            json={
                "first_name": "Anna", "last_name": "Verdi",
                "phone": "3331234567", "password": "password-lunga",
                "birth_date": "1990-05-01",
            },
        )
        assert r.status_code == 422


@pytest.mark.asyncio
class TestAccessoAlPortale:
    async def test_senza_email_non_si_puo_dare_un_accesso(self, client, admin_tokens):
        """L'email non è un dettaglio anagrafico: è la chiave con cui si entra.

        Meglio un rifiuto che spiega, che un account creato su un indirizzo
        vuoto e inutilizzabile.
        """
        creata = await client.post(
            "/api/admin/clients",
            json={"first_name": "Anna", "last_name": "Verdi"},
            headers=auth(admin_tokens),
        )
        cid = creata.json()["id"]

        r = await client.post(
            f"/api/admin/clients/{cid}/portal-account",
            headers=auth(admin_tokens),
        )
        assert r.status_code == 400
        assert "email" in r.json()["detail"].lower()
