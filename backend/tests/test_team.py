"""
Staff account management.

The lockout invariants get the most attention: an admin who deactivates the last
admin, or demotes themselves, leaves the salon unable to reach its own
management area, and the only way back would be editing the database by hand.
"""
import pytest
from sqlalchemy import select

from app.models.collaborator import Collaborator
from app.models.user import User, UserRole
from tests.conftest import ADMIN_PASSWORD, COLLAB_PASSWORD, auth

GOOD_PASSWORD = "una-password-lunga-2026"


class TestCreation:
    async def test_admin_creates_a_collaborator_login(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": "nuovo@nsh-test.it", "password": GOOD_PASSWORD},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == "collaborator"
        assert resp.json()["is_active"] is True

    async def test_new_login_can_sign_in(self, client, admin_tokens):
        await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": "nuovo@nsh-test.it", "password": GOOD_PASSWORD},
        )
        resp = await client.post(
            "/api/admin/auth/login",
            json={"email": "nuovo@nsh-test.it", "password": GOOD_PASSWORD},
        )
        assert resp.status_code == 200

    async def test_login_can_be_linked_to_a_calendar_profile(
        self, client, db, admin_tokens, collaborator
    ):
        resp = await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={
                "email": "sofia.login@nsh-test.it",
                "password": GOOD_PASSWORD,
                "collaborator_id": collaborator.id,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["collaborator_id"] == collaborator.id
        assert collaborator.first_name in resp.json()["collaborator_name"]

        linked = (await db.execute(
            select(Collaborator).where(Collaborator.id == collaborator.id)
        )).scalar_one()
        assert linked.user_id == resp.json()["id"]

    async def test_duplicate_email_is_rejected(self, client, admin_tokens, admin_user):
        resp = await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": admin_user.email, "password": GOOD_PASSWORD},
        )
        assert resp.status_code == 400

    async def test_short_password_is_rejected(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": "corta@nsh-test.it", "password": "breve"},
        )
        assert resp.status_code == 422

    async def test_collaborator_cannot_create_logins(self, client, collab_tokens):
        resp = await client.post(
            "/api/admin/team",
            headers=auth(collab_tokens),
            json={"email": "abusivo@nsh-test.it", "password": GOOD_PASSWORD},
        )
        assert resp.status_code == 403

    async def test_profile_already_linked_is_rejected(
        self, client, db, admin_tokens, collaborator
    ):
        first = await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": "primo@nsh-test.it", "password": GOOD_PASSWORD,
                  "collaborator_id": collaborator.id},
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": "secondo@nsh-test.it", "password": GOOD_PASSWORD,
                  "collaborator_id": collaborator.id},
        )
        assert second.status_code == 400


class TestLockoutProtection:
    async def test_cannot_deactivate_the_last_admin(self, client, admin_tokens, admin_user):
        resp = await client.put(
            f"/api/admin/team/{admin_user.id}",
            headers=auth(admin_tokens),
            json={"is_active": False},
        )
        assert resp.status_code == 400
        assert "disattivare" in resp.json()["detail"].lower()

    async def test_cannot_demote_yourself(self, client, admin_tokens, admin_user):
        resp = await client.put(
            f"/api/admin/team/{admin_user.id}",
            headers=auth(admin_tokens),
            json={"role": "collaborator"},
        )
        assert resp.status_code == 400

    async def test_second_admin_can_be_demoted(self, client, db, admin_tokens):
        """With another admin in place the invariant no longer blocks the change."""
        created = await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": "secondo.admin@nsh-test.it", "password": GOOD_PASSWORD,
                  "role": "admin"},
        )
        assert created.status_code == 201
        other_id = created.json()["id"]

        resp = await client.put(
            f"/api/admin/team/{other_id}",
            headers=auth(admin_tokens),
            json={"role": "collaborator"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "collaborator"

    async def test_collaborator_can_be_deactivated(self, client, admin_tokens, collaborator_user):
        resp = await client.put(
            f"/api/admin/team/{collaborator_user.id}",
            headers=auth(admin_tokens),
            json={"is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_deactivated_member_cannot_log_in(
        self, client, admin_tokens, collaborator_user
    ):
        await client.put(
            f"/api/admin/team/{collaborator_user.id}",
            headers=auth(admin_tokens),
            json={"is_active": False},
        )
        resp = await client.post(
            "/api/admin/auth/login",
            json={"email": collaborator_user.email, "password": COLLAB_PASSWORD},
        )
        assert resp.status_code == 403


class TestOwnPasswordChange:
    async def test_staff_changes_their_own_password(self, client, collab_tokens, collaborator_user):
        resp = await client.post(
            "/api/admin/team/me/password",
            headers=auth(collab_tokens),
            json={"current_password": COLLAB_PASSWORD, "new_password": GOOD_PASSWORD},
        )
        assert resp.status_code == 204

        old = await client.post(
            "/api/admin/auth/login",
            json={"email": collaborator_user.email, "password": COLLAB_PASSWORD},
        )
        assert old.status_code == 401

        new = await client.post(
            "/api/admin/auth/login",
            json={"email": collaborator_user.email, "password": GOOD_PASSWORD},
        )
        assert new.status_code == 200

    async def test_wrong_current_password_is_rejected(self, client, collab_tokens):
        resp = await client.post(
            "/api/admin/team/me/password",
            headers=auth(collab_tokens),
            json={"current_password": "sbagliata", "new_password": GOOD_PASSWORD},
        )
        assert resp.status_code == 400

    async def test_reusing_the_same_password_is_rejected(self, client, collab_tokens):
        resp = await client.post(
            "/api/admin/team/me/password",
            headers=auth(collab_tokens),
            json={"current_password": COLLAB_PASSWORD, "new_password": COLLAB_PASSWORD},
        )
        assert resp.status_code == 400

    async def test_short_new_password_is_rejected(self, client, collab_tokens):
        resp = await client.post(
            "/api/admin/team/me/password",
            headers=auth(collab_tokens),
            json={"current_password": COLLAB_PASSWORD, "new_password": "breve"},
        )
        assert resp.status_code == 422

    async def test_client_token_cannot_change_a_staff_password(self, client, client_tokens):
        resp = await client.post(
            "/api/admin/team/me/password",
            headers=auth(client_tokens),
            json={"current_password": "qualsiasi", "new_password": GOOD_PASSWORD},
        )
        assert resp.status_code == 401


class TestAdminReset:
    async def test_admin_resets_a_forgotten_password(
        self, client, admin_tokens, collaborator_user
    ):
        resp = await client.post(
            f"/api/admin/team/{collaborator_user.id}/reset-password",
            headers=auth(admin_tokens),
            json={"new_password": GOOD_PASSWORD},
        )
        assert resp.status_code == 204

        login = await client.post(
            "/api/admin/auth/login",
            json={"email": collaborator_user.email, "password": GOOD_PASSWORD},
        )
        assert login.status_code == 200

    async def test_collaborator_cannot_reset_someone_elses_password(
        self, client, collab_tokens, admin_user
    ):
        resp = await client.post(
            f"/api/admin/team/{admin_user.id}/reset-password",
            headers=auth(collab_tokens),
            json={"new_password": GOOD_PASSWORD},
        )
        assert resp.status_code == 403


class TestListing:
    async def test_listing_shows_the_linked_profile(
        self, client, db, admin_tokens, collaborator
    ):
        await client.post(
            "/api/admin/team",
            headers=auth(admin_tokens),
            json={"email": "collegato@nsh-test.it", "password": GOOD_PASSWORD,
                  "collaborator_id": collaborator.id},
        )
        resp = await client.get("/api/admin/team", headers=auth(admin_tokens))
        assert resp.status_code == 200

        linked = [u for u in resp.json() if u["email"] == "collegato@nsh-test.it"]
        assert len(linked) == 1
        assert linked[0]["collaborator_id"] == collaborator.id

    async def test_collaborator_cannot_list_the_team(self, client, collab_tokens):
        resp = await client.get("/api/admin/team", headers=auth(collab_tokens))
        assert resp.status_code == 403
