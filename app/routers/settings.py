"""System settings router — working hours and other configurable parameters."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.auth.dependencies import require_admin

router = APIRouter(prefix="/settings", tags=["Settings"])


class DaySchedule(BaseModel):
    enabled: bool = True
    start: str = "07:30"   # "HH:MM"
    end: str   = "16:30"


class WorkingHoursPayload(BaseModel):
    sun: DaySchedule
    mon: DaySchedule
    tue: DaySchedule
    wed: DaySchedule
    thu: DaySchedule
    fri: DaySchedule
    sat: DaySchedule


def _get_setting(db: Session, key: str) -> Optional[str]:
    from sqlalchemy import text
    row = db.execute(text("SELECT value FROM system_settings WHERE key = :k"), {"k": key}).fetchone()
    return row[0] if row else None


def _set_setting(db: Session, key: str, value: str) -> None:
    from sqlalchemy import text
    db.execute(
        text("INSERT INTO system_settings (key, value) VALUES (:k, :v) "
             "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()"),
        {"k": key, "v": value},
    )
    db.commit()


@router.get("/working-hours")
def get_working_hours(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Return current working hours schedule."""
    import json
    raw = _get_setting(db, "working_hours")
    if raw:
        return json.loads(raw)
    # Defaults matching working_hours.py
    return {
        "sun": {"enabled": True,  "start": "07:30", "end": "16:30"},
        "mon": {"enabled": True,  "start": "07:30", "end": "16:30"},
        "tue": {"enabled": True,  "start": "07:30", "end": "16:30"},
        "wed": {"enabled": True,  "start": "07:30", "end": "16:30"},
        "thu": {"enabled": True,  "start": "07:30", "end": "16:30"},
        "fri": {"enabled": True,  "start": "07:30", "end": "13:00"},
        "sat": {"enabled": False, "start": "00:00", "end": "00:00"},
    }


@router.post("/working-hours")
def save_working_hours(payload: WorkingHoursPayload, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Save working hours schedule and reload the in-memory cache."""
    import json
    from app.services import working_hours as wh_module
    data = payload.model_dump()
    _set_setting(db, "working_hours", json.dumps(data))
    # Reload in-memory schedule
    _reload_working_hours(wh_module, data)
    return {"ok": True}


def _reload_working_hours(wh_module, data: dict) -> None:
    """Update the in-memory _SCHEDULE dict from the saved payload."""
    day_map = {"sun": 6, "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5}
    new_schedule = {}
    for day_name, idx in day_map.items():
        d = data.get(day_name, {})
        if not d.get("enabled", False):
            continue
        sh, sm = [int(x) for x in d["start"].split(":")]
        eh, em = [int(x) for x in d["end"].split(":")]
        new_schedule[idx] = (sh, sm, eh, em)
    wh_module._SCHEDULE = new_schedule
