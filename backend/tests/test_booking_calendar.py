"""
Per-day availability for the client calendar.

The calendar greys out days before the client taps one, so it needs the whole
visible month in a single answer. It also has to agree with the per-day
endpoint: a day the calendar shows as free must actually return those slots,
otherwise the client picks a day and finds nothing.
"""
from datetime import date, timedelta

import pytest

CALENDAR = "/api/public/availability/calendar"


def _params(service_id, collaborator_id, start, end):
    return {
        "service_id": service_id,
        "collaborator_id": collaborator_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


class TestCalendar:
    async def test_returns_one_entry_per_day(
        self, client, booking_config, collaborator, service
    ):
        start = date.today()
        end = start + timedelta(days=6)
        resp = await client.get(
            CALENDAR, params=_params(service.id, collaborator.id, start, end)
        )
        assert resp.status_code == 200, resp.text
        days = resp.json()
        assert len(days) == 7
        assert days[0]["date"] == start.isoformat()
        assert days[-1]["date"] == end.isoformat()

    async def test_a_working_day_reports_slots(
        self, client, booking_config, collaborator, service
    ):
        """The fixture collaborator works Mon–Sat, so a weekday is open."""
        start = date.today()
        end = start + timedelta(days=6)
        resp = await client.get(
            CALENDAR, params=_params(service.id, collaborator.id, start, end)
        )
        assert any(d["slots"] > 0 for d in resp.json()), "nessun giorno disponibile in una settimana"

    async def test_closed_day_reports_zero(
        self, client, booking_config, collaborator, service
    ):
        """Sunday is not worked, so it must come back empty rather than absent."""
        start = date.today()
        end = start + timedelta(days=13)
        resp = await client.get(
            CALENDAR, params=_params(service.id, collaborator.id, start, end)
        )
        sundays = [
            d for d in resp.json()
            if date.fromisoformat(d["date"]).weekday() == 6
        ]
        assert sundays, "nessuna domenica nell'intervallo di due settimane"
        assert all(d["slots"] == 0 for d in sundays)

    async def test_agrees_with_the_per_day_endpoint(
        self, client, booking_config, collaborator, service
    ):
        """A day the calendar calls free must really hand over that many slots."""
        start = date.today()
        end = start + timedelta(days=6)
        cal = await client.get(
            CALENDAR, params=_params(service.id, collaborator.id, start, end)
        )
        free_day = next(d for d in cal.json() if d["slots"] > 0)

        per_day = await client.get(
            "/api/public/availability",
            params={
                "service_id": service.id,
                "collaborator_id": collaborator.id,
                "target_date": free_day["date"],
            },
        )
        assert per_day.status_code == 200
        assert len(per_day.json()) == free_day["slots"]

    async def test_past_days_are_empty(
        self, client, booking_config, collaborator, service
    ):
        start = date.today() - timedelta(days=3)
        resp = await client.get(
            CALENDAR, params=_params(service.id, collaborator.id, start, date.today())
        )
        past = [d for d in resp.json() if date.fromisoformat(d["date"]) < date.today()]
        assert past and all(d["slots"] == 0 for d in past)


class TestCalendarRejections:
    async def test_reversed_range(self, client, booking_config, collaborator, service):
        today = date.today()
        resp = await client.get(
            CALENDAR,
            params=_params(service.id, collaborator.id, today, today - timedelta(days=1)),
        )
        assert resp.status_code == 400

    async def test_range_too_wide_is_refused(
        self, client, booking_config, collaborator, service
    ):
        """A slot computation per day is not free — the span is capped."""
        start = date.today()
        resp = await client.get(
            CALENDAR,
            params=_params(service.id, collaborator.id, start, start + timedelta(days=400)),
        )
        assert resp.status_code == 400

    async def test_same_collaborator_service_rule_applies(
        self, client, booking_config, collaborator, unoffered_service
    ):
        start = date.today()
        resp = await client.get(
            CALENDAR,
            params=_params(unoffered_service.id, collaborator.id, start, start + timedelta(days=6)),
        )
        assert resp.status_code == 400
        assert "non esegue" in resp.json()["detail"]

    async def test_hidden_collaborator_is_refused(
        self, client, booking_config, hidden_collaborator, service
    ):
        start = date.today()
        resp = await client.get(
            CALENDAR,
            params=_params(service.id, hidden_collaborator.id, start, start + timedelta(days=6)),
        )
        assert resp.status_code == 404
