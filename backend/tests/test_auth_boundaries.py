"""
Auth boundary tests.

These are regression tests for a real privilege-escalation bug: staff and client
tokens are signed with the same key but their `sub` claim indexes different
tables (users vs client_accounts). Before the fix, a client token whose account
id collided with a staff user id authenticated as that user — and with seeded
data both ids were 1, so any portal client acted as the admin.

If any test here fails, treat it as a security regression, not a flaky test.
"""
import pytest

from app.utils.auth import create_access_token
from tests.conftest import ADMIN_PASSWORD, CLIENT_PASSWORD, auth

# Endpoints that must never answer to a client token.
STAFF_ENDPOINTS = [
    "/api/admin/auth/me",
    "/api/admin/appointments",
    "/api/admin/clients",
    "/api/admin/services",
    "/api/admin/collaborators",
]

ADMIN_ONLY_ENDPOINTS = [
    "/api/admin/dashboard/stats?period=today",
    "/api/admin/expenses",
    "/api/admin/payments",
    "/api/admin/settings/booking",
    "/api/admin/waitlist",
]


class TestClientTokenCannotReachStaffApi:
    @pytest.mark.parametrize("path", STAFF_ENDPOINTS)
    async def test_client_access_token_rejected(self, client, client_tokens, path):
        resp = await client.get(path, headers=auth(client_tokens))
        assert resp.status_code == 401, (
            f"{path} accepted a client token ({resp.status_code}) — privilege escalation"
        )

    @pytest.mark.parametrize("path", ADMIN_ONLY_ENDPOINTS)
    async def test_client_token_rejected_on_admin_only(self, client, client_tokens, path):
        resp = await client.get(path, headers=auth(client_tokens))
        assert resp.status_code == 401, f"{path} accepted a client token ({resp.status_code})"

    async def test_colliding_ids_do_not_grant_admin(
        self, client, db, admin_user, client_account
    ):
        """
        The exact production shape of the bug: same numeric id in both tables.

        The fixtures create admin_user and client_account independently, so this
        asserts the ids really do collide (otherwise the test proves nothing)
        before checking that the client token still cannot pass as the admin.
        """
        assert admin_user.id == client_account.id == 1, (
            "expected colliding ids for this regression test"
        )

        tokens = (await client.post(
            "/api/public/auth/login",
            json={"email": client_account.email, "password": CLIENT_PASSWORD},
        )).json()

        resp = await client.get("/api/admin/auth/me", headers=auth(tokens))
        assert resp.status_code == 401
        # Belt and braces: the admin's email must not leak even on a 200.
        assert admin_user.email not in resp.text


class TestRefreshTokenBoundaries:
    async def test_client_refresh_cannot_mint_staff_token(self, client, client_tokens):
        """
        The worse half of the bug: /admin/auth/refresh took any token carrying
        `refresh: true` and returned a genuine staff access token for that id.
        """
        resp = await client.post(
            "/api/admin/auth/refresh",
            json={"refresh_token": client_tokens["refresh_token"]},
        )
        assert resp.status_code == 401, "client refresh token was exchanged for a staff token"

    async def test_staff_refresh_still_works(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/auth/refresh",
            json={"refresh_token": admin_tokens["refresh_token"]},
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"]

    async def test_refresh_token_not_accepted_as_access_token(self, client, admin_tokens):
        resp = await client.get(
            "/api/admin/auth/me",
            headers={"Authorization": f"Bearer {admin_tokens['refresh_token']}"},
        )
        assert resp.status_code == 401

    async def test_client_refresh_not_accepted_as_client_access(self, client, client_tokens):
        resp = await client.get(
            "/api/public/appointments",
            headers={"Authorization": f"Bearer {client_tokens['refresh_token']}"},
        )
        assert resp.status_code == 401


class TestForgedAndMalformedTokens:
    async def test_token_signed_with_wrong_key_rejected(self, client, admin_user):
        from jose import jwt

        forged = jwt.encode(
            {"sub": str(admin_user.id), "role": "admin", "exp": 9999999999},
            "not-the-real-secret",
            algorithm="HS256",
        )
        resp = await client.get("/api/admin/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert resp.status_code == 401

    async def test_missing_token_rejected(self, client):
        resp = await client.get("/api/admin/auth/me")
        assert resp.status_code in (401, 403)

    async def test_unknown_user_id_rejected(self, client):
        """A validly signed token for a user that does not exist must not pass."""
        token = create_access_token(999999, {"role": "admin"})
        resp = await client.get("/api/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    async def test_client_type_claim_cannot_be_dropped_to_reach_staff_api(
        self, client, admin_user, client_account
    ):
        """
        A client cannot forge a staff token by omitting `type` — that requires
        the signing key, which they do not have. Signed here only to document
        that the id alone is not authorisation; the guard is the signature.
        """
        assert admin_user.id == client_account.id
        # Same id, no `type` claim, but signed with the real key: this is what an
        # attacker cannot produce. It legitimately succeeds, which is why the
        # `type` check on client-issued tokens is the actual control.
        token = create_access_token(client_account.id, {"role": "admin"})
        resp = await client.get("/api/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestDeactivatedAccounts:
    async def test_deactivated_staff_cannot_log_in(self, client, db, admin_user):
        admin_user.is_active = False
        await db.commit()
        resp = await client.post(
            "/api/admin/auth/login",
            json={"email": admin_user.email, "password": ADMIN_PASSWORD},
        )
        assert resp.status_code == 403

    async def test_deactivated_staff_token_stops_working(self, client, db, admin_user, admin_tokens):
        """An already-issued token must stop working once the account is disabled."""
        admin_user.is_active = False
        await db.commit()
        resp = await client.get("/api/admin/auth/me", headers=auth(admin_tokens))
        assert resp.status_code == 401

    async def test_deactivated_client_token_stops_working(
        self, client, db, client_account, client_tokens
    ):
        client_account.is_active = False
        await db.commit()
        resp = await client.get("/api/public/appointments", headers=auth(client_tokens))
        assert resp.status_code == 401


class TestClientDataIsolation:
    async def test_client_sees_only_own_appointments(
        self, client, db, client_account, other_client, collaborator, service, client_tokens
    ):
        from datetime import datetime, timedelta, timezone

        from app.models.appointment import (
            Appointment, AppointmentOrigin, AppointmentService, AppointmentStatus,
        )
        from sqlalchemy import select

        from app.models.client import Client as ClientModel

        own = (await db.execute(
            select(ClientModel).where(ClientModel.account_id == client_account.id)
        )).scalar_one()

        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=3)
        for owner in (own, other_client):
            appt = Appointment(
                client_id=owner.id,
                collaborator_id=collaborator.id,
                start_time=start,
                end_time=start + timedelta(hours=1),
                status=AppointmentStatus.confirmed,
                origin=AppointmentOrigin.salon,
            )
            db.add(appt)
            await db.flush()
            db.add(AppointmentService(
                appointment_id=appt.id, service_id=service.id, price_snapshot=30.0,
            ))
            start += timedelta(hours=2)
        await db.commit()

        resp = await client.get("/api/public/appointments", headers=auth(client_tokens))
        assert resp.status_code == 200
        returned = resp.json()
        assert len(returned) == 1, "client saw another client's appointments"
        assert all(a["client_id"] == own.id for a in returned)
