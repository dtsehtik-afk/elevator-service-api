"""Tests for authentication: login, token validation, role enforcement."""

import pytest


def test_login_success(client, admin_user):
    """Valid credentials should return an access token."""
    resp = client.post(
        "/auth/login",
        data={"username": "admin@test.com", "password": "adminpass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, admin_user):
    """Wrong password should return 401."""
    resp = client.post(
        "/auth/login",
        data={"username": "admin@test.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


def test_login_unknown_email(client):
    """Unknown email should return 401."""
    resp = client.post(
        "/auth/login",
        data={"username": "nobody@test.com", "password": "pass"},
    )
    assert resp.status_code == 401


def test_protected_endpoint_no_token(client):
    """Accessing a protected endpoint without a token should return 401."""
    resp = client.get("/elevators")
    assert resp.status_code == 401


def test_protected_endpoint_with_token(client, admin_token):
    """A valid token should grant access to protected endpoints."""
    resp = client.get(
        "/elevators",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200


def test_admin_only_endpoint_with_technician_token(client, tech_token):
    """A technician token should be rejected on ADMIN-only endpoints."""
    resp = client.get(
        "/analytics/risk-elevators",
        headers={"Authorization": f"Bearer {tech_token}"},
    )
    assert resp.status_code == 403


def test_health_endpoint_public(client):
    """Health endpoint should be accessible without authentication."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_invalid_token(client):
    """A garbage token should return 401."""
    resp = client.get(
        "/elevators",
        headers={"Authorization": "Bearer this.is.garbage"},
    )
    assert resp.status_code == 401
