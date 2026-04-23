"""Tests for technician CRUD and auth role enforcement."""

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_technicians(client, admin_token):
    resp = client.get("/technicians", headers=auth(admin_token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_technician(client, admin_token):
    resp = client.post(
        "/technicians",
        json={
            "name": "New Tech",
            "email": "newtech@test.com",
            "phone": "0501234567",
            "password": "password123",
            "role": "TECHNICIAN",
            "specializations": ["MECHANICAL"],
            "area_codes": ["6200"],
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "New Tech"
    assert data["role"] == "TECHNICIAN"
    assert "hashed_password" not in data


def test_create_technician_duplicate_email(client, admin_token, technician_user):
    resp = client.post(
        "/technicians",
        json={
            "name": "Dup Tech",
            "email": "tech@test.com",  # same as technician_user
            "phone": "0509999999",
            "password": "password123",
            "role": "TECHNICIAN",
            "specializations": [],
            "area_codes": [],
        },
        headers=auth(admin_token),
    )
    assert resp.status_code == 409


def test_get_technician(client, admin_token, technician_user):
    resp = client.get(f"/technicians/{technician_user.id}", headers=auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(technician_user.id)


def test_get_technician_not_found(client, admin_token):
    import uuid
    resp = client.get(f"/technicians/{uuid.uuid4()}", headers=auth(admin_token))
    assert resp.status_code == 404


def test_update_technician_location(client, tech_token):
    # Location update uses the authenticated user's identity — POST /technicians/location
    resp = client.post(
        "/technicians/location",
        json={"latitude": 32.09, "longitude": 34.79},
        headers=auth(tech_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_latitude"] == 32.09
    assert data["current_longitude"] == 34.79


def test_technician_cannot_create_technician(client, tech_token):
    resp = client.post(
        "/technicians",
        json={
            "name": "Unauthorized",
            "email": "unauth@test.com",
            "phone": "0501111111",
            "password": "pass",
            "role": "TECHNICIAN",
            "specializations": [],
            "area_codes": [],
        },
        headers=auth(tech_token),
    )
    assert resp.status_code == 403
