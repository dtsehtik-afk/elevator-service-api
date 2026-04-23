"""Tests for management company CRUD and elevator association."""

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_companies_empty(client, admin_token):
    resp = client.get("/management-companies", headers=auth(admin_token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_company(client, admin_token):
    resp = client.post(
        "/management-companies",
        json={
            "name": "Acme Elevators",
            "contact_name": "John Doe",
            "phone": "0521234567",
            "email": "john@acme.com",
            "caller_phones": ["0521234567", "0509876543"],
        },
        headers=auth(admin_token),
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["name"] == "Acme Elevators"


def test_create_company_minimal(client, admin_token):
    resp = client.post(
        "/management-companies",
        json={"name": "Minimal Co"},
        headers=auth(admin_token),
    )
    assert resp.status_code in (200, 201)
    assert resp.json()["name"] == "Minimal Co"


def test_get_company(client, admin_token):
    create = client.post(
        "/management-companies",
        json={"name": "Test Co", "phone": "0501111111"},
        headers=auth(admin_token),
    )
    cid = create.json()["id"]
    resp = client.get(f"/management-companies/{cid}", headers=auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["id"] == cid


def test_get_company_not_found(client, admin_token):
    import uuid
    resp = client.get(f"/management-companies/{uuid.uuid4()}", headers=auth(admin_token))
    assert resp.status_code == 404


def test_update_company(client, admin_token):
    create = client.post(
        "/management-companies",
        json={"name": "Old Name"},
        headers=auth(admin_token),
    )
    cid = create.json()["id"]
    resp = client.patch(
        f"/management-companies/{cid}",
        json={"name": "New Name", "caller_phones": ["0501234567"]},
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_assign_elevator_to_company(client, admin_token, sample_elevator):
    create = client.post(
        "/management-companies",
        json={"name": "Property Mgmt"},
        headers=auth(admin_token),
    )
    cid = create.json()["id"]

    # elevator_id is a query param on the assign-elevator endpoint
    resp = client.post(
        f"/management-companies/{cid}/assign-elevator?elevator_id={sample_elevator.id}",
        headers=auth(admin_token),
    )
    assert resp.status_code == 200


def test_delete_company(client, admin_token):
    create = client.post(
        "/management-companies",
        json={"name": "To Delete"},
        headers=auth(admin_token),
    )
    cid = create.json()["id"]
    resp = client.delete(f"/management-companies/{cid}", headers=auth(admin_token))
    assert resp.status_code in (200, 204)


def test_technician_cannot_create_company(client, tech_token):
    resp = client.post(
        "/management-companies",
        json={"name": "Forbidden Co"},
        headers=auth(tech_token),
    )
    assert resp.status_code == 403
