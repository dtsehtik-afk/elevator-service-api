"""System settings router — working hours and other configurable parameters."""
import json
import os
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from app.database import get_db
from app.auth.dependencies import get_current_user, require_admin
from app.models.technician import Technician

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


# ── Holidays ──────────────────────────────────────────────────────────────────

@router.get("/holidays", summary="Get list of closed holiday dates (YYYY-MM-DD)")
def get_holidays(db: Session = Depends(get_db), _=Depends(require_admin)):
    raw = _get_setting(db, "holidays")
    return json.loads(raw) if raw else []


class HolidaysPayload(BaseModel):
    dates: List[str]  # list of "YYYY-MM-DD" strings


@router.post("/holidays", summary="Save holiday dates and reload in-memory set (admin only)")
def save_holidays(payload: HolidaysPayload, db: Session = Depends(get_db), _=Depends(require_admin)):
    from app.services import working_hours as wh_module
    _set_setting(db, "holidays", json.dumps(payload.dates))
    wh_module._HOLIDAYS = set(payload.dates)
    return {"ok": True}


@router.post("/holidays/auto-fetch", summary="Auto-fetch Israeli holidays from Hebcal for current+next year")
def auto_fetch_holidays(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Calls Hebcal API, merges with any manually-set dates, saves and hot-reloads."""
    from datetime import date as _date
    from app.services.working_hours import fetch_holidays_from_hebcal
    from app.services import working_hours as wh_module

    current_year = _date.today().year
    fetched: list[str] = []
    errors: list[str] = []
    for year in [current_year, current_year + 1]:
        try:
            fetched.extend(fetch_holidays_from_hebcal(year))
        except Exception as exc:
            errors.append(f"{year}: {exc}")

    existing_raw = _get_setting(db, "holidays")
    existing = set()
    if existing_raw:
        try:
            parsed = json.loads(existing_raw)
            if isinstance(parsed, list):
                existing = set(parsed)
        except Exception as e:
            errors.append(f"DB parse error: {e}")

    merged = sorted(existing | set(fetched))

    try:
        _set_setting(db, "holidays", json.dumps(merged))
        wh_module._HOLIDAYS = set(merged)
    except Exception as e:
        return {"ok": False, "error": str(e), "errors": errors}
    return {"ok": True, "fetched": len(fetched), "total": len(merged), "dates": merged, "errors": errors}


# ── Role permissions ──────────────────────────────────────────────────────────

_DEFAULT_ROLE_PERMISSIONS: Dict[str, Dict[str, List[str]]] = {
    "ADMIN": {
        "service_calls": ["view", "create", "assign", "close", "delete"],
        "invoices":       ["view", "create", "send", "mark_paid", "delete"],
        "inventory":      ["view", "manage", "purchase_orders"],
        "crm":            ["view", "manage"],
        "hr":             ["view", "manage"],
        "reports":        ["view", "export"],
        "settings":       ["view", "edit"],
        "users":          ["view", "manage", "assign_roles"],
    },
    "CEO": {
        "service_calls": ["view", "create", "assign", "close"],
        "invoices":       ["view", "create", "send", "mark_paid"],
        "inventory":      ["view", "manage", "purchase_orders"],
        "crm":            ["view", "manage"],
        "hr":             ["view", "manage"],
        "reports":        ["view", "export"],
        "settings":       ["view", "edit"],
        "users":          ["view", "manage", "assign_roles"],
    },
    "VP": {
        "service_calls": ["view", "create", "assign", "close"],
        "invoices":       ["view", "create", "send", "mark_paid"],
        "inventory":      ["view", "manage"],
        "crm":            ["view", "manage"],
        "hr":             ["view"],
        "reports":        ["view", "export"],
        "settings":       ["view"],
        "users":          ["view"],
    },
    "SERVICE_MANAGER": {
        "service_calls": ["view", "create", "assign", "close"],
        "invoices":       ["view"],
        "inventory":      ["view"],
        "crm":            ["view"],
        "reports":        ["view", "export"],
        "settings":       ["view"],
        "users":          ["view"],
    },
    "DISPATCHER": {
        "service_calls": ["view", "create", "assign"],
        "inventory":      ["view"],
        "reports":        ["view"],
    },
    "TECHNICIAN": {
        "service_calls": ["view", "create", "assign", "close"],
    },
    "ACCOUNTANT": {
        "invoices": ["view", "create", "send", "mark_paid"],
        "reports":  ["view", "export"],
    },
    "SECRETARY": {
        "service_calls": ["view"],
        "invoices":       ["view"],
        "reports":        ["view"],
    },
    "SALES": {
        "crm":      ["view", "manage"],
        "invoices": ["view"],
        "reports":  ["view"],
    },
    "INVENTORY_MANAGER": {
        "inventory": ["view", "manage", "purchase_orders"],
        "reports":   ["view"],
    },
}


@router.get("/roles", summary="Get all role permissions (merged defaults + overrides)")
def get_role_permissions(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    raw = _get_setting(db, "role_permissions")
    overrides = json.loads(raw) if raw else {}
    merged = {}
    for role, perms in _DEFAULT_ROLE_PERMISSIONS.items():
        merged[role] = overrides.get(role, perms)
    return merged


@router.put("/roles", summary="Save role permissions overrides (admin only)")
def save_role_permissions(
    payload: Dict[str, Dict[str, List[str]]],
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    _set_setting(db, "role_permissions", json.dumps(payload))
    return {"ok": True}


@router.get("/roles/defaults", summary="Get built-in role permission defaults")
def get_role_defaults(current_user: Technician = Depends(get_current_user)):
    return _DEFAULT_ROLE_PERMISSIONS


# ── Field label overrides ─────────────────────────────────────────────────────

@router.get("/field-labels/{entity_type}", summary="Get custom label overrides for an entity's built-in fields")
def get_field_labels(
    entity_type: str,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    raw = _get_setting(db, f"field_labels_{entity_type}")
    return json.loads(raw) if raw else {}


@router.put("/field-labels/{entity_type}", summary="Save label overrides for built-in fields (admin only)")
def save_field_labels(
    entity_type: str,
    payload: Dict[str, str],  # field_key → custom_label
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    _set_setting(db, f"field_labels_{entity_type}", json.dumps(payload))
    return {"ok": True}


# ── Navigation config ─────────────────────────────────────────────────────────
# Stored as: { "/path": {"label": "שם", "visible": true} }

@router.get("/nav-config", summary="Get nav label/visibility overrides")
def get_nav_config(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    raw = _get_setting(db, "nav_config")
    return json.loads(raw) if raw else {}


@router.put("/nav-config", summary="Save nav label/visibility overrides (admin only)")
def save_nav_config(
    payload: Dict[str, Any],  # path → {label, visible}
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    _set_setting(db, "nav_config", json.dumps(payload))
    return {"ok": True}


# ── Company info ─────────────────────────────────────────────────────────────

@router.get("/company-info", summary="Get company name (public — no auth)")
def get_company_info(db: Session = Depends(get_db)):
    raw = _get_setting(db, "company_info")
    if raw:
        return json.loads(raw)
    return {"company_name": "אקורד מעליות", "company_icon": "⚡"}


@router.put("/company-info", summary="Save company name (admin only)")
def save_company_info(
    payload: Dict[str, str],
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    _set_setting(db, "company_info", json.dumps(payload))
    return {"ok": True}


@router.post("/company-info/admin-sync", summary="Sync company info pushed from admin console (api-key auth)")
def admin_sync_company_info(
    payload: Dict[str, str],
    x_api_key: str = Header(None, alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    secret = os.getenv("WEBHOOK_SECRET", "")
    if not secret or x_api_key != secret:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Invalid API key")
    _set_setting(db, "company_info", json.dumps(payload))
    return {"ok": True}


# ── WhatsApp agent config ─────────────────────────────────────────────────────

from app.services.chat_agent import _SYSTEM_PROMPT as _DEFAULT_SYSTEM_PROMPT


@router.get("/agent-config", summary="Get WhatsApp AI agent configuration")
def get_agent_config(
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    raw = _get_setting(db, "wa_agent_config")
    if raw:
        return json.loads(raw)
    return {"system_prompt": _DEFAULT_SYSTEM_PROMPT}


@router.post("/agent-config", summary="Save WhatsApp AI agent configuration (admin only)")
def save_agent_config(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    _set_setting(db, "wa_agent_config", json.dumps(payload))
    # Update in-memory prompt so running agent picks it up immediately
    try:
        from app.services import chat_agent as _ca
        _ca._SYSTEM_PROMPT = payload.get("system_prompt", _DEFAULT_SYSTEM_PROMPT)
    except Exception:
        pass
    return {"ok": True}
