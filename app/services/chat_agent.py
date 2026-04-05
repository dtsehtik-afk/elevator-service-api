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

import anthropic
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.elevator import Elevator
from app.models.maintenance import MaintenanceRecord
from app.models.service_call import ServiceCall
from app.models.technician import Technician

logger = logging.getLogger(__name__)

# ── Tool definitions for Claude ───────────────────────────────────────────────

_TOOLS = [
    {
        "name": "search_elevators",
        "description": (
            "חפש מעליות לפי כתובת, עיר, שם בניין או מספר סידורי. "
            "מחזיר רשימת מעליות תואמות עם פרטים בסיסיים."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "מחרוזת חיפוש — כתובת, שם עיר, שם בניין וכו'",
                },
                "limit": {
                    "type": "integer",
                    "description": "מספר תוצאות מקסימלי (ברירת מחדל: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_elevator_calls",
        "description": (
            "מחזיר היסטוריית קריאות שירות עבור מעלית ספציפית לפי מזהה. "
            "כולל תאריך, סוג תקלה, סטטוס, טכנאי שטיפל והערות סגירה."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "elevator_id": {
                    "type": "string",
                    "description": "UUID של המעלית",
                },
                "limit": {
                    "type": "integer",
                    "description": "מספר קריאות אחרונות להחזיר (ברירת מחדל: 10)",
                    "default": 10,
                },
            },
            "required": ["elevator_id"],
        },
    },
    {
        "name": "get_recent_calls",
        "description": (
            "מחזיר קריאות שירות מהימים האחרונים. "
            "ניתן לסנן לפי סטטוס, טכנאי, עיר."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "כמה ימים אחורה לחפש (ברירת מחדל: 7)",
                    "default": 7,
                },
                "status": {
                    "type": "string",
                    "description": "סנן לפי סטטוס: OPEN, ASSIGNED, IN_PROGRESS, RESOLVED, CLOSED",
                },
                "city": {
                    "type": "string",
                    "description": "סנן לפי עיר",
                },
                "technician_name": {
                    "type": "string",
                    "description": "סנן לפי שם טכנאי",
                },
                "limit": {
                    "type": "integer",
                    "description": "מספר תוצאות מקסימלי",
                    "default": 15,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_technician_info",
        "description": "מחזיר פרטים ומידע על טכנאי — קריאות פתוחות, עומס עבודה.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "שם הטכנאי (חלקי או מלא)",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_elevator_maintenance",
        "description": "מחזיר רשומות תחזוקה תקופתית עבור מעלית.",
        "input_schema": {
            "type": "object",
            "properties": {
                "elevator_id": {
                    "type": "string",
                    "description": "UUID של המעלית",
                },
            },
            "required": ["elevator_id"],
        },
    },
    {
        "name": "get_system_summary",
        "description": "מחזיר סיכום כללי של מצב המערכת — קריאות פתוחות, טכנאים פעילים וכו'.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


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
        "התמחות": tech.specialization or "",
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
    else:
        return {"error": f"כלי לא מוכר: {tool_name}"}


# ── Main chat function ────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """אתה נציג שירות חכם של מערכת ניהול מעליות של חברת אקורד מעליות.
אתה עונה לטכנאים ומנהלים דרך ווצאפ בעברית טבעית, קצרה וברורה.

יש לך גישה לכלים שמאפשרים לך לשאול את מסד הנתונים בזמן אמת:
- חיפוש מעליות לפי כתובת/עיר/שם בניין
- היסטוריית קריאות של מעלית ספציפית
- קריאות אחרונות עם פילטרים שונים
- מידע על טכנאים ועומס עבודה
- רשומות תחזוקה תקופתית
- סיכום מצב המערכת

כללים:
- ענה קצר וענייני — ווצאפ, לא דוח
- אם נשאלת על מעלית ספציפית — תחפש קודם את המעלית
- אם לא מצאת תוצאות — אמור זאת בבירור
- תאריכים בפורמט DD/MM/YYYY
- אל תמציא מידע — השתמש רק בנתונים מהכלים"""


def answer_question(db: Session, question: str, asker_name: str = "טכנאי") -> str:
    """
    Answer a free-text Hebrew question about the system using Claude + tool use.

    Args:
        db:          Database session
        question:    The question text from WhatsApp
        asker_name:  Name of the technician/manager asking

    Returns:
        Hebrew answer string to send back via WhatsApp
    """
    from app.config import get_settings
    s = get_settings()

    if not s.anthropic_api_key:
        return "❌ שירות השאלות אינו מוגדר (חסר ANTHROPIC_API_KEY)"

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    messages = [
        {"role": "user", "content": f"{asker_name} שואל: {question}"}
    ]

    # Agentic loop — Claude may call multiple tools before answering
    for _iteration in range(6):  # max 6 rounds
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",   # fast + cheap
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=_TOOLS,
            messages=messages,
        )

        # If Claude is done — return the text answer
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text.strip()
            return "לא הצלחתי לעבד את השאלה."

        # Claude wants to use tools
        if response.stop_reason == "tool_use":
            # Add Claude's response (with tool calls) to history
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("🔧 Chat agent calling tool: %s(%s)", block.name, block.input)
                    result = _run_tool(db, block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        break  # unexpected stop reason

    return "לא הצלחתי לענות על השאלה — נסה לנסח אחרת."
