"""
One sign-in screen for staff and clients.

The weight here is on what the shared endpoint hands out. Staff and clients are
separate tables with separate privileges, and the only thing keeping a client
token off the management area is the `type: client` marking. If this endpoint
ever issued an unmarked token to a client, that client would be an admin — the
escalation this codebase already had once, reintroduced through the front door.
"""
import pytest
from sqlalchemy import select

from app.models.client import ClientAccount
from app.models.user import User, UserRole
from app.utils.auth import hash_password
from tests.conftest import ADMIN_PASSWORD, CLIENT_PASSWORD, COLLAB_PASSWORD, auth

LOGIN = "/api/auth/login"
GOOD_PASSWORD = "una-password-lunga-2026"


class TestStaffSignIn:
    async def test_admin_signs_in_and_is_labelled_staff(self, client, admin_user):
        resp = await client.post(
            LOGIN, json={"email": admin_user.email, "password": ADMIN_PASSWORD}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["audience"] == "staff"
        assert body["role"] == "admin"

    async def test_collaborator_signs_in_as_staff(self, client, collaborator_user):
        resp = await client.post(
            LOGIN, json={"email": collaborator_user.email, "password": COLLAB_PASSWORD}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["audience"] == "staff"
        assert resp.json()["role"] == "collaborator"

    async def test_the_token_actually_opens_the_management_area(self, client, admin_user):
        resp = await client.post(
            LOGIN, json={"email": admin_user.email, "password": ADMIN_PASSWORD}
        )
        me = await client.get("/api/admin/auth/me", headers=auth(resp.json()))
        assert me.status_code == 200

    async def test_deactivated_staff_is_refused(self, client, db, collaborator_user):
        collaborator_user.is_active = False
        await db.commit()
        resp = await client.post(
            LOGIN, json={"email": collaborator_user.email, "password": COLLAB_PASSWORD}
        )
        assert resp.status_code == 403


class TestClientSignIn:
    async def test_client_signs_in_and_is_labelled_client(self, client, client_account):
        resp = await client.post(
            LOGIN, json={"email": client_account.email, "password": CLIENT_PASSWORD}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["audience"] == "client"
        assert resp.json().get("role") is None

    async def test_the_token_opens_the_portal(self, client, client_account):
        resp = await client.post(
            LOGIN, json={"email": client_account.email, "password": CLIENT_PASSWORD}
        )
        mine = await client.get("/api/public/appointments", headers=auth(resp.json()))
        assert mine.status_code == 200

    async def test_client_token_cannot_reach_the_management_area(self, client, client_account):
        """The whole point of the audience marking."""
        resp = await client.post(
            LOGIN, json={"email": client_account.email, "password": CLIENT_PASSWORD}
        )
        tokens = resp.json()

        for path in ("/api/admin/auth/me", "/api/admin/clients", "/api/admin/dashboard/stats"):
            blocked = await client.get(path, headers=auth(tokens))
            assert blocked.status_code == 401, f"{path} raggiungibile con un token cliente"

    async def test_client_refresh_token_cannot_become_a_staff_token(
        self, client, client_account
    ):
        resp = await client.post(
            LOGIN, json={"email": client_account.email, "password": CLIENT_PASSWORD}
        )
        swap = await client.post(
            "/api/admin/auth/refresh",
            json={"refresh_token": resp.json()["refresh_token"]},
        )
        assert swap.status_code == 401

    async def test_deactivated_client_is_refused(self, client, db, client_account):
        client_account.is_active = False
        await db.commit()
        resp = await client.post(
            LOGIN, json={"email": client_account.email, "password": CLIENT_PASSWORD}
        )
        assert resp.status_code == 403


class TestRejections:
    async def test_unknown_email(self, client):
        resp = await client.post(
            LOGIN, json={"email": "nessuno@nsh-test.it", "password": GOOD_PASSWORD}
        )
        assert resp.status_code == 401

    async def test_wrong_password(self, client, admin_user):
        resp = await client.post(
            LOGIN, json={"email": admin_user.email, "password": "sbagliata-del-tutto"}
        )
        assert resp.status_code == 401

    async def test_unknown_email_and_wrong_password_look_the_same(
        self, client, admin_user
    ):
        """The response must not reveal who has an account."""
        unknown = await client.post(
            LOGIN, json={"email": "nessuno@nsh-test.it", "password": GOOD_PASSWORD}
        )
        wrong = await client.post(
            LOGIN, json={"email": admin_user.email, "password": "sbagliata-del-tutto"}
        )
        assert unknown.status_code == wrong.status_code
        assert unknown.json() == wrong.json()


class TestOneAddressOneAccount:
    """
    Staff and clients sign in from the same box, so an address that exists in
    both tables would make the login guess. Both creation paths refuse it.
    """

    async def test_staff_address_cannot_be_reused_for_a_portal_account(
        self, client, admin_user
    ):
        resp = await client.post(
            "/api/public/auth/register",
            json={
                "first_name": "Furba", "last_name": "Test",
                "phone": "3351112233",
                "email": admin_user.email,
                "password": GOOD_PASSWORD,
                "birth_date": "1992-02-20",
            },
        )
        assert resp.status_code == 400
        assert "staff" in resp.json()["detail"].lower()

    async def test_portal_address_cannot_be_reused_for_a_staff_login(
        self, client, admin_tokens, client_account
    ):
        resp = await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": client_account.email, "password": GOOD_PASSWORD},
        )
        assert resp.status_code == 400
        assert "cliente" in resp.json()["detail"].lower()

    async def test_staff_wins_when_both_already_exist(self, client, db):
        """
        Rows written before the guard existed can still overlap. The salon's own
        account has to win, otherwise an admin could be shadowed by a client
        account carrying the same address.
        """
        shared = "doppia@nsh-test.it"
        db.add(User(
            email=shared, password_hash=await hash_password(GOOD_PASSWORD),
            role=UserRole.admin, is_active=True,
        ))
        db.add(ClientAccount(
            email=shared, password_hash=await hash_password(GOOD_PASSWORD), is_active=True,
        ))
        await db.commit()

        resp = await client.post(LOGIN, json={"email": shared, "password": GOOD_PASSWORD})
        assert resp.status_code == 200
        assert resp.json()["audience"] == "staff"
