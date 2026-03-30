"""Dev startup script — creates DB, seeds admin user, then launches uvicorn."""

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///elevator_dev.db")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-local")

# ── Bootstrap DB ──────────────────────────────────────────────────────────────
from app.database import Base, engine, SessionLocal
import app.models  # noqa: F401 — registers all models

Base.metadata.create_all(bind=engine)

from app.models.technician import Technician
from app.auth.security import hash_password

db = SessionLocal()
if not db.query(Technician).filter(Technician.email == "admin@example.com").first():
    db.add(Technician(
        name="Admin",
        email="admin@example.com",
        hashed_password=hash_password("admin1234"),
        role="ADMIN",
        specializations=[],
        area_codes=[],
    ))
    db.commit()
    print("Admin user created: admin@example.com / admin1234")

# Seed demo data
elevators_data = [
    {"address": "5 Rothschild Blvd",  "city": "Tel Aviv",  "floor_count": 15, "model": "Otis Gen2",           "manufacturer": "Otis",        "status": "ACTIVE"},
    {"address": "12 Ben Gurion Blvd", "city": "Tel Aviv",  "floor_count": 22, "model": "KONE MonoSpace",      "manufacturer": "KONE",        "status": "ACTIVE"},
    {"address": "3 HaYarkon St",      "city": "Tel Aviv",  "floor_count": 8,  "model": "Schindler 3300",      "manufacturer": "Schindler",   "status": "UNDER_REPAIR"},
    {"address": "45 Herzl St",        "city": "Haifa",     "floor_count": 12, "model": "ThyssenKrupp",        "manufacturer": "TK Elevator", "status": "ACTIVE"},
    {"address": "7 Dizengoff St",     "city": "Tel Aviv",  "floor_count": 5,  "model": "Otis 2000",           "manufacturer": "Otis",        "status": "ACTIVE"},
    {"address": "88 Begin Rd",        "city": "Jerusalem", "floor_count": 18, "model": "Mitsubishi Nexiez",   "manufacturer": "Mitsubishi",  "status": "INACTIVE"},
    {"address": "22 Allenby St",      "city": "Tel Aviv",  "floor_count": 10, "model": "Otis Gen2",           "manufacturer": "Otis",        "status": "ACTIVE"},
    {"address": "5 Balfour St",       "city": "Jerusalem", "floor_count": 6,  "model": "KONE EcoSpace",       "manufacturer": "KONE",        "status": "ACTIVE"},
]

from app.models.elevator import Elevator
if db.query(Elevator).count() == 0:
    elevators = []
    for e in elevators_data:
        el = Elevator(**e)
        db.add(el)
        elevators.append(el)
    db.flush()

    from app.models.service_call import ServiceCall
    import datetime
    calls = [
        (elevators[0].id, "Building Manager", "Unusual noise from motor",    "HIGH",     "MECHANICAL"),
        (elevators[1].id, "Tenant",           "Door won't close fully",      "CRITICAL",  "DOOR"),
        (elevators[2].id, "Security Guard",   "Elevator software crash",     "LOW",       "SOFTWARE"),
        (elevators[3].id, "Resident",         "Stuck between floors 3-4",    "CRITICAL",  "STUCK"),
        (elevators[4].id, "Manager",          "Electrical flickering light", "MEDIUM",    "ELECTRICAL"),
        (elevators[0].id, "Tenant",           "Motor noise again",           "HIGH",      "MECHANICAL"),
        (elevators[1].id, "Manager",          "Door sensor fault",           "MEDIUM",    "DOOR"),
        (elevators[5].id, "Receptionist",     "Buttons unresponsive",        "HIGH",      "ELECTRICAL"),
    ]
    for eid, rep, desc, pri, fault in calls:
        db.add(ServiceCall(
            elevator_id=eid, reported_by=rep, description=desc,
            priority=pri, fault_type=fault,
        ))

    from app.models.maintenance import MaintenanceSchedule
    today = datetime.date.today()
    maint_data = [
        (elevators[0].id, today + datetime.timedelta(days=15),  "QUARTERLY"),
        (elevators[1].id, today + datetime.timedelta(days=45),  "SEMI_ANNUAL"),
        (elevators[2].id, today - datetime.timedelta(days=5),   "ANNUAL"),      # OVERDUE
        (elevators[3].id, today + datetime.timedelta(days=90),  "INSPECTION"),
        (elevators[6].id, today + datetime.timedelta(days=180), "ANNUAL"),
    ]
    for eid, dt, mtype in maint_data:
        status = "OVERDUE" if dt < today else "SCHEDULED"
        db.add(MaintenanceSchedule(
            elevator_id=eid, scheduled_date=dt,
            maintenance_type=mtype, status=status,
            checklist={"items": [{"name": "Check cables", "done": False},
                                  {"name": "Test emergency brake", "done": False}]},
        ))

    db.commit()
    print(f"Seeded {len(elevators_data)} elevators, {len(calls)} calls, {len(maint_data)} maintenance events")

    # Technicians
    from app.models.technician import Technician
    techs = [
        {"name": "Yossi Cohen", "email": "yossi@service.com", "role": "TECHNICIAN",
         "specializations": ["MECHANICAL", "DOOR"],    "area_codes": ["6200"], "max_daily_calls": 6,
         "current_latitude": 32.08, "current_longitude": 34.78},
        {"name": "Dana Levy",   "email": "dana@service.com",  "role": "TECHNICIAN",
         "specializations": ["ELECTRICAL", "SOFTWARE"], "area_codes": ["3200"], "max_daily_calls": 8,
         "current_latitude": 32.79, "current_longitude": 34.98},
        {"name": "Avi Mizrahi", "email": "avi@service.com",   "role": "DISPATCHER",
         "specializations": [],                          "area_codes": [],       "max_daily_calls": 10,
         "current_latitude": 31.77, "current_longitude": 35.21},
    ]
    for t in techs:
        if not db.query(Technician).filter(Technician.email == t["email"]).first():
            db.add(Technician(
                hashed_password=hash_password("tech1234"), is_available=True, **t
            ))
    db.commit()
    print(f"Seeded {len(techs)} technicians")

db.close()

# ── Launch uvicorn ─────────────────────────────────────────────────────────────
print("\nStarting server at http://localhost:8000")
print("  Swagger UI : http://localhost:8000/docs")
print("  Dashboard  : http://localhost:8501\n")

import uvicorn
uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
