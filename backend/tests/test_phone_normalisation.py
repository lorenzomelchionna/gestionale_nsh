"""
Phone numbers are canonicalised to E.164 on the way in.

Two spellings of the same number have to compare equal, because the number is
how the salon finds a person: the WhatsApp inbox matches an incoming message to
a client by it, and the admin search looks it up.

Note what this normalisation is NO LONGER used for. Registration used to link a
new account to an existing client by matching the phone, and these tests
certified that behaviour — until it turned out to be the way a stranger could
take over a client's record just by knowing her mobile number. Linking now
happens after the email is verified and matches on the address alone; see
tests/test_registration_takeover.py.
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


class TestTheNumberStillMatchesAcrossSpellings:
    async def test_both_spellings_land_on_the_same_stored_value(
        self, client, db, admin_tokens
    ):
        """What the salon types by hand and what a client types online end up
        byte-identical, which is what makes any later lookup by number work."""
        created = await client.post(
            "/api/admin/clients",
            headers=auth(admin_tokens),
            json={"first_name": "Maria", "last_name": "Rossi", "phone": "333 287 6794"},
        )
        assert created.status_code == 201

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
        assert len(rows) == 2, "le due grafie non sono finite sullo stesso valore"

    async def test_a_matching_number_alone_does_not_hand_over_the_record(
        self, client, db, admin_tokens
    ):
        """Il duplicato sopra è voluto.

        Fondere le due schede sul solo numero significherebbe che chiunque
        conosca il cellulare di una cliente si prende la sua anagrafica. Finché
        il numero non viene verificato (OTP WhatsApp, previsto al go-live), due
        righe che il salone può unire a mano battono una riga unita per errore.
        """
        created = await client.post(
            "/api/admin/clients",
            headers=auth(admin_tokens),
            json={"first_name": "Maria", "last_name": "Rossi", "phone": "333 287 6794"},
        )
        client_id = created.json()["id"]

        await client.post(
            "/api/public/auth/register",
            json={
                "first_name": "Chiunque",
                "last_name": "Altro",
                "phone": "333 287 6794",
                "email": "estraneo@nsh-test.it",
                "password": GOOD_PASSWORD,
                "birth_date": "1990-05-12",
            },
        )

        del_salone = (await db.execute(
            select(Client).where(Client.id == client_id)
        )).scalar_one()
        assert del_salone.account_id is None

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
