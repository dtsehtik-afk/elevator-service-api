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

logger = logging.getLogger(__name__)

# ── Tool definitions for Gemini REST API ─────────────────────────────────────

_GEMINI_TOOLS = [{
    "function_declarations": [
        {
            "name": "search_elevators",
            "description": "חפש מעליות לפי כתובת, עיר, שם בניין או מספר סידורי.",
            "parameters": {"type": "OBJECT", "properties": {
                "query": {"type": "STRING", "description": "מחרוזת חיפוש"},
                "limit": {"type": "INTEGER", "description": "מספר תוצאות מקסימלי"},
            }, "required": ["query"]},
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
            "description": "מחזיר סיכום כללי של מצב המערכת — קריאות פתוחות, טכנאים פעילים.",
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
    ]
}]

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


# ── DB query functions (called when Claude invokes a tool) ────────────────────

def _search_elevators(db: Session, query: str, limit: int = 5) -> list[dict]:
    elevators = (
        db.query(Elevator)
        .filter(
            Elevator.address.ilike(f"%{query}%")
            | Elevator.city.ilike(f"%{query}%")
            | Elevator.building_name.ilike(f"%{query}%")
            | Elevator.serial_number.ilike(f"%{query}%")
        )
        .limit(limit)
        .all()
    )
    return [
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

    return {
        "קריאות_פתוחות": open_calls,
        "קריאות_בטיפול": in_progress,
        "קריאות_היום": today_calls,
        "טכנאים_פעילים": active_techs,
        "שעה_נוכחית": now.strftime("%d/%m/%Y %H:%M"),
    }


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _run_tool(db: Session, tool_name: str, tool_input: dict) -> Any:
    """Execute a tool call from Claude and return the result."""
    if tool_name == "search_elevators":
        return _search_elevators(db, tool_input["query"], tool_input.get("limit", 5))
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
    else:
        return {"error": f"כלי לא מוכר: {tool_name}"}


# ── Main chat function ────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """אתה מנהל הלוגיסטיקה החכם של חברת אקורד מעליות.
תפקידך לנהל את המערך השוטף של קריאות השירות — לוודא שהטכנאים מטפלים בקריאות, לענות על שאלותיהם, ולספק מידע מדויק בזמן אמת.

אתה מדבר עם טכנאים ומנהלים דרך ווצאפ — בעברית חמה, ישירה וקצרה.

יש לך גישה לנתונים בזמן אמת:
- קריאות שירות פתוחות, בטיפול וסגורות
- מידע על מעליות לפי כתובת, עיר או בניין
- היסטוריית טיפולים של כל מעלית
- עומס עבודה וזמינות טכנאים
- רשומות תחזוקה תקופתית
- סיכום מצב כולל של המערכת
- מיקום נוכחי של טכנאים (אם שיתפו מיקום)

כללים חמורים:
- ענה קצר וענייני — ווצאפ, לא דוח
- פנה לטכנאי בשמו כשידוע
- אם נשאלת על מעלית ספציפית — חפש אותה קודם בכלים
- תאריכים בפורמט DD/MM/YYYY
- אל תמציא מידע בשום מקרה — השתמש רק בנתונים שהכלים מחזירים
- אם אין לך נתונים או שאינך בטוח — אמור בבירור "אין לי מידע על כך" או "לא מצאתי נתונים"
- עדיף לא לענות מאשר להמציא"""


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

    if not s.gemini_api_key:
        return "❌ שירות השאלות אינו מוגדר (חסר GEMINI_API_KEY)"

    # Load recent conversation history only when this is a reply/quoted message
    history = _load_conversation_history(db, phone) if (phone and with_history) else []

    # Append current question; if history ends with user-role we merge
    current = {"role": "user", "parts": [{"text": f"{asker_name} שואל: {question}"}]}
    if history and history[-1]["role"] == "user":
        history[-1]["parts"][0]["text"] += "\n" + current["parts"][0]["text"]
        contents = history
    else:
        contents = history + [current]

    with httpx.Client(timeout=30) as client:
        for _iteration in range(6):
            payload = {
                "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
                "tools": _GEMINI_TOOLS,
                "contents": contents,
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600},
            }
            resp = client.post(f"{_GEMINI_URL}?key={s.gemini_api_key}", json=payload)
            resp.raise_for_status()
            data = resp.json()

            parts = data["candidates"][0]["content"]["parts"]

            # Collect function calls
            fn_calls = [p["functionCall"] for p in parts if "functionCall" in p]

            if not fn_calls:
                # No tool calls — return text answer
                for p in parts:
                    if "text" in p and p["text"]:
                        return p["text"].strip()
                return "לא הצלחתי לעבד את השאלה."

            # Append model turn
            contents.append({"role": "model", "parts": parts})

            # Execute tools and build response turn
            fn_responses = []
            for fn_call in fn_calls:
                name = fn_call["name"]
                args = fn_call.get("args", {})
                logger.warning("🔧 Chat agent calling tool: %s(%s)", name, args)
                result = _run_tool(db, name, args)
                logger.warning("🔧 Tool result: %s", str(result)[:300])
                fn_responses.append({
                    "functionResponse": {
                        "name": name,
                        "response": {"result": json.dumps(result, ensure_ascii=False)},
                    }
                })

            contents.append({"role": "user", "parts": fn_responses})

    return "לא הצלחתי לענות על השאלה — נסה לנסח אחרת."
