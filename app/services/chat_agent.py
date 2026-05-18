"""
WhatsApp Chat Agent — conversational interface to the system via Claude.

Technicians and managers can ask free-text questions in Hebrew via WhatsApp:
  "מה קרה במעלית ברחוב הרצל 5 חיפה?"
  "מתי הייתה הקריאה האחרונה של תומר?"
  "כמה קריאות פתוחות יש היום?"

Claude uses tool-use to query the live database and answers in natural Hebrew.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.elevator import Elevator
from app.models.maintenance import MaintenanceSchedule as MaintenanceRecord
from app.models.service_call import ServiceCall
from app.models.technician import Technician
from app.models.customer import Customer
from app.models.management_company import ManagementCompany
from app.models.inspection_report import InspectionReport
from app.models.incoming_call import IncomingCallLog

logger = logging.getLogger(__name__)

# ── Tool definitions for Gemini REST API ─────────────────────────────────────

_GEMINI_TOOLS = [{
    "function_declarations": [
        {
            "name": "search_elevators",
            "description": "חפש מעליות לפי כתובת, עיר, שם בניין או מספר סידורי. כשמחפשים לפי עיר — השתמש ב-limit=100 כדי לקבל רשימה מלאה. ברירת המחדל היא 20.",
            "parameters": {"type": "OBJECT", "properties": {
                "query": {"type": "STRING", "description": "מחרוזת חיפוש — שם עיר, כתובת, בניין"},
                "city": {"type": "STRING", "description": "סינון לפי עיר בלבד (מדויק יותר ממחרוזת חיפוש)"},
                "limit": {"type": "INTEGER", "description": "מספר תוצאות מקסימלי — השתמש ב-100 לרשימה מלאה של עיר"},
            }, "required": []},
        },
        {
            "name": "get_elevator_calls",
            "description": "מחזיר היסטוריית קריאות שירות עבור מעלית ספציפית לפי מזהה.",
            "parameters": {"type": "OBJECT", "properties": {
                "elevator_id": {"type": "STRING", "description": "UUID של המעלית"},
                "limit": {"type": "INTEGER", "description": "מספר קריאות אחרונות"},
            }, "required": ["elevator_id"]},
        },
        {
            "name": "get_recent_calls",
            "description": "מחזיר קריאות שירות מהימים האחרונים. ניתן לסנן לפי סטטוס, טכנאי, עיר.",
            "parameters": {"type": "OBJECT", "properties": {
                "days": {"type": "INTEGER", "description": "כמה ימים אחורה"},
                "status": {"type": "STRING", "description": "OPEN/ASSIGNED/IN_PROGRESS/RESOLVED/CLOSED"},
                "city": {"type": "STRING", "description": "סנן לפי עיר"},
                "technician_name": {"type": "STRING", "description": "סנן לפי שם טכנאי"},
                "limit": {"type": "INTEGER", "description": "מספר תוצאות מקסימלי"},
            }, "required": []},
        },
        {
            "name": "get_technician_info",
            "description": "מחזיר פרטים ומידע על טכנאי — קריאות פתוחות, עומס עבודה.",
            "parameters": {"type": "OBJECT", "properties": {
                "name": {"type": "STRING", "description": "שם הטכנאי"},
            }, "required": ["name"]},
        },
        {
            "name": "get_elevator_maintenance",
            "description": "מחזיר רשומות תחזוקה תקופתית עבור מעלית.",
            "parameters": {"type": "OBJECT", "properties": {
                "elevator_id": {"type": "STRING", "description": "UUID של המעלית"},
            }, "required": ["elevator_id"]},
        },
        {
            "name": "get_system_summary",
            "description": "מחזיר סיכום כללי של מצב המערכת — כמה קריאות נפתחו היום, קריאות פתוחות, קריאות בטיפול, מספר טכנאים פעילים. השתמש בכלי זה לכל שאלה על כמות קריאות, סטטוס כללי או נתוני היום.",
            "parameters": {"type": "OBJECT", "properties": {}, "required": []},
        },
        {
            "name": "get_technician_location",
            "description": "מחזיר את המיקום הנוכחי של טכנאי (אם שיתף מיקום חי). יכול גם למצוא את הטכנאי הקרוב ביותר לאזור מסוים.",
            "parameters": {"type": "OBJECT", "properties": {
                "technician_name": {"type": "STRING", "description": "שם הטכנאי (אופציונלי)"},
                "near_address": {"type": "STRING", "description": "כתובת לחפש טכנאי קרוב (אופציונלי)"},
            }, "required": []},
        },
        {
            "name": "search_by_phone",
            "description": "חפש מעליות לפי מספר טלפון של המתקשר או חברת הניהול.",
            "parameters": {"type": "OBJECT", "properties": {
                "phone": {"type": "STRING", "description": "מספר טלפון לחיפוש"},
            }, "required": ["phone"]},
        },
        {
            "name": "close_service_call",
            "description": "סוגר קריאת שירות ומזין הערות פתרון. השתמש רק לאחר קבלת אישור מפורש מהמשתמש.",
            "parameters": {"type": "OBJECT", "properties": {
                "call_id": {"type": "STRING", "description": "UUID של הקריאה לסגירה"},
                "resolution_notes": {"type": "STRING", "description": "הערות תיקון/פתרון"},
            }, "required": ["call_id", "resolution_notes"]},
        },
        {
            "name": "assign_service_call",
            "description": "מעביר קריאת שירות לטכנאי אחר. השתמש רק לאחר קבלת אישור מפורש מהמשתמש.",
            "parameters": {"type": "OBJECT", "properties": {
                "call_id": {"type": "STRING", "description": "UUID של הקריאה"},
                "technician_name": {"type": "STRING", "description": "שם הטכנאי החדש"},
            }, "required": ["call_id", "technician_name"]},
        },
        {
            "name": "transfer_to_quote",
            "description": "מסמן קריאת שירות כדורשת הצעת מחיר ומוסיף הערות. השתמש רק לאחר קבלת אישור מפורש מהמשתמש.",
            "parameters": {"type": "OBJECT", "properties": {
                "call_id": {"type": "STRING", "description": "UUID של הקריאה"},
                "notes": {"type": "STRING", "description": "הערות לגבי הצעת המחיר"},
            }, "required": ["call_id"]},
        },
        {
            "name": "get_technician_route",
            "description": "מחזיר את רשימת הקריאות הפתוחות של טכנאי מסודרות כמסלול עבודה להיום.",
            "parameters": {"type": "OBJECT", "properties": {
                "technician_name": {"type": "STRING", "description": "שם הטכנאי"},
            }, "required": ["technician_name"]},
        },
        {
            "name": "get_my_calls",
            "description": "מחזיר את הקריאות הפתוחות המשובצות לטכנאי שמחזיק בשיחה הנוכחית.",
            "parameters": {"type": "OBJECT", "properties": {
                "phone": {"type": "STRING", "description": "מספר הטלפון של הטכנאי"},
            }, "required": ["phone"]},
        },
        {
            "name": "get_call_by_number",
            "description": "מחזיר פרטים מלאים על קריאת שירות לפי מספר קריאה. קבל 'S00042' או '42' — שניהם עובדים.",
            "parameters": {"type": "OBJECT", "properties": {
                "call_number": {"type": "STRING", "description": "מספר הקריאה, למשל S00042 או 42"},
            }, "required": ["call_number"]},
        },
        {
            "name": "list_technicians",
            "description": "מחזיר רשימת כל הטכנאים הפעילים עם סטטוס זמינות, תפקיד ומספר קריאות פתוחות.",
            "parameters": {"type": "OBJECT", "properties": {
                "available_only": {"type": "BOOLEAN", "description": "אם True — רק טכנאים זמינים כרגע"},
            }, "required": []},
        },
        {
            "name": "search_customers",
            "description": "חפש לקוחות לפי שם, טלפון, עיר או איש קשר. מחזיר פרטי לקוח ורשימת מעליות.",
            "parameters": {"type": "OBJECT", "properties": {
                "query": {"type": "STRING", "description": "מחרוזת חיפוש — שם לקוח, עיר, טלפון"},
            }, "required": ["query"]},
        },
        {
            "name": "get_management_company_info",
            "description": "מחזיר פרטי חברת ניהול — טלפון, איש קשר, כמה מעליות, מספרי טלפון מוכרים.",
            "parameters": {"type": "OBJECT", "properties": {
                "name": {"type": "STRING", "description": "שם חברת הניהול (חיפוש חלקי)"},
            }, "required": ["name"]},
        },
        {
            "name": "get_elevator_inspections",
            "description": "מחזיר דוחות בדיקה תקופתית עבור מעלית — תאריך, תוצאה (עבר/נכשל), ליקויים.",
            "parameters": {"type": "OBJECT", "properties": {
                "elevator_id": {"type": "STRING", "description": "UUID של המעלית"},
                "limit": {"type": "INTEGER", "description": "מספר דוחות אחרונים (ברירת מחדל: 5)"},
            }, "required": ["elevator_id"]},
        },
        {
            "name": "get_upcoming_maintenance",
            "description": "מחזיר תחזוקות מתוכננות או באיחור — מי צריך ביקור קרוב, מה עבר את התאריך.",
            "parameters": {"type": "OBJECT", "properties": {
                "days_ahead": {"type": "INTEGER", "description": "כמה ימים קדימה לבדוק (ברירת מחדל: 14)"},
                "overdue_only": {"type": "BOOLEAN", "description": "אם True — רק תחזוקות שעברו את התאריך"},
            }, "required": []},
        },
        {
            "name": "get_pending_unmatched_calls",
            "description": "מחזיר קריאות שנכנסו ממוקד/מייל ולא שויכו אוטומטית למעלית — ממתינות לטיפול ידני.",
            "parameters": {"type": "OBJECT", "properties": {
                "limit": {"type": "INTEGER", "description": "מספר תוצאות מקסימלי (ברירת מחדל: 10)"},
            }, "required": []},
        },
        {
            "name": "get_document_analysis",
            "description": "מחזיר ניתוח AI של חוזים/הסכמי שירות/תסקירים שהועלו למערכת עבור מעלית, פרויקט, חוזה, ליד או לקוח. מכיל סיכום, שדות שחולצו ושדות שעודכנו אוטומטית.",
            "parameters": {"type": "OBJECT", "properties": {
                "entity_type": {"type": "STRING", "description": "ELEVATOR|PROJECT|CONTRACT|LEAD|CUSTOMER"},
                "entity_id": {"type": "STRING", "description": "UUID של הישות"},
            }, "required": ["entity_type", "entity_id"]},
        },
    ]
}]

_GEMINI_PRIMARY = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_GEMINI_FALLBACK = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
_GEMINI_URL = _GEMINI_PRIMARY


# ── DB query functions (called when Claude invokes a tool) ────────────────────

def _search_elevators(db: Session, query: str = "", city: str = "", limit: int = 20) -> list[dict]:
    q = db.query(Elevator)
    if city:
        q = q.filter(Elevator.city.ilike(f"%{city}%"))
    if query:
        q = q.filter(
            Elevator.address.ilike(f"%{query}%")
            | Elevator.city.ilike(f"%{query}%")
            | Elevator.building_name.ilike(f"%{query}%")
            | Elevator.serial_number.ilike(f"%{query}%")
        )
    if not query and not city:
        return [{"שגיאה": "יש לציין query או city לחיפוש"}]
    total = q.count()
    elevators = q.order_by(Elevator.address).limit(limit).all()
    result = [
        {
            "id": str(e.id),
            "address": e.address,
            "city": e.city,
            "building_name": e.building_name or "",
            "serial_number": e.serial_number or "",
            "status": e.status,
            "risk_score": e.risk_score,
            "last_service_date": e.last_service_date.strftime("%d/%m/%Y") if e.last_service_date else None,
            "next_service_date": e.next_service_date.strftime("%d/%m/%Y") if e.next_service_date else None,
        }
        for e in elevators
    ]
    if total > limit:
        result.append({"הערה": f"מוצגות {len(elevators)} מתוך {total} — הגדל את limit לקבלת כולן"})
    return result


def _get_elevator_calls(db: Session, elevator_id: str, limit: int = 10) -> list[dict]:
    import uuid as _uuid
    try:
        eid = _uuid.UUID(elevator_id)
    except ValueError:
        return [{"error": "מזהה מעלית לא תקין"}]

    calls = (
        db.query(ServiceCall)
        .filter(ServiceCall.elevator_id == eid)
        .order_by(ServiceCall.created_at.desc())
        .limit(limit)
        .all()
    )

    _FAULT_HE = {
        "STUCK": "מעלית תקועה", "DOOR": "תקלת דלת", "ELECTRICAL": "חשמלית",
        "MECHANICAL": "מכנית", "SOFTWARE": "תוכנה", "OTHER": "כללית",
    }
    _STATUS_HE = {
        "OPEN": "פתוח", "ASSIGNED": "שובץ", "IN_PROGRESS": "בטיפול",
        "RESOLVED": "טופל", "CLOSED": "סגור",
    }

    result = []
    for c in calls:
        assignment = (
            db.query(Assignment)
            .filter(Assignment.service_call_id == c.id,
                    Assignment.status.in_(["CONFIRMED", "COMPLETED", "REJECTED"]))
            .order_by(Assignment.assigned_at.desc())
            .first()
        )
        tech_name = None
        if assignment:
            tech = db.query(Technician).filter(Technician.id == assignment.technician_id).first()
            tech_name = tech.name if tech else None

        result.append({
            "תאריך": c.created_at.strftime("%d/%m/%Y %H:%M") if c.created_at else "",
            "סוג_תקלה": _FAULT_HE.get(c.fault_type, c.fault_type),
            "עדיפות": c.priority,
            "סטטוס": _STATUS_HE.get(c.status, c.status),
            "מדווח": c.reported_by or "",
            "טכנאי": tech_name or "לא שובץ",
            "תיאור": c.description or "",
            "הערות_סגירה": c.resolution_notes or "",
            "זמן_טיפול_שעות": (
                round((c.resolved_at - c.created_at).total_seconds() / 3600, 1)
                if c.resolved_at and c.created_at else None
            ),
        })
    return result


def _get_recent_calls(
    db: Session,
    days: int = 7,
    status: str | None = None,
    city: str | None = None,
    technician_name: str | None = None,
    limit: int = 15,
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = db.query(ServiceCall).filter(ServiceCall.created_at >= since)

    if status:
        query = query.filter(ServiceCall.status == status.upper())

    calls = query.order_by(ServiceCall.created_at.desc()).all()

    result = []
    for c in calls:
        elevator = db.query(Elevator).filter(Elevator.id == c.elevator_id).first()

        # City filter
        if city and elevator and city.lower() not in (elevator.city or "").lower():
            continue

        # Technician filter
        tech_name_found = None
        if technician_name:
            assignment = (
                db.query(Assignment)
                .join(Technician, Assignment.technician_id == Technician.id)
                .filter(
                    Assignment.service_call_id == c.id,
                    Technician.name.ilike(f"%{technician_name}%"),
                )
                .first()
            )
            if not assignment:
                continue
            tech = db.query(Technician).filter(Technician.id == assignment.technician_id).first()
            tech_name_found = tech.name if tech else None
        else:
            assignment = (
                db.query(Assignment)
                .filter(Assignment.service_call_id == c.id,
                        Assignment.status.in_(["CONFIRMED", "COMPLETED"]))
                .first()
            )
            if assignment:
                tech = db.query(Technician).filter(Technician.id == assignment.technician_id).first()
                tech_name_found = tech.name if tech else None

        result.append({
            "תאריך": c.created_at.strftime("%d/%m/%Y %H:%M") if c.created_at else "",
            "כתובת": f"{elevator.address}, {elevator.city}" if elevator else "לא ידוע",
            "בניין": elevator.building_name or "" if elevator else "",
            "סוג_תקלה": c.fault_type,
            "עדיפות": c.priority,
            "סטטוס": c.status,
            "טכנאי": tech_name_found or "לא שובץ",
            "תיאור": c.description or "",
        })

        if len(result) >= limit:
            break

    return result


def _get_technician_info(db: Session, name: str) -> dict:
    tech = (
        db.query(Technician)
        .filter(Technician.name.ilike(f"%{name}%"))
        .first()
    )
    if not tech:
        return {"error": f"לא נמצא טכנאי בשם '{name}'"}

    open_assignments = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"]),
        )
        .all()
    )

    open_calls = []
    for a in open_assignments:
        call = db.query(ServiceCall).filter(ServiceCall.id == a.service_call_id).first()
        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first() if call else None
        open_calls.append({
            "כתובת": f"{elevator.address}, {elevator.city}" if elevator else "לא ידוע",
            "סטטוס": a.status,
            "זמן_נסיעה": f"{a.travel_minutes} דק'" if a.travel_minutes else "",
        })

    return {
        "שם": tech.name,
        "טלפון": tech.phone or "",
        "התמחות": ", ".join(tech.specializations) if tech.specializations else "",
        "פעיל": tech.is_active,
        "קריאות_פתוחות": open_calls,
        "מיקום_נוכחי": (
            f"{tech.current_latitude:.4f}, {tech.current_longitude:.4f}"
            if tech.current_latitude and tech.current_longitude else "לא ידוע"
        ),
    }


def _get_elevator_maintenance(db: Session, elevator_id: str) -> list[dict]:
    import uuid as _uuid
    try:
        eid = _uuid.UUID(elevator_id)
    except ValueError:
        return [{"error": "מזהה לא תקין"}]

    records = (
        db.query(MaintenanceRecord)
        .filter(MaintenanceRecord.elevator_id == eid)
        .order_by(MaintenanceRecord.scheduled_date.desc())
        .limit(10)
        .all()
    )

    return [
        {
            "תאריך_מתוכנן": r.scheduled_date.strftime("%d/%m/%Y") if r.scheduled_date else "",
            "תאריך_ביצוע": r.completed_date.strftime("%d/%m/%Y") if r.completed_date else "טרם בוצע",
            "סטטוס": r.status,
            "טכנאי": r.technician_name or "",
            "הערות": r.notes or "",
        }
        for r in records
    ]


def _get_technician_location(db: Session, technician_name: str | None = None, near_address: str | None = None) -> dict:
    techs = db.query(Technician).filter(Technician.is_active == True).all()  # noqa: E712
    results = []
    for t in techs:
        if technician_name and technician_name.lower() not in t.name.lower():
            continue
        # Prefer live location, fall back to base location
        lat = t.current_latitude or t.base_latitude
        lng = t.current_longitude or t.base_longitude
        is_live = bool(t.current_latitude and t.current_longitude)
        if lat and lng:
            results.append({
                "שם": t.name,
                "קו_רוחב": lat,
                "קו_אורך": lng,
                "סוג_מיקום": "חי" if is_live else "מיקום_בסיס",
                "קישור_מפה": f"https://maps.google.com/?q={lat},{lng}",
                "זמין": t.is_available,
            })
        else:
            if not technician_name:
                continue  # Skip techs with no location when doing general query
            results.append({"שם": t.name, "מיקום": "לא הוגדר מיקום"})
    if not results:
        return {"תוצאה": "לא נמצא מיקום זמין — ודא שהוגדר מיקום בסיס לטכנאים בדשבורד"}
    return {"טכנאים": results}


def _search_by_phone(db: Session, phone: str) -> list[dict]:
    """Find elevators associated with a given caller phone number."""
    from app.models.elevator import Elevator
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    last9 = digits[-9:] if len(digits) >= 9 else digits
    if not last9:
        return [{"error": "מספר טלפון לא תקין"}]

    all_elevs = db.query(Elevator).all()
    results = []
    for e in all_elevs:
        for cp in (e.caller_phones or []):
            cp_d = "".join(c for c in cp if c.isdigit())
            if cp_d[-9:] == last9:
                results.append({
                    "id": str(e.id),
                    "כתובת": f"{e.address}, {e.city}",
                    "בניין": e.building_name or "",
                    "סטטוס": e.status,
                })
                break
    if not results:
        return [{"תוצאה": f"לא נמצאו מעליות עם מספר {phone}"}]
    return results


def _get_system_summary(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    open_calls   = db.query(ServiceCall).filter(ServiceCall.status == "OPEN").count()
    in_progress  = db.query(ServiceCall).filter(ServiceCall.status == "IN_PROGRESS").count()
    today_calls  = db.query(ServiceCall).filter(ServiceCall.created_at >= today_start).count()
    active_techs = db.query(Technician).filter(Technician.is_active == True).count()  # noqa

    closed_today = (
        db.query(ServiceCall)
        .filter(ServiceCall.status.in_(["RESOLVED", "CLOSED"]), ServiceCall.updated_at >= today_start)
        .all()
    )
    closers: dict[str, int] = {}
    for c in closed_today:
        name = c.resolved_by or "לא ידוע"
        closers[name] = closers.get(name, 0) + 1

    return {
        "קריאות_פתוחות": open_calls,
        "קריאות_בטיפול": in_progress,
        "קריאות_היום": today_calls,
        "נסגרו_היום": len(closed_today),
        "סגרו_היום": closers,
        "טכנאים_פעילים": active_techs,
        "שעה_נוכחית": now.strftime("%d/%m/%Y %H:%M"),
    }


# ── Write-action DB functions ─────────────────────────────────────────────────

def _close_service_call(db: Session, call_id: str, resolution_notes: str) -> dict:
    """Close a service call and save resolution notes."""
    import uuid as _uuid
    try:
        cid = _uuid.UUID(call_id)
    except ValueError:
        return {"error": "מזהה קריאה לא תקין"}
    call = db.query(ServiceCall).filter(ServiceCall.id == cid).first()
    if not call:
        return {"error": "הקריאה לא נמצאה"}
    if call.status in ("CLOSED", "RESOLVED"):
        return {"error": f"הקריאה כבר במצב {call.status}"}
    call.status = "CLOSED"
    call.resolution_notes = resolution_notes
    call.resolved_at = datetime.now(timezone.utc)
    db.commit()

    # Find the technician and send updated route
    from app.models.assignment import Assignment
    from app.services.route_service import send_route_to_technician
    # Find active assignment to notify the tech
    assignment = db.query(Assignment).filter(
        Assignment.service_call_id == cid,
        Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"])
    ).first()
    if assignment:
        tech = db.query(Technician).filter(Technician.id == assignment.technician_id).first()
        if tech:
            send_route_to_technician(db, tech)

    return {"success": True, "call_number": call.call_number, "status": "CLOSED"}


def _assign_service_call(db: Session, call_id: str, technician_name: str) -> dict:
    """Reassign a service call to a different technician."""
    import uuid as _uuid
    try:
        cid = _uuid.UUID(call_id)
    except ValueError:
        return {"error": "מזהה קריאה לא תקין"}
    call = db.query(ServiceCall).filter(ServiceCall.id == cid).first()
    if not call:
        return {"error": "הקריאה לא נמצאה"}
    tech = db.query(Technician).filter(Technician.name.ilike(f"%{technician_name}%")).first()
    if not tech:
        return {"error": f"הטכנאי '{technician_name}' לא נמצא במערכת"}
    # Update existing active assignment or create new one
    from app.models.assignment import Assignment
    existing = (
        db.query(Assignment)
        .filter(Assignment.service_call_id == cid,
                Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"]))
        .first()
    )
    if existing:
        existing.technician_id = tech.id
        existing.status = "CONFIRMED"
    else:
        new_assign = Assignment(
            service_call_id=cid,
            technician_id=tech.id,
            assignment_type="MANUAL",
            status="CONFIRMED",
        )
        db.add(new_assign)
    call.status = "ASSIGNED"
    db.commit()

    # Send updated route to the newly assigned technician
    from app.services.route_service import send_route_to_technician
    send_route_to_technician(db, tech)

    return {"success": True, "call_number": call.call_number, "assigned_to": tech.name}


def _transfer_to_quote(db: Session, call_id: str, notes: str = "") -> dict:
    """Mark a service call as requiring a quote."""
    import uuid as _uuid
    try:
        cid = _uuid.UUID(call_id)
    except ValueError:
        return {"error": "מזהה קריאה לא תקין"}
    call = db.query(ServiceCall).filter(ServiceCall.id == cid).first()
    if not call:
        return {"error": "הקריאה לא נמצאה"}
    call.quote_needed = True
    if notes:
        existing = call.resolution_notes or ""
        call.resolution_notes = f"{existing}\n[הצעת מחיר]: {notes}".strip()
    db.commit()
    return {"success": True, "call_number": call.call_number, "quote_needed": True}


def _get_technician_route(db: Session, technician_name: str) -> dict:
    """Return open assigned calls for a technician, ordered as a work route."""
    from app.models.assignment import Assignment
    tech = db.query(Technician).filter(Technician.name.ilike(f"%{technician_name}%")).first()
    if not tech:
        return {"error": f"הטכנאי '{technician_name}' לא נמצא"}
    assignments = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id,
                Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"]))
        .all()
    )
    route = []
    for a in assignments:
        call = db.query(ServiceCall).filter(
            ServiceCall.id == a.service_call_id,
            ServiceCall.status.notin_(["CLOSED", "RESOLVED"])
        ).first()
        if not call:
            continue
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        route.append({
            "מספר_קריאה": call.call_number or str(call.id)[:8],
            "כתובת": f"{elev.address}, {elev.city}" if elev else "לא ידוע",
            "בניין": elev.building_name or "" if elev else "",
            "עדיפות": call.priority,
            "סטטוס": call.status,
            "תיאור": call.description[:80] if call.description else "",
            "תאריך_פתיחה": call.created_at.strftime("%d/%m %H:%M") if call.created_at else "",
        })
    route.sort(key=lambda x: ("CRITICAL" not in x["עדיפות"], "HIGH" not in x["עדיפות"]))
    return {"טכנאי": tech.name, "קריאות": route, "סה_כ": len(route)}


def _get_my_calls(db: Session, phone: str) -> dict:
    """Return open calls assigned to the technician identified by phone."""
    from app.models.assignment import Assignment
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    last9 = digits[-9:]
    tech = (
        db.query(Technician)
        .filter((Technician.phone.contains(last9)) | (Technician.whatsapp_number.contains(last9)))
        .first()
    )
    if not tech:
        return {"error": "לא נמצא טכנאי מקושר למספר הטלפון הזה"}
    return _get_technician_route(db, tech.name)


def _get_call_by_number(db: Session, call_number_str: str) -> dict:
    """Lookup a service call by its number (accepts 'S00042' or '42')."""
    raw = call_number_str.strip().upper().lstrip("S").lstrip("0") or "0"
    try:
        num = int(raw)
    except ValueError:
        return {"error": f"מספר קריאה לא תקין: {call_number_str}"}
    call = db.query(ServiceCall).filter(ServiceCall.call_number == num).first()
    if not call:
        return {"error": f"לא נמצאה קריאה מספר {call_number_str}"}
    elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    tech = None
    asgn = (
        db.query(Assignment)
        .filter(Assignment.service_call_id == call.id, Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION", "AUTO_ASSIGNED"]))
        .order_by(Assignment.created_at.desc())
        .first()
    )
    if asgn:
        t = db.query(Technician).filter(Technician.id == asgn.technician_id).first()
        tech = t.name if t else None
    return {
        "מספר_קריאה": f"S{call.call_number:05d}" if call.call_number else None,
        "כתובת": f"{elev.address}, {elev.city}" if elev else "לא ידוע",
        "סטטוס": call.status,
        "עדיפות": call.priority,
        "סוג_תקלה": call.fault_type,
        "תיאור": call.description,
        "מדווח_ע_י": call.reported_by,
        "טכנאי_משובץ": tech,
        "הערות_פתרון": call.resolution_notes,
        "נפתחה": call.created_at.strftime("%d/%m/%Y %H:%M") if call.created_at else None,
    }


def _list_technicians(db: Session, available_only: bool = False) -> list:
    """Return all active technicians with availability and open call count."""
    q = db.query(Technician).filter(Technician.is_active == True)  # noqa
    if available_only:
        q = q.filter(Technician.is_available == True)  # noqa
    techs = q.order_by(Technician.name).all()
    result = []
    for t in techs:
        open_count = (
            db.query(Assignment)
            .join(ServiceCall, Assignment.service_call_id == ServiceCall.id)
            .filter(Assignment.technician_id == t.id, ServiceCall.status.in_(["OPEN", "ASSIGNED", "IN_PROGRESS"]))
            .count()
        )
        result.append({
            "שם": t.name,
            "טלפון": t.phone,
            "תפקיד": t.role,
            "זמין": t.is_available,
            "בכוננות": t.is_on_call,
            "קריאות_פתוחות": open_count,
        })
    return result


def _search_customers(db: Session, query: str) -> list:
    """Search customers by name, phone, city or contact person."""
    q = f"%{query}%"
    customers = (
        db.query(Customer)
        .filter(
            Customer.is_active == True,  # noqa
            (Customer.name.ilike(q)) | (Customer.phone.ilike(q)) |
            (Customer.city.ilike(q)) | (Customer.contact_person.ilike(q)),
        )
        .limit(8)
        .all()
    )
    result = []
    for c in customers:
        elev_count = db.query(Elevator).filter(Elevator.customer_id == c.id).count()
        result.append({
            "שם": c.name,
            "סוג": c.customer_type,
            "טלפון": c.phone,
            "עיר": c.city,
            "איש_קשר": c.contact_person,
            "מעליות": elev_count,
        })
    return result or [{"תוצאה": "לא נמצאו לקוחות תואמים"}]


def _get_management_company_info(db: Session, name: str) -> list:
    """Return management company details matching the name."""
    companies = (
        db.query(ManagementCompany)
        .filter(ManagementCompany.name.ilike(f"%{name}%"))
        .limit(5)
        .all()
    )
    result = []
    for c in companies:
        elev_count = db.query(Elevator).filter(Elevator.management_company_id == c.id).count()
        result.append({
            "שם": c.name,
            "איש_קשר": c.contact_name,
            "טלפון": c.phone,
            "אימייל": c.email,
            "טלפונים_מוכרים": c.caller_phones,
            "מעליות_בניהול": elev_count,
        })
    return result or [{"תוצאה": "לא נמצאה חברת ניהול תואמת"}]


def _get_elevator_inspections(db: Session, elevator_id: str, limit: int = 5) -> list:
    """Return recent inspection reports for an elevator."""
    import uuid as _uuid
    try:
        eid = _uuid.UUID(elevator_id)
    except ValueError:
        return [{"error": "מזהה מעלית לא תקין"}]
    reports = (
        db.query(InspectionReport)
        .filter(InspectionReport.elevator_id == eid)
        .order_by(InspectionReport.inspection_date.desc())
        .limit(limit)
        .all()
    )
    if not reports:
        return [{"תוצאה": "אין דוחות בדיקה לעלית זו"}]
    result = []
    for r in reports:
        result.append({
            "תאריך": r.inspection_date.strftime("%d/%m/%Y") if r.inspection_date else None,
            "תוצאה": "עבר" if r.result == "PASS" else ("נכשל" if r.result == "FAIL" else "לא ידוע"),
            "בודק": r.inspector_name,
            "ליקויים": r.deficiency_count,
            "סטטוס_דוח": r.report_status,
            "מספר_תיק": r.labor_file_number,
        })
    return result


def _get_upcoming_maintenance(db: Session, days_ahead: int = 14, overdue_only: bool = False) -> list:
    """Return upcoming or overdue maintenance schedules."""
    now = datetime.now(timezone.utc).date()
    future = now + timedelta(days=days_ahead)
    q = db.query(MaintenanceRecord)
    if overdue_only:
        q = q.filter(MaintenanceRecord.status == "OVERDUE")
    else:
        q = q.filter(
            MaintenanceRecord.status.in_(["SCHEDULED", "OVERDUE"]),
            MaintenanceRecord.scheduled_date <= future,
        )
    records = q.order_by(MaintenanceRecord.scheduled_date).limit(20).all()
    if not records:
        return [{"תוצאה": "אין תחזוקות ממתינות בטווח הזמן הזה"}]
    result = []
    for r in records:
        elev = db.query(Elevator).filter(Elevator.id == r.elevator_id).first()
        tech = db.query(Technician).filter(Technician.id == r.technician_id).first() if r.technician_id else None
        result.append({
            "כתובת": f"{elev.address}, {elev.city}" if elev else "לא ידוע",
            "תאריך_מתוכנן": r.scheduled_date.strftime("%d/%m/%Y") if r.scheduled_date else None,
            "סוג": r.maintenance_type,
            "סטטוס": r.status,
            "טכנאי": tech.name if tech else None,
        })
    return result


def _get_document_analysis(db: Session, entity_type: str, entity_id: str) -> list:
    """Return AI document analyses for a given entity."""
    try:
        from app.models.document_analysis import DocumentAnalysis
        import uuid as _uuid
        eid = _uuid.UUID(entity_id)
        records = (
            db.query(DocumentAnalysis)
            .filter(
                DocumentAnalysis.entity_type == entity_type.upper(),
                DocumentAnalysis.entity_id == eid,
                DocumentAnalysis.status == "PROCESSED",
            )
            .order_by(DocumentAnalysis.created_at.desc())
            .limit(5)
            .all()
        )
        if not records:
            return [{"תוצאה": "אין מסמכים מנותחים עבור ישות זו"}]
        return [
            {
                "קובץ": r.filename,
                "סוג_מסמך": r.document_type or "לא ידוע",
                "סיכום": r.summary_text or "",
                "שדות_שמולאו_אוטו": list((r.auto_filled or {}).keys()),
                "תאריך_העלאה": r.created_at.strftime("%d/%m/%Y") if r.created_at else None,
                "נתונים_מחולצים": r.extracted_data or {},
            }
            for r in records
        ]
    except Exception as exc:
        return [{"שגיאה": str(exc)}]


def _get_pending_unmatched_calls(db: Session, limit: int = 10) -> list:
    """Return unmatched incoming calls awaiting manual elevator assignment."""
    logs = (
        db.query(IncomingCallLog)
        .filter(IncomingCallLog.match_status.in_(["UNMATCHED", "PARTIAL"]))
        .order_by(IncomingCallLog.created_at.desc())
        .limit(limit)
        .all()
    )
    if not logs:
        return [{"תוצאה": "אין קריאות ממתינות לשיוך"}]
    result = []
    for lg in logs:
        result.append({
            "כתובת": f"{lg.call_street or ''}, {lg.call_city or ''}".strip(", "),
            "סוג_תקלה": lg.fault_type,
            "עדיפות": lg.priority,
            "מתקשר": lg.caller_name or lg.caller_phone,
            "סטטוס_התאמה": "התאמה חלקית" if lg.match_status == "PARTIAL" else "לא זוהה",
            "נכנסה": lg.created_at.strftime("%d/%m/%Y %H:%M") if lg.created_at else None,
        })
    return result


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _run_tool(db: Session, tool_name: str, tool_input: dict) -> Any:
    """Execute a tool call from Claude and return the result."""
    if tool_name == "search_elevators":
        return _search_elevators(
            db,
            query=tool_input.get("query", ""),
            city=tool_input.get("city", ""),
            limit=tool_input.get("limit", 20),
        )
    elif tool_name == "get_elevator_calls":
        return _get_elevator_calls(db, tool_input["elevator_id"], tool_input.get("limit", 10))
    elif tool_name == "get_recent_calls":
        return _get_recent_calls(
            db,
            days=tool_input.get("days", 7),
            status=tool_input.get("status"),
            city=tool_input.get("city"),
            technician_name=tool_input.get("technician_name"),
            limit=tool_input.get("limit", 15),
        )
    elif tool_name == "get_technician_info":
        return _get_technician_info(db, tool_input["name"])
    elif tool_name == "get_elevator_maintenance":
        return _get_elevator_maintenance(db, tool_input["elevator_id"])
    elif tool_name == "get_system_summary":
        return _get_system_summary(db)
    elif tool_name == "get_technician_location":
        return _get_technician_location(db, tool_input.get("technician_name"), tool_input.get("near_address"))
    elif tool_name == "search_by_phone":
        return _search_by_phone(db, tool_input.get("phone", ""))
    elif tool_name == "close_service_call":
        return _close_service_call(db, tool_input["call_id"], tool_input.get("resolution_notes", ""))
    elif tool_name == "assign_service_call":
        return _assign_service_call(db, tool_input["call_id"], tool_input["technician_name"])
    elif tool_name == "transfer_to_quote":
        return _transfer_to_quote(db, tool_input["call_id"], tool_input.get("notes", ""))
    elif tool_name == "get_technician_route":
        return _get_technician_route(db, tool_input["technician_name"])
    elif tool_name == "get_my_calls":
        return _get_my_calls(db, tool_input.get("phone", ""))
    elif tool_name == "get_call_by_number":
        return _get_call_by_number(db, tool_input.get("call_number", ""))
    elif tool_name == "list_technicians":
        return _list_technicians(db, tool_input.get("available_only", False))
    elif tool_name == "search_customers":
        return _search_customers(db, tool_input.get("query", ""))
    elif tool_name == "get_management_company_info":
        return _get_management_company_info(db, tool_input.get("name", ""))
    elif tool_name == "get_elevator_inspections":
        return _get_elevator_inspections(db, tool_input["elevator_id"], tool_input.get("limit", 5))
    elif tool_name == "get_upcoming_maintenance":
        return _get_upcoming_maintenance(db, tool_input.get("days_ahead", 14), tool_input.get("overdue_only", False))
    elif tool_name == "get_pending_unmatched_calls":
        return _get_pending_unmatched_calls(db, tool_input.get("limit", 10))
    elif tool_name == "get_document_analysis":
        return _get_document_analysis(db, tool_input["entity_type"], tool_input["entity_id"])
    else:
        return {"error": f"כלי לא מוכר: {tool_name}"}


# ── Main chat function ────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """אתה עוזר דיגיטלי זמין לצוות דרך ווצאפ.
יש לך גישה למערכת דרך כלים — מעליות, קריאות שירות, טכנאים, לקוחות, חברות ניהול, בדיקות, תחזוקה וקריאות ממתינות.

השתמש בכלים לשליפת מידע חי. אל תמציא תשובות.
ענה בעברית קצרה וישירה. תאריכים בפורמט DD/MM/YYYY.

══ כלל ריצה מיידית ══
שאלות מידע: קרא כלי → ענה מיד. אל תשאל "האם לבצע?" — פשוט תחפש.
• "רשימת מעליות בעיר X" → search_elevators(city=X, limit=100)
• "הקפץ לי קריאה 42" → get_call_by_number → הצג פרטים
• "מה יש לי היום?" → get_my_calls → הצג רשימה

══ כלל תוצאות חלקיות ══
אם חיפוש מחזיר "מוצגות X מתוך Y" — הרץ שוב עם limit גדול יותר.
אל תאמר "הנה הרשימה" לפני שמשכת את הכל.

══ כלל אישור — לכל פעולה שמשנה נתונים ══
כל פעולה שמשנה, יוצרת או מוחקת נתונים חייבת אישור מפורש לפני הביצוע.
כולל: סגירת קריאה, שיבוץ טכנאי, העברה להצעת מחיר, ועוד.
אישור תקף: כן / לא / 1 / 2 / אישור / ביטול. הודעה עמומה — המתן.
"הקפץ לי" / "הראה לי" / "כמה" / "מתי" / "מי" = מידע בלבד, ללא אישור.

══ כלל הרשאות ══
פרטי ההרשאות של המשתמש יסופקו בהקשר. הצג רק מידע שהתפקיד שלו מורשה לראות.
אם אין לו הרשאה למידע מבוקש — השב: "אין לך הרשאה לצפות במידע זה (תפקידך: [תפקיד])".
אם המשתמש לא זוהה במערכת — התייחס כטכנאי (הרשאות מוגבלות לקריאות שירות בלבד).

אם המשתמש מבקש משהו שאין לך כלי עבורו — ציין: "פעולה זו אינה זמינה כרגע (חסר: [תיאור])"."""


def _load_conversation_history(db: Session, phone: str, limit: int = 10) -> list:
    """
    Load the last N WhatsApp messages for a phone number and format them
    as Gemini conversation turns (user/model roles).
    incoming messages (direction='in') → role 'user'
    outgoing messages (direction='out') → role 'model'
    """
    try:
        from app.models.whatsapp_message import WhatsAppMessage
        msgs = (
            db.query(WhatsAppMessage)
            .filter(WhatsAppMessage.phone == phone)
            .order_by(WhatsAppMessage.timestamp.desc())
            .limit(limit)
            .all()
        )
        msgs = list(reversed(msgs))  # oldest first
        turns = []
        for m in msgs:
            text = m.transcription or m.text
            if not text:
                continue
            role = "user" if m.direction == "in" else "model"
            turns.append({"role": role, "parts": [{"text": text}]})
        # Gemini requires alternating roles — merge consecutive same-role turns
        merged = []
        for turn in turns:
            if merged and merged[-1]["role"] == turn["role"]:
                merged[-1]["parts"][0]["text"] += "\n" + turn["parts"][0]["text"]
            else:
                merged.append(turn)
        return merged
    except Exception as exc:
        logger.warning("Could not load conversation history: %s", exc)
        return []


def _load_qa_context(db: Session, question: str, limit: int = 5) -> str:
    """Return a block of relevant Q&A pairs to prepend to the system prompt."""
    try:
        from app.models.bot_qa import BotQA
        from sqlalchemy import or_
        words = [w for w in question.split() if len(w) > 2][:6]
        if not words:
            return ""
        filters = [BotQA.question.ilike(f"%{w}%") for w in words]
        pairs = (
            db.query(BotQA)
            .filter(BotQA.active == True, or_(*filters))
            .order_by(BotQA.use_count.desc())
            .limit(limit)
            .all()
        )
        if not pairs:
            return ""
        lines = ["══ דוגמאות מהניסיון (QA) ══"]
        for p in pairs:
            lines.append(f"ש: {p.question}\nת: {p.answer}")
            p.use_count = (p.use_count or 0) + 1
        db.commit()
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("Could not load bot QA context: %s", exc)
        return ""


def _get_caller_role(db: Session, phone: str) -> tuple:
    """Return (role, permissions_dict) for a caller identified by WhatsApp phone."""
    from app.models.technician import Technician
    from app.routers.settings import _DEFAULT_ROLE_PERMISSIONS

    normalized = phone.strip().lstrip("+")
    tech = None
    for candidate in [phone, normalized, f"+{normalized}"]:
        tech = db.query(Technician).filter(
            (Technician.phone == candidate) | (Technician.whatsapp_number == candidate)
        ).first()
        if tech:
            break

    role = tech.role if tech else "TECHNICIAN"
    perms = _DEFAULT_ROLE_PERMISSIONS.get(role, _DEFAULT_ROLE_PERMISSIONS.get("TECHNICIAN", {}))
    return role, perms, tech.name if tech else None


def _build_role_context(role: str, perms: dict, name: str | None) -> str:
    """Format role and permissions as system prompt context."""
    perm_lines = []
    label_map = {
        "service_calls": "קריאות שירות",
        "invoices": "חשבוניות",
        "inventory": "מלאי",
        "crm": "CRM / לקוחות",
        "hr": "משאבי אנוש",
        "reports": "דוחות",
        "settings": "הגדרות",
        "users": "ניהול משתמשים",
    }
    action_map = {
        "view": "צפייה", "create": "יצירה", "assign": "שיבוץ",
        "close": "סגירה", "delete": "מחיקה", "send": "שליחה",
        "mark_paid": "סימון שולם", "manage": "ניהול",
        "purchase_orders": "הזמנות רכש", "export": "ייצוא",
        "edit": "עריכה", "assign_roles": "שינוי תפקידים",
    }
    for module, actions in perms.items():
        hebrew_actions = [action_map.get(a, a) for a in actions]
        perm_lines.append(f"  • {label_map.get(module, module)}: {', '.join(hebrew_actions)}")

    lines = [f"══ פרטי המשתמש ══", f"תפקיד: {role}"]
    if name:
        lines.insert(1, f"שם: {name}")
    lines.append("הרשאות:")
    lines.extend(perm_lines)
    return "\n".join(lines)


def answer_question(db: Session, question: str, asker_name: str = "טכנאי", phone: str = "", with_history: bool = False) -> str:
    """
    Answer a free-text Hebrew question about the system using Gemini + tool use.

    Args:
        db:           Database session
        question:     The question text from WhatsApp
        asker_name:   Name of the technician/manager asking
        phone:        Sender's phone number (used to load conversation history)
        with_history: Whether to load conversation history (True only for quoted/reply messages)

    Returns:
        Hebrew answer string to send back via WhatsApp
    """
    from app.config import get_settings
    s = get_settings()

    # Always load recent conversation history to maintain fluid conversation
    history = _load_conversation_history(db, phone) if phone else []

    # Append current question; if history ends with user-role we merge
    current = {"role": "user", "parts": [{"text": f"{asker_name} שואל: {question}"}]}
    if history and history[-1]["role"] == "user":
        history[-1]["parts"][0]["text"] += "\n" + current["parts"][0]["text"]
        contents = history
    else:
        contents = history + [current]

    # Inject relevant Q&A pairs into system prompt
    qa_ctx = _load_qa_context(db, question)

    # Build role-based permission context
    role_ctx = ""
    if phone:
        try:
            role, perms, tech_name = _get_caller_role(db, phone)
            role_ctx = _build_role_context(role, perms, tech_name)
        except Exception:
            pass

    extra = "\n\n".join(filter(None, [role_ctx, qa_ctx]))

    # Try Gemini first (with tool use), fall back to Anthropic if unavailable
    if s.gemini_api_key:
        try:
            return _answer_gemini(db, s, contents, extra_system=extra)
        except Exception as exc:
            logger.warning("Gemini unavailable (%s) — trying Anthropic fallback", exc)

    if s.anthropic_api_key:
        try:
            return _answer_anthropic(s, question, asker_name, db=db, extra_system=extra)
        except Exception as exc:
            logger.warning("Anthropic fallback also failed: %s", exc)

    return "השירות אינו זמין כרגע — נסה שוב בעוד מספר דקות."


def _answer_gemini(db, s, contents: list, extra_system: str = "") -> str:
    """Run the Gemini tool-use loop and return Hebrew answer."""
    system_text = _SYSTEM_PROMPT + ("\n\n" + extra_system if extra_system else "")
    with httpx.Client(timeout=30) as client:
        for _iteration in range(6):
            payload = {
                "system_instruction": {"parts": [{"text": system_text}]},
                "tools": _GEMINI_TOOLS,
                "contents": contents,
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1200},
            }
            for url in (_GEMINI_PRIMARY, _GEMINI_FALLBACK):
                resp = client.post(f"{url}?key={s.gemini_api_key}", json=payload)
                if resp.status_code not in (429, 503):
                    break
                logger.warning("Gemini %s returned %s, trying fallback model", url, resp.status_code)
            if not resp.is_success:
                raise httpx.HTTPStatusError(f"Gemini {resp.status_code}", request=resp.request, response=resp)

            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            fn_calls = [p["functionCall"] for p in parts if "functionCall" in p]

            if not fn_calls:
                for p in parts:
                    if "text" in p and p["text"]:
                        return p["text"].strip()
                return "לא הצלחתי לעבד את השאלה."

            contents.append({"role": "model", "parts": parts})
            fn_responses = []
            for fn_call in fn_calls:
                name = fn_call["name"]
                args = fn_call.get("args", {})
                logger.warning("🔧 Gemini tool: %s(%s)", name, args)
                result = _run_tool(db, name, args)
                fn_responses.append({
                    "functionResponse": {
                        "name": name,
                        "response": {"result": json.dumps(result, ensure_ascii=False)},
                    }
                })
            contents.append({"role": "user", "parts": fn_responses})

    return "לא הצלחתי לענות על השאלה."


_ANTHROPIC_TOOLS = [
    {
        "name": "search_elevators",
        "description": "חפש מעליות לפי כתובת, עיר, שם בניין או מספר סידורי. כשמחפשים לפי עיר — השתמש ב-limit=100.",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string"},
            "city": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": []},
    },
    {
        "name": "get_elevator_calls",
        "description": "מחזיר היסטוריית קריאות שירות עבור מעלית ספציפית לפי מזהה.",
        "input_schema": {"type": "object", "properties": {
            "elevator_id": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": ["elevator_id"]},
    },
    {
        "name": "get_recent_calls",
        "description": "מחזיר קריאות שירות מהימים האחרונים. ניתן לסנן לפי סטטוס, טכנאי, עיר.",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer"},
            "status": {"type": "string"},
            "city": {"type": "string"},
            "technician_name": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": []},
    },
    {
        "name": "get_technician_info",
        "description": "מחזיר פרטים ומידע על טכנאי.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string"},
        }, "required": ["name"]},
    },
    {
        "name": "get_system_summary",
        "description": "מחזיר סיכום כללי — כמה קריאות נפתחו היום, קריאות פתוחות, קריאות בטיפול, מספר טכנאים פעילים. השתמש לכל שאלה על כמות קריאות, סטטוס כללי או נתוני היום.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_technician_location",
        "description": "מחזיר מיקום נוכחי של טכנאי.",
        "input_schema": {"type": "object", "properties": {
            "technician_name": {"type": "string"},
            "near_address": {"type": "string"},
        }, "required": []},
    },
    {
        "name": "search_by_phone",
        "description": "חפש מעליות לפי מספר טלפון.",
        "input_schema": {"type": "object", "properties": {
            "phone": {"type": "string"},
        }, "required": ["phone"]},
    },
    {
        "name": "close_service_call",
        "description": "סוגר קריאת שירות. השתמש רק לאחר קבלת אישור מפורש.",
        "input_schema": {"type": "object", "properties": {
            "call_id": {"type": "string"},
            "resolution_notes": {"type": "string"},
        }, "required": ["call_id", "resolution_notes"]},
    },
    {
        "name": "assign_service_call",
        "description": "מעביר קריאה לטכנאי אחר. השתמש רק לאחר קבלת אישור מפורש.",
        "input_schema": {"type": "object", "properties": {
            "call_id": {"type": "string"},
            "technician_name": {"type": "string"},
        }, "required": ["call_id", "technician_name"]},
    },
    {
        "name": "transfer_to_quote",
        "description": "מסמן קריאה כדורשת הצעת מחיר. השתמש רק לאחר קבלת אישור מפורש.",
        "input_schema": {"type": "object", "properties": {
            "call_id": {"type": "string"},
            "notes": {"type": "string"},
        }, "required": ["call_id"]},
    },
    {
        "name": "get_technician_route",
        "description": "מחזיר רשימת קריאות פתוחות לטכנאי כמסלול עבודה.",
        "input_schema": {"type": "object", "properties": {
            "technician_name": {"type": "string"},
        }, "required": ["technician_name"]},
    },
    {
        "name": "get_my_calls",
        "description": "מחזיר את הקריאות הפתוחות של הטכנאי שמחזיק בשיחה.",
        "input_schema": {"type": "object", "properties": {
            "phone": {"type": "string"},
        }, "required": ["phone"]},
    },
    {
        "name": "get_call_by_number",
        "description": "מחזיר פרטים מלאים על קריאת שירות לפי מספר קריאה (S00042 או 42).",
        "input_schema": {"type": "object", "properties": {
            "call_number": {"type": "string"},
        }, "required": ["call_number"]},
    },
    {
        "name": "list_technicians",
        "description": "מחזיר רשימת כל הטכנאים הפעילים עם סטטוס זמינות וקריאות פתוחות.",
        "input_schema": {"type": "object", "properties": {
            "available_only": {"type": "boolean"},
        }, "required": []},
    },
    {
        "name": "search_customers",
        "description": "חפש לקוחות לפי שם, טלפון, עיר או איש קשר.",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string"},
        }, "required": ["query"]},
    },
    {
        "name": "get_management_company_info",
        "description": "מחזיר פרטי חברת ניהול — טלפון, איש קשר, מעליות בניהול.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string"},
        }, "required": ["name"]},
    },
    {
        "name": "get_elevator_inspections",
        "description": "מחזיר דוחות בדיקה תקופתית עבור מעלית.",
        "input_schema": {"type": "object", "properties": {
            "elevator_id": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": ["elevator_id"]},
    },
    {
        "name": "get_upcoming_maintenance",
        "description": "מחזיר תחזוקות מתוכננות או באיחור בטווח ימים נתון.",
        "input_schema": {"type": "object", "properties": {
            "days_ahead": {"type": "integer"},
            "overdue_only": {"type": "boolean"},
        }, "required": []},
    },
    {
        "name": "get_pending_unmatched_calls",
        "description": "מחזיר קריאות שנכנסו ולא שויכו למעלית — ממתינות לטיפול ידני.",
        "input_schema": {"type": "object", "properties": {
            "limit": {"type": "integer"},
        }, "required": []},
    },
]


def _answer_anthropic(s, question: str, asker_name: str, db=None, extra_system: str = "") -> str:
    """Fallback: answer via Anthropic Claude with full tool-use DB access."""
    headers = {
        "x-api-key": s.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    messages = [{"role": "user", "content": f"{asker_name} שואל: {question}"}]

    with httpx.Client(timeout=30) as client:
        for _iteration in range(6):
            payload = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 600,
                "system": _SYSTEM_PROMPT + ("\n\n" + extra_system if extra_system else ""),
                "tools": _ANTHROPIC_TOOLS if db else [],
                "messages": messages,
            }
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            # Collect text and tool_use blocks
            tool_uses = [b for b in data["content"] if b["type"] == "tool_use"]
            text_blocks = [b for b in data["content"] if b["type"] == "text"]

            if not tool_uses:
                return text_blocks[0]["text"].strip() if text_blocks else "לא הצלחתי לענות."

            # Execute tools and feed results back
            messages.append({"role": "assistant", "content": data["content"]})
            tool_results = []
            for tu in tool_uses:
                logger.info("🔧 Anthropic tool: %s(%s)", tu["name"], tu["input"])
                result = _run_tool(db, tu["name"], tu["input"]) if db else {"error": "no db"}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
            messages.append({"role": "user", "content": tool_results})

    return "לא הצלחתי לענות על השאלה."
