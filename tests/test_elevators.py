"""Tests for elevator CRUD and analytics endpoints."""

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_elevator(client, admin_token):
    """Admin should be able to create a new elevator."""
    resp = client.post(
        "/elevators",
        json={
            "address": "5 Dizengoff St",
            "city": "Tel Aviv",
            "floor_count": 10,
            "status": "ACTIVE",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["city"] == "Tel Aviv"
    assert data["risk_score"] == 0.0


def test_create_elevator_invalid_status(client, admin_token):
    """Invalid status should return 422."""
    resp = client.post(
        "/elevators",
        json={
            "address": "5 Dizengoff St",
            "city": "Tel Aviv",
            "floor_count": 10,
            "status": "INVALID_STATUS",
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 422


def test_list_elevators(client, admin_token, sample_elevator):
    """Listing elevators should return at least the sample elevator."""
    resp = client.get("/elevators", headers=auth(admin_token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


def test_filter_elevators_by_city(client, admin_token, sample_elevator):
    """Filtering by city should return matching elevators."""
    resp = client.get("/elevators?city=Tel+Aviv", headers=auth(admin_token))
    assert resp.status_code == 200
    for e in resp.json():
        assert "Tel Aviv" in e["city"]


def test_get_elevator(client, admin_token, sample_elevator):
    """Fetching by ID should return the correct elevator."""
    resp = client.get(f"/elevators/{sample_elevator.id}", headers=auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(sample_elevator.id)


def test_get_elevator_not_found(client, admin_token):
    """Fetching a non-existent elevator should return 404."""
    import uuid
    resp = client.get(f"/elevators/{uuid.uuid4()}", headers=auth(admin_token))
    assert resp.status_code == 404


def test_update_elevator(client, admin_token, sample_elevator):
    """Updating an elevator should persist the changes."""
    resp = client.put(
        f"/elevators/{sample_elevator.id}",
        json={"status": "UNDER_REPAIR"},
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "UNDER_REPAIR"


def test_elevator_analytics(client, admin_token, sample_elevator):
    """Analytics endpoint should return a valid response."""
    resp = client.get(
        f"/elevators/{sample_elevator.id}/analytics",
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_calls" in data
    assert "risk_score" in data


def test_technician_cannot_create_elevator(client, tech_token):
    """A technician role should not be able to create an elevator."""
    resp = client.post(
        "/elevators",
        json={
            "address": "1 Test St",
            "city": "Haifa",
            "floor_count": 5,
            "status": "ACTIVE",
        },
        headers=auth(tech_token),
    )
    assert resp.status_code == 403
