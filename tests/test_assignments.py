"""Tests for call assignment flow: manual assign, reassign, and status tracking."""

import pytest
import uuid


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def open_call(client, admin_token, sample_elevator):
    resp = client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "Resident",
            "description": "Door won't close",
            "priority": "MEDIUM",
            "fault_type": "DOOR",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 201
    return resp.json()


def test_manual_assign(client, admin_token, open_call, technician_user):
    call_id = open_call["id"]
    resp = client.post(
        f"/calls/{call_id}/assign",
        json={"technician_id": str(technician_user.id), "notes": "Nearest tech"},
        headers=auth(admin_token),
    )
    assert resp.status_code in (200, 201)

    # Verify the call is now ASSIGNED
    call = client.get(f"/calls/{call_id}", headers=auth(admin_token))
    assert call.json()["status"] == "ASSIGNED"


def test_manual_assign_invalid_technician(client, admin_token, open_call):
    call_id = open_call["id"]
    resp = client.post(
        f"/calls/{call_id}/assign",
        json={"technician_id": str(uuid.uuid4())},
        headers=auth(admin_token),
    )
    assert resp.status_code == 404


def test_manual_assign_invalid_call(client, admin_token, technician_user):
    resp = client.post(
        f"/calls/{uuid.uuid4()}/assign",
        json={"technician_id": str(technician_user.id)},
        headers=auth(admin_token),
    )
    assert resp.status_code == 404


def test_technician_cannot_assign(client, tech_token, open_call, technician_user):
    call_id = open_call["id"]
    resp = client.post(
        f"/calls/{call_id}/assign",
        json={"technician_id": str(technician_user.id)},
        headers=auth(tech_token),
    )
    assert resp.status_code == 403


def test_call_filter_by_status(client, admin_token, sample_elevator):
    # Create an open call
    client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "Manager",
            "description": "Test",
            "priority": "LOW",
            "fault_type": "OTHER",
        },
        headers=auth(admin_token),
    )
    resp = client.get("/calls?status=OPEN", headers=auth(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert all(c["status"] == "OPEN" for c in data)


def test_call_filter_by_fault_type(client, admin_token, sample_elevator):
    client.post(
        "/calls",
        json={
            "elevator_id": str(sample_elevator.id),
            "reported_by": "System",
            "description": "Maintenance due",
            "priority": "LOW",
            "fault_type": "MAINTENANCE",
        },
        headers=auth(admin_token),
    )
    resp = client.get("/calls?fault_type=MAINTENANCE", headers=auth(admin_token))
    assert resp.status_code == 200
    assert all(c["fault_type"] == "MAINTENANCE" for c in resp.json())


def test_resolve_call(client, admin_token, open_call):
    call_id = open_call["id"]
    resp = client.patch(
        f"/calls/{call_id}",
        json={"status": "RESOLVED", "resolution_notes": "Fixed the door sensor"},
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "RESOLVED"
    assert data["resolution_notes"] == "Fixed the door sensor"
    assert data["resolved_at"] is not None
