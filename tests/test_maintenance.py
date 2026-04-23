"""Tests for maintenance schedule CRUD and status transitions."""

import pytest
from datetime import date, timedelta


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def future_date(days=10):
    return (date.today() + timedelta(days=days)).isoformat()


def test_list_maintenance_empty(client, admin_token):
    resp = client.get("/maintenance", headers=auth(admin_token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_maintenance(client, admin_token, sample_elevator, technician_user):
    resp = client.post(
        "/maintenance",
        json={
            "elevator_id": str(sample_elevator.id),
            "technician_id": str(technician_user.id),
            "scheduled_date": future_date(10),
            "maintenance_type": "QUARTERLY",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "SCHEDULED"
    assert data["maintenance_type"] == "QUARTERLY"
    assert data["elevator_id"] == str(sample_elevator.id)


def test_create_maintenance_no_technician(client, admin_token, sample_elevator):
    resp = client.post(
        "/maintenance",
        json={
            "elevator_id": str(sample_elevator.id),
            "scheduled_date": future_date(5),
            "maintenance_type": "ANNUAL",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 201
    assert resp.json()["technician_id"] is None


def test_update_maintenance_status(client, admin_token, sample_elevator):
    create = client.post(
        "/maintenance",
        json={
            "elevator_id": str(sample_elevator.id),
            "scheduled_date": future_date(7),
            "maintenance_type": "INSPECTION",
        },
        headers=auth(admin_token),
    )
    assert create.status_code == 201
    mid = create.json()["id"]

    update = client.patch(
        f"/maintenance/{mid}",
        json={"status": "COMPLETED", "completion_notes": "All done"},
        headers=auth(admin_token),
    )
    assert update.status_code == 200
    assert update.json()["status"] == "COMPLETED"
    assert update.json()["completion_notes"] == "All done"


def test_maintenance_invalid_elevator(client, admin_token):
    import uuid
    resp = client.post(
        "/maintenance",
        json={
            "elevator_id": str(uuid.uuid4()),
            "scheduled_date": future_date(10),
            "maintenance_type": "QUARTERLY",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 404


def test_maintenance_filter_by_elevator(client, admin_token, sample_elevator):
    client.post(
        "/maintenance",
        json={
            "elevator_id": str(sample_elevator.id),
            "scheduled_date": future_date(10),
            "maintenance_type": "SEMI_ANNUAL",
        },
        headers=auth(admin_token),
    )
    resp = client.get(
        f"/maintenance?elevator_id={sample_elevator.id}",
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    assert all(m["elevator_id"] == str(sample_elevator.id) for m in resp.json())


def test_technician_cannot_create_maintenance(client, tech_token, sample_elevator):
    resp = client.post(
        "/maintenance",
        json={
            "elevator_id": str(sample_elevator.id),
            "scheduled_date": future_date(10),
            "maintenance_type": "QUARTERLY",
        },
        headers=auth(tech_token),
    )
    assert resp.status_code == 403
