"""Tests for the daily schedule algorithm."""

import uuid
from datetime import date, datetime, timezone

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_empty_schedule(client, admin_token, technician_user):
    """A technician with no assignments should return an empty schedule."""
    resp = client.get(
        f"/schedule/{technician_user.id}",
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_stops"] == 0
    assert data["stops"] == []


def test_schedule_with_service_calls(client, admin_token, technician_user, sample_elevator, db):
    """Schedule should include assigned service calls sorted by priority."""
    from app.models.assignment import Assignment
    from app.models.service_call import ServiceCall

    today = date.today()

    # Create two calls with different priorities
    high_call = ServiceCall(
        elevator_id=sample_elevator.id,
        reported_by="Manager",
        description="High priority",
        priority="HIGH",
        fault_type="MECHANICAL",
        status="ASSIGNED",
        created_at=datetime.now(timezone.utc),
        assigned_at=datetime.now(timezone.utc),
    )
    low_call = ServiceCall(
        elevator_id=sample_elevator.id,
        reported_by="Manager",
        description="Low priority",
        priority="LOW",
        fault_type="OTHER",
        status="ASSIGNED",
        created_at=datetime.now(timezone.utc),
        assigned_at=datetime.now(timezone.utc),
    )
    db.add_all([high_call, low_call])
    db.flush()

    # Assign both to the technician with today's timestamp
    for call in [high_call, low_call]:
        assignment = Assignment(
            service_call_id=call.id,
            technician_id=technician_user.id,
            assignment_type="MANUAL",
            assigned_at=datetime.now(timezone.utc),
        )
        db.add(assignment)
    db.commit()

    resp = client.get(
        f"/schedule/{technician_user.id}?date={today.isoformat()}",
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_stops"] == 2

    # HIGH should appear before LOW
    priorities = [s["priority"] for s in data["stops"]]
    assert priorities.index("HIGH") < priorities.index("LOW")


def test_schedule_invalid_date(client, admin_token, technician_user):
    """An invalid date format should return 400."""
    resp = client.get(
        f"/schedule/{technician_user.id}?date=not-a-date",
        headers=auth(admin_token),
    )
    assert resp.status_code == 400


def test_schedule_unknown_technician(client, admin_token):
    """Fetching a schedule for a non-existent technician should return 404."""
    resp = client.get(
        f"/schedule/{uuid.uuid4()}",
        headers=auth(admin_token),
    )
    assert resp.status_code == 404


def test_schedule_estimated_times_present(client, admin_token, technician_user, sample_elevator, db):
    """Each stop in the schedule should include estimated_arrival and duration."""
    from app.models.assignment import Assignment
    from app.models.service_call import ServiceCall

    call = ServiceCall(
        elevator_id=sample_elevator.id,
        reported_by="Manager",
        description="Test call",
        priority="MEDIUM",
        fault_type="ELECTRICAL",
        status="ASSIGNED",
        created_at=datetime.now(timezone.utc),
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.flush()
    db.add(Assignment(
        service_call_id=call.id,
        technician_id=technician_user.id,
        assignment_type="MANUAL",
        assigned_at=datetime.now(timezone.utc),
    ))
    db.commit()

    today = date.today()
    resp = client.get(
        f"/schedule/{technician_user.id}?date={today.isoformat()}",
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    stops = resp.json()["stops"]
    assert len(stops) >= 1
    assert "estimated_arrival" in stops[0]
    assert "estimated_duration_minutes" in stops[0]
