"""
Phone numbers are canonicalised to E.164 on the way in.

The integration tests carry the real weight: a client the salon typed in by
hand and the same person registering online must end up as ONE record. Before
normalisation the two spellings of the same number did not compare equal, so
registration created a second client and split the appointment history.
"""
import pytest
from sqlalchemy import select

from app.models.client import Client
from app.utils.phone import InvalidPhoneNumber, to_e164
from tests.conftest import auth

GOOD_PASSWORD = "una-password-lunga-2026"


class TestToE164:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Italian mobile, the shapes people actually type
            ("3332876794", "+393332876794"),
            ("333 287 6794", "+393332876794"),
            ("333-287-6794", "+393332876794"),
            ("+39 333 287 6794", "+393332876794"),
            ("+393332876794", "+393332876794"),
            ("393332876794", "+393332876794"),
            ("00393332876794", "+393332876794"),
            ("0039 333 287 6794", "+393332876794"),
            # Landline keeps its trunk zero — +39 081 5551234
            ("081 5551234", "+390815551234"),
            # A mobile whose own prefix starts 393 is not a country code
            ("3932876794", "+393932876794"),
            # Already-international foreign numbers pass through untouched
            ("+44 20 7946 0958", "+442079460958"),
            ("+1 415 523 8886", "+14155238886"),
        ],
    )
    def test_normalises(self, raw, expected):
        assert to_e164(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_blank_means_no_number(self, raw):
        assert to_e164(raw) is None

    @pytest.mark.parametrize("raw", ["333", "n/a", "-", "boh"])
    def test_unusable_input_raises(self, raw):
        """A typo surfaces as an error rather than being stored unmatched."""
        with pytest.raises(InvalidPhoneNumber):
            to_e164(raw)

    def test_is_idempotent(self):
        once = to_e164("333 287 6794")
        assert to_e164(once) == once


class TestAdminEntry:
    async def test_local_format_is_stored_as_e164(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/clients",
            headers=auth(admin_tokens),
            json={"first_name": "Maria", "last_name": "Rossi", "phone": "333 287 6794"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["phone"] == "+393332876794"

    async def test_update_normalises_too(self, client, admin_tokens, other_client):
        resp = await client.put(
            f"/api/admin/clients/{other_client.id}",
            headers=auth(admin_tokens),
            json={"phone": "339 758 2243"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["phone"] == "+393397582243"

    async def test_client_without_a_phone_is_allowed(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/clients",
            headers=auth(admin_tokens),
            json={"first_name": "Senza", "last_name": "Telefono"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["phone"] is None

    async def test_typo_is_rejected(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/clients",
            headers=auth(admin_tokens),
            json={"first_name": "Errore", "last_name": "Digitazione", "phone": "333"},
        )
        assert resp.status_code == 422


class TestRegistrationLinksInsteadOfDuplicating:
    """The reason this normalisation exists."""

    async def test_same_person_different_spelling_is_one_record(
        self, client, db, admin_tokens
    ):
        created = await client.post(
            "/api/admin/clients",
            headers=auth(admin_tokens),
            json={"first_name": "Maria", "last_name": "Rossi", "phone": "333 287 6794"},
        )
        assert created.status_code == 201
        client_id = created.json()["id"]

        # Same person signs up online, typing the number the other way round.
        resp = await client.post(
            "/api/public/auth/register",
            json={
                "first_name": "Maria",
                "last_name": "Rossi",
                "phone": "+39 333 287 6794",
                "email": "maria.rossi@nsh-test.it",
                "password": GOOD_PASSWORD,
                "birth_date": "1990-05-12",
            },
        )
        assert resp.status_code == 201, resp.text

        rows = (await db.execute(
            select(Client).where(Client.phone == "+393332876794")
        )).scalars().all()
        assert len(rows) == 1, "la registrazione ha duplicato il cliente"
        assert rows[0].id == client_id
        assert rows[0].account_id is not None, "account non collegato all'anagrafica"

    async def test_registration_stores_e164(self, client, db):
        resp = await client.post(
            "/api/public/auth/register",
            json={
                "first_name": "Nuova",
                "last_name": "Cliente",
                "phone": "334 111 2233",
                "email": "nuova.cliente@nsh-test.it",
                "password": GOOD_PASSWORD,
                "birth_date": "1988-11-03",
            },
        )
        assert resp.status_code == 201, resp.text

        row = (await db.execute(
            select(Client).where(Client.email == "nuova.cliente@nsh-test.it")
        )).scalar_one()
        assert row.phone == "+393341112233"

    async def test_registration_rejects_an_unusable_phone(self, client):
        resp = await client.post(
            "/api/public/auth/register",
            json={
                "first_name": "Errore",
                "last_name": "Digitazione",
                "phone": "333",
                "email": "errore@nsh-test.it",
                "password": GOOD_PASSWORD,
            },
        )
        assert resp.status_code == 422
