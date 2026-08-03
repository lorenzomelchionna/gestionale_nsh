"""
Permission matrix.

This is the coherence guard: EXPECTED_GUARDS pins the auth level of every route
in the app. Adding, removing or re-guarding a route makes this fail until the
map is updated deliberately — so an endpoint can never quietly ship without an
auth decision, which is how the escalation bug reached production.

Guard levels:
  admin  → Depends(require_admin)       staff with role=admin only
  staff  → Depends(get_current_user)    admin or collaborator
  client → Depends(get_current_client)  portal account
  public → no authentication
"""
import pytest
from fastapi.routing import APIRoute

from app.dependencies import get_current_client, get_current_user, require_admin
from app.main import app
from tests.conftest import auth

GUARD_BY_DEPENDENCY = {
    require_admin: "admin",
    get_current_user: "staff",
    get_current_client: "client",
}

EXPECTED_GUARDS = {
    ("POST", "/api/admin/absences"): "admin",
    ("DELETE", "/api/admin/absences/{absence_id}"): "admin",
    ("GET", "/api/admin/absences/{collaborator_id}"): "staff",
    ("GET", "/api/admin/appointments"): "staff",
    ("POST", "/api/admin/appointments"): "staff",
    ("GET", "/api/admin/appointments/pending"): "staff",
    ("DELETE", "/api/admin/appointments/{appointment_id}"): "staff",
    ("GET", "/api/admin/appointments/{appointment_id}"): "staff",
    ("PUT", "/api/admin/appointments/{appointment_id}"): "staff",
    ("POST", "/api/admin/appointments/{appointment_id}/cancel"): "staff",
    ("POST", "/api/admin/appointments/{appointment_id}/complete"): "staff",
    ("POST", "/api/admin/appointments/{appointment_id}/confirm"): "staff",
    ("POST", "/api/admin/appointments/{appointment_id}/reject"): "staff",
    ("POST", "/api/admin/appointments/{appointment_id}/reschedule"): "staff",
    # The shared sign-in screen. Public by necessity — it is where a session
    # begins — and it may return either a staff or a client token, so what it
    # hands out matters more than what guards it. See tests/test_unified_login.
    ("POST", "/api/auth/login"): "public",
    ("POST", "/api/admin/auth/login"): "public",
    ("GET", "/api/admin/auth/me"): "staff",
    ("POST", "/api/admin/auth/refresh"): "public",
    ("GET", "/api/admin/availability"): "staff",
    # Chat: staff, not admin-only — answering clients is day-to-day work for
    # collaborators too, and the inbox exposes no financial data.
    ("GET", "/api/admin/chat/conversations"): "staff",
    ("GET", "/api/admin/chat/conversations/{conversation_id}"): "staff",
    ("POST", "/api/admin/chat/conversations/{conversation_id}/reply"): "staff",
    ("PATCH", "/api/admin/chat/conversations/{conversation_id}/archive"): "staff",
    ("GET", "/api/admin/chat/unread-count"): "staff",
    ("GET", "/api/admin/chat/status"): "staff",
    ("GET", "/api/admin/clients"): "staff",
    ("POST", "/api/admin/clients"): "admin",
    ("DELETE", "/api/admin/clients/{client_id}"): "admin",
    ("GET", "/api/admin/clients/{client_id}"): "staff",
    ("PUT", "/api/admin/clients/{client_id}"): "admin",
    ("GET", "/api/admin/clients/{client_id}/appointments"): "staff",
    ("GET", "/api/admin/collaborators"): "staff",
    ("POST", "/api/admin/collaborators"): "admin",
    ("DELETE", "/api/admin/collaborators/{collaborator_id}"): "admin",
    ("GET", "/api/admin/collaborators/{collaborator_id}"): "staff",
    ("PUT", "/api/admin/collaborators/{collaborator_id}"): "admin",
    ("PUT", "/api/admin/collaborators/{collaborator_id}/schedule"): "admin",
    ("PUT", "/api/admin/collaborators/{collaborator_id}/services"): "admin",
    ("GET", "/api/admin/dashboard/revenue-chart"): "admin",
    ("GET", "/api/admin/dashboard/stats"): "admin",
    ("GET", "/api/admin/dashboard/yearly-chart"): "admin",
    ("GET", "/api/admin/expenses"): "admin",
    ("POST", "/api/admin/expenses"): "admin",
    ("DELETE", "/api/admin/expenses/{expense_id}"): "admin",
    ("PUT", "/api/admin/expenses/{expense_id}"): "admin",
    ("POST", "/api/admin/extra-days"): "admin",
    ("GET", "/api/admin/extra-days/{collaborator_id}"): "admin",
    ("DELETE", "/api/admin/extra-days/{extra_day_id}"): "admin",
    ("POST", "/api/admin/messaging/preview"): "admin",
    ("POST", "/api/admin/messaging/send"): "admin",
    ("GET", "/api/admin/payments"): "admin",
    ("POST", "/api/admin/payments"): "admin",
    ("GET", "/api/admin/products"): "staff",
    ("POST", "/api/admin/products"): "admin",
    ("POST", "/api/admin/products/movements"): "admin",
    ("GET", "/api/admin/products/{product_id}"): "staff",
    ("PUT", "/api/admin/products/{product_id}"): "admin",
    ("PUT", "/api/admin/products/{product_id}/image"): "admin",
    ("DELETE", "/api/admin/products/{product_id}/image"): "admin",
    ("GET", "/api/admin/services"): "staff",
    ("POST", "/api/admin/services"): "admin",
    ("DELETE", "/api/admin/services/{service_id}"): "admin",
    ("GET", "/api/admin/services/{service_id}"): "staff",
    ("PUT", "/api/admin/services/{service_id}"): "admin",
    # Team: admin-only, except changing your own password which any staff does.
    ("GET", "/api/admin/team"): "admin",
    ("POST", "/api/admin/team"): "admin",
    ("PUT", "/api/admin/team/{user_id}"): "admin",
    ("POST", "/api/admin/team/{user_id}/reset-password"): "admin",
    ("POST", "/api/admin/team/me/password"): "staff",
    ("GET", "/api/admin/settings/booking"): "admin",
    ("PUT", "/api/admin/settings/booking"): "admin",
    ("GET", "/api/admin/waitlist"): "admin",
    ("POST", "/api/admin/waitlist"): "admin",
    ("DELETE", "/api/admin/waitlist/{entry_id}"): "admin",
    ("PATCH", "/api/admin/waitlist/{entry_id}/fulfil"): "admin",
    ("POST", "/api/admin/waitlist/{entry_id}/notify"): "admin",
    ("GET", "/api/public/appointments"): "client",
    ("POST", "/api/public/appointments"): "client",
    ("POST", "/api/public/appointments/{appointment_id}/accept-alternative"): "client",
    ("POST", "/api/public/appointments/{appointment_id}/cancel"): "client",
    ("POST", "/api/public/appointments/{appointment_id}/reject-alternative"): "client",
    ("POST", "/api/public/auth/forgot-password"): "public",
    ("POST", "/api/public/auth/login"): "public",
    ("POST", "/api/public/auth/register"): "public",
    # Both public by necessity: they are how someone who cannot yet log in
    # proves the address is theirs. The control is the emailed code.
    ("POST", "/api/public/auth/verify-email"): "public",
    ("POST", "/api/public/auth/resend-code"): "public",
    ("POST", "/api/public/auth/reset-password"): "public",
    ("GET", "/api/public/availability"): "public",
    ("GET", "/api/public/availability/calendar"): "public",
    # Unauthenticated by necessity — Twilio cannot hold our credentials. The
    # control is the Twilio signature check inside the handler, not a dependency.
    ("POST", "/api/public/whatsapp/webhook"): "public",
    ("GET", "/api/public/collaborators"): "public",
    # Unauthenticated by necessity: an <img> tag cannot send an Authorization
    # header. The control is the 32-byte token in the path — unguessable and
    # non-sequential, so the catalogue cannot be enumerated through it.
    ("GET", "/api/public/product-images/{token}"): "public",
    ("GET", "/api/public/services"): "public",
    ("GET", "/api/public/waitlist"): "client",
    ("POST", "/api/public/waitlist"): "client",
    ("DELETE", "/api/public/waitlist/{entry_id}"): "client",
    ("GET", "/health"): "public",
}


def detect_guard(route: APIRoute) -> str:
    """Walk the dependency tree and report which auth dependency guards the route."""
    seen: set[int] = set()
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        if dep.call in GUARD_BY_DEPENDENCY:
            return GUARD_BY_DEPENDENCY[dep.call]
        stack.extend(dep.dependencies)
    return "public"


def actual_guards() -> dict[tuple[str, str], str]:
    found = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            found[(method, route.path)] = detect_guard(route)
    return found


class TestRouteInventory:
    def test_no_unclassified_routes(self):
        """A new endpoint must be added to EXPECTED_GUARDS with a deliberate level."""
        new = sorted(set(actual_guards()) - set(EXPECTED_GUARDS))
        assert not new, (
            "Rotte nuove senza livello di permesso dichiarato — aggiungile a "
            f"EXPECTED_GUARDS scegliendo admin/staff/client/public: {new}"
        )

    def test_no_stale_expectations(self):
        removed = sorted(set(EXPECTED_GUARDS) - set(actual_guards()))
        assert not removed, f"Rotte rimosse ma ancora in EXPECTED_GUARDS: {removed}"

    @pytest.mark.parametrize(
        ("endpoint", "expected"),
        sorted(EXPECTED_GUARDS.items()),
        ids=lambda v: f"{v[0]} {v[1]}" if isinstance(v, tuple) else str(v),
    )
    def test_guard_unchanged(self, endpoint, expected):
        found = actual_guards()
        assert found[endpoint] == expected, (
            f"{endpoint[0]} {endpoint[1]}: atteso '{expected}', trovato '{found[endpoint]}'"
        )

    def test_every_admin_route_is_authenticated(self):
        """Nothing under /api/admin may be reachable without a token, except login/refresh."""
        allowed_public = {
            ("POST", "/api/admin/auth/login"),
            ("POST", "/api/admin/auth/refresh"),
        }
        offenders = [
            ep for ep, guard in actual_guards().items()
            if ep[1].startswith("/api/admin") and guard == "public" and ep not in allowed_public
        ]
        assert not offenders, f"Endpoint admin senza autenticazione: {offenders}"


class TestCollaboratorIsDeniedAdminRoutes:
    """Runtime confirmation that the static map matches real behaviour."""

    ADMIN_GETS = [
        "/api/admin/dashboard/stats?period=today",
        "/api/admin/expenses",
        "/api/admin/payments",
        "/api/admin/settings/booking",
        "/api/admin/waitlist",
    ]

    @pytest.mark.parametrize("path", ADMIN_GETS)
    async def test_collaborator_forbidden(self, client, collab_tokens, path):
        resp = await client.get(path, headers=auth(collab_tokens))
        assert resp.status_code == 403, f"{path} raggiungibile da un collaboratore"

    @pytest.mark.parametrize("path", ADMIN_GETS)
    async def test_admin_allowed(self, client, admin_tokens, booking_config, path):
        resp = await client.get(path, headers=auth(admin_tokens))
        assert resp.status_code == 200, f"{path} negato all'admin: {resp.status_code}"

    async def test_collaborator_can_read_shared_data(self, client, collab_tokens):
        """The collaborator role is not locked out of day-to-day work."""
        for path in ("/api/admin/appointments", "/api/admin/clients", "/api/admin/services"):
            resp = await client.get(path, headers=auth(collab_tokens))
            assert resp.status_code == 200, f"{path} negato al collaboratore"

    async def test_collaborator_cannot_write_master_data(self, client, collab_tokens):
        resp = await client.post(
            "/api/admin/services",
            headers=auth(collab_tokens),
            json={
                "name": "Non permesso", "price": 10.0,
                "duration_slots": 1, "category": "Taglio",
            },
        )
        assert resp.status_code == 403
