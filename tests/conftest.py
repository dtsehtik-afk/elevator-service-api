"""Pytest fixtures — in-memory SQLite test database and test client."""

import os

# Must be set BEFORE any app module is imported so database.py picks up SQLite
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once per test session."""
    Base.metadata.create_all(bind=engine)
    # Disable rate limiting so repeated login calls in tests don't get blocked
    app.state.limiter.enabled = False
    from app.auth import router as auth_module
    auth_module._limiter.enabled = False
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """Provide a fresh database session per test, rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db):
    """FastAPI TestClient with the test database session injected."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db):
    """Create and return an admin technician for authenticated requests."""
    from app.auth.security import hash_password
    from app.models.technician import Technician

    user = Technician(
        name="Admin User",
        email="admin@test.com",
        hashed_password=hash_password("adminpass123"),
        role="ADMIN",
        specializations=[],
        area_codes=[],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def technician_user(db):
    """Create and return a regular technician for authenticated requests."""
    from app.auth.security import hash_password
    from app.models.technician import Technician

    user = Technician(
        name="Tech User",
        email="tech@test.com",
        hashed_password=hash_password("techpass123"),
        role="TECHNICIAN",
        specializations=["MECHANICAL"],
        area_codes=["6200"],
        current_latitude=32.0853,
        current_longitude=34.7818,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def admin_token(client, admin_user):
    """Return a JWT token for the admin user."""
    resp = client.post(
        "/auth/login",
        data={"username": "admin@test.com", "password": "adminpass123"},
    )
    return resp.json()["access_token"]


@pytest.fixture()
def tech_token(client, technician_user):
    """Return a JWT token for the technician user."""
    resp = client.post(
        "/auth/login",
        data={"username": "tech@test.com", "password": "techpass123"},
    )
    return resp.json()["access_token"]


@pytest.fixture()
def sample_elevator(db):
    """Create and return a sample elevator."""
    from app.models.elevator import Elevator

    elevator = Elevator(
        address="1 HaShalom Rd",
        city="Tel Aviv",
        building_name="Tower A",
        floor_count=20,
        model="Otis Gen2",
        manufacturer="Otis",
        serial_number="SN-001",
        status="ACTIVE",
        risk_score=0.0,
    )
    db.add(elevator)
    db.commit()
    db.refresh(elevator)
    return elevator
