"""Tests for service call lifecycle: open, assign, close, recurring detection."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_service_call(client, admin_token, sample_elevator):
    """Opening a service call should return status 201 and OPEN status."""
    resp = client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "Building Manager",
            "description": "Elevator stuck on floor 5",
            "priority": "HIGH",
            "fault_type": "STUCK",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "OPEN"
    assert data["is_recurring"] is False


def test_service_call_invalid_priority(client, admin_token, sample_elevator):
    """Invalid priority value should return 422."""
    resp = client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "Manager",
            "description": "Issue",
            "priority": "SUPER_URGENT",
            "fault_type": "OTHER",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 422


def test_service_call_not_found_elevator(client, admin_token):
    """Opening a call for a non-existent elevator should return 404."""
    resp = client.post(
        "/calls",
        json={
            "elevator_id": str(uuid.uuid4()),
            "reported_by": "Manager",
            "description": "Issue",
            "priority": "LOW",
            "fault_type": "OTHER",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 404


def test_recurring_detection(client, admin_token, sample_elevator, db):
    """A second call with the same fault_type within 30 days should be flagged recurring."""
    from app.models.service_call import ServiceCall

    # Insert a prior call directly into DB (simulating a recent call)
    prior_call = ServiceCall(
        elevator_id=sample_elevator.id,
        reported_by="Manager",
        description="First call",
        priority="MEDIUM",
        fault_type="DOOR",
        status="RESOLVED",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db.add(prior_call)
    db.commit()

    resp = client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "Manager",
            "description": "Door stuck again",
            "priority": "MEDIUM",
            "fault_type": "DOOR",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 201
    assert resp.json()["is_recurring"] is True


def test_update_service_call_status(client, admin_token, sample_elevator):
    """Updating status should be reflected in the response."""
    # Create
    create_resp = client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "Tech",
            "description": "Motor noise",
            "priority": "MEDIUM",
            "fault_type": "MECHANICAL",
        },
        headers=auth(admin_token),
    )
    call_id = create_resp.json()["id"]

    # Update
    update_resp = client.patch(
        f"/calls/{call_id}",
        json={"status": "IN_PROGRESS"},
        headers=auth(admin_token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "IN_PROGRESS"


def test_resolve_call_sets_resolved_at(client, admin_token, sample_elevator):
    """Resolving a call should automatically set resolved_at."""
    create_resp = client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "Tech",
            "description": "Electrical fault",
            "priority": "HIGH",
            "fault_type": "ELECTRICAL",
        },
        headers=auth(admin_token),
    )
    call_id = create_resp.json()["id"]

    update_resp = client.patch(
        f"/calls/{call_id}",
        json={"status": "RESOLVED", "resolution_notes": "Replaced fuse"},
        headers=auth(admin_token),
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["status"] == "RESOLVED"
    assert data["resolved_at"] is not None


def test_audit_log_created(client, admin_token, sample_elevator):
    """Each status change should create an audit log entry."""
    create_resp = client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "Manager",
            "description": "Test call",
            "priority": "LOW",
            "fault_type": "OTHER",
        },
        headers=auth(admin_token),
    )
    call_id = create_resp.json()["id"]

    client.patch(
        f"/calls/{call_id}",
        json={"status": "IN_PROGRESS"},
        headers=auth(admin_token),
    )

    audit_resp = client.get(f"/calls/{call_id}/audit", headers=auth(admin_token))
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    assert len(logs) >= 2  # Creation + status change
