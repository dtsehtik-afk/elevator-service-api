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
            "description": "מחזיר את המיקום הנוכחי של טכנאי (אם שיתף מיקום חי). יכול גם למצוא את הטכנאי הקרוב ביותר לאזור מסוים. חובה להשתמש בכלי זה כשנשאלים איפה טכנאי נמצא או מי קרוב.",
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
            "description": "סוגר קריאת שירות ומזין הערות פתרון. השתמש רק לאחר קבלת אישור מפורש מהמשתמש לגבי קריאה ספציפית בודדת. אזהרה חמורה: חל איסור לסגור מספר קריאות ביחד.",
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
            "name": "get_my_confirmed_calls",
            "description": "מחזיר את הקריאות שהטכנאי אישר (לחץ 1 או קיבל ידנית) — לא כולל קריאות שרק נשלחו אליו ולא אושרו. השתמש כשטכנאי שואל 'איזה קריאות אישרתי?' או 'מה שלחתי 1 עליו?'.",
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
            "description": "מחזיר דוחות בדיקה תקופתית עבור מעלית ספציפית — תאריך, תוצאה (עבר/נכשל), ליקויים.",
            "parameters": {"type": "OBJECT", "properties": {
                "elevator_id": {"type": "STRING", "description": "UUID של המעלית"},
                "limit": {"type": "INTEGER", "description": "מספר דוחות אחרונים (ברירת מחדל: 5)"},
            }, "required": ["elevator_id"]},
        },
        {
            "name": "search_inspection_reports",
            "description": "חיפוש דוחות בודק לפי עיר ו/או סטטוס ליקויים. השתמש בכלי זה כאשר שואלים על דוחות בודק בעיר מסוימת, דוחות עם ליקויים פתוחים, או דוחות שדורשים טיפול. לעולם אל תשתמש ב-get_recent_calls לשאלות על דוחות בודק.",
            "parameters": {"type": "OBJECT", "properties": {
                "city": {"type": "STRING", "description": "סינון לפי עיר (חיפוש חלקי)"},
                "has_open_deficiencies": {"type": "BOOLEAN", "description": "אם True — רק דוחות עם ליקויים שטרם טופלו"},
                "limit": {"type": "INTEGER", "description": "מספר תוצאות (ברירת מחדל: 10)"},
            }, "required": []},
        },
        {
            "name": "get_upcoming_maintenance",
            "description": "מחזיר תחזוקות מתוכננות או באיחור — מי צריך ביקור קרוב, מה עבר את התאריך.",
            "parameters": {"type": "OBJECT", "properties": {
                "days_ahead": {"type": "INTEGER", "description": "כמה ימים קדימה לבדוק (ברירת מחדל: 14)"},
                "overdue_only": {"type": "BOOLEAN", "description": "אם True — רק תחזוקות שעברו את התאריך"},
                "city": {"type": "STRING", "description": "סינון לפי עיר ספציפית"},
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
        {
            "name": "take_service_call",
            "description": "טכנאי לוקח על עצמו קריאת שירות פתוחה ומשבץ את עצמו אליה. השתמש כאשר הטכנאי אומר 'לקחתי', 'אני על זה', 'הולך לשם', 'אני מגיע', 'אני לוקח', 'יש לי'. בצע מיד ללא בקשת אישור נוסף.",
            "parameters": {"type": "OBJECT", "properties": {
                "address_hint": {"type": "STRING", "description": "כתובת/עיר/שם בניין של הקריאה מהטקסט"},
                "call_id": {"type": "STRING", "description": "UUID של קריאה ספציפית אם ידוע"},
            }, "required": []},
        },
        {
            "name": "close_my_active_call",
            "description": "סוגר את הקריאה הפעילה של הטכנאי הנוכחי. השתמש כאשר הטכנאי אומר 'סיימתי', 'בוצע', 'טיפלתי', 'סגרתי', 'גמרתי'. חלץ הערות פתרון מהטקסט אם יש. בצע מיד.",
            "parameters": {"type": "OBJECT", "properties": {
                "resolution_notes": {"type": "STRING", "description": "תיאור מה בוצע / הערות סגירה מהטקסט"},
                "quote_needed": {"type": "BOOLEAN", "description": "True אם הטכנאי ציין שנדרשת הצעת מחיר"},
            }, "required": []},
        },
        {
            "name": "get_my_route",
            "description": "מחזיר את המסלול המסודר של הטכנאי כולל קישור ל-Google Maps עם כל העצירות. השתמש כאשר הטכנאי שואל 'מה יש לי', 'שלח מסלול', 'הקריאות שלי', 'סדר יום', 'מסלול על המפה', 'קישור למפה', 'תציג מפה'.",
            "parameters": {"type": "OBJECT", "properties": {}, "required": []},
        },
        {
            "name": "request_call_from_dispatcher",
            "description": "טכנאי מבקש לטפל בקריאה — שולח בקשה לאישור מוקד. השתמש כאשר הטכנאי אומר 'מבקש', 'אשמח לטפל', 'רוצה לטפל'. שונה מ-take_service_call שמשבץ מיד.",
            "parameters": {"type": "OBJECT", "properties": {
                "address_hint": {"type": "STRING", "description": "כתובת/עיר של הקריאה המבוקשת"},
            }, "required": []},
        },
        {
            "name": "mark_call_in_progress",
            "description": "מסמן את הקריאה הפעילה כ'בטיפול'. השתמש כאשר הטכנאי אומר 'התחלתי', 'אני שם', 'מתחיל לטפל'.",
            "parameters": {"type": "OBJECT", "properties": {}, "required": []},
        },
        {
            "name": "create_service_call",
            "description": "פותח קריאת שירות חדשה עבור מעלית מזהה. השתמש רק לאחר קבלת אישור מפורש מהמשתמש לפתוח את הקריאה לכתובת הרלוונטית.",
            "parameters": {"type": "OBJECT", "properties": {
                "elevator_id": {"type": "STRING", "description": "UUID של המעלית"},
                "reported_by": {"type": "STRING", "description": "שם/טלפון של המדווח (אם ידוע)"},
                "description": {"type": "STRING", "description": "תיאור התקלה"},
                "priority": {"type": "STRING", "description": "עדיפות: LOW/MEDIUM/HIGH/CRITICAL"},
                "fault_type": {"type": "STRING", "description": "סוג: STUCK/DOOR/ELECTRICAL/MECHANICAL/SOFTWARE/OTHER"},
            }, "required": ["elevator_id", "description"]},
        },
        {
            "name": "match_unmatched_call_to_elevator",
            "description": "משייך קריאה ממתינה שלא זוהתה למעלית ספציפית ומייצר ממנה קריאת שירות. השתמש רק לאחר אישור מהמשתמש.",
            "parameters": {"type": "OBJECT", "properties": {
                "incoming_call_id": {"type": "STRING", "description": "מזהה ה-UUID של הקריאה הממתינה מהמוקד"},
                "elevator_id": {"type": "STRING", "description": "UUID של המעלית אליה רוצים לשייך את הקריאה"},
            }, "required": ["incoming_call_id", "elevator_id"]},
        },
        {
            "name": "plan_weekly_route",
            "description": "בונה תוכנית עבודה לימים הקרובים — מחלק את כל הקריאות הפתוחות לפי עדיפות וקרבה גיאוגרפית, X קריאות ביום. השתמש כאשר הטכנאי מבקש 'תכנן שבוע', 'כמה ימים קדימה', 'חלק לי את העבודה', 'תבנה מסלול לימים הקרובים'.",
            "parameters": {"type": "OBJECT", "properties": {
                "calls_per_day": {"type": "INTEGER", "description": "מספר קריאות ביום (ברירת מחדל: 8)"},
                "days": {"type": "INTEGER", "description": "מספר ימים לתכנון (ברירת מחדל: 5)"},
            }, "required": []},
        },
        {
            "name": "save_to_qa",
            "description": "שמור שאלה ותשובה חדשה למאגר הידע (QA) של הבוט. השתמש בזה כאשר ענית על שאלה חדשה שהתשובה עליה חשובה, או כאשר למדת מידע חדש מהמשתמש שכדאי לזכור לעתיד.",
            "parameters": {"type": "OBJECT", "properties": {
                "question": {"type": "STRING", "description": "השאלה או נושא המידע"},
                "answer": {"type": "STRING", "description": "התשובה המלאה או המידע לשמירה"},
                "tags": {"type": "STRING", "description": "מילות מפתח מופרדות בפסיקים"},
            }, "required": ["question", "answer"]},
        },
        {
            "name": "transfer_to_monitoring",
            "description": "מעביר קריאת שירות לסטטוס מעקב (MONITORING) ומוסיף הערות. השתמש כאשר הבעיה נפתרה זמנית ויש לעקוב, או כאשר המשתמש אומר 'העבר למעקב', 'מעקב', 'עקוב'. השתמש רק לאחר קבלת אישור מפורש מהמשתמש.",
            "parameters": {"type": "OBJECT", "properties": {
                "call_id": {"type": "STRING", "description": "UUID של הקריאה"},
                "notes": {"type": "STRING", "description": "הערות — מה קרה ולמה עוברים למעקב"},
            }, "required": ["call_id"]},
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
        terms = [t for t in query.split() if t not in ('רחוב', 'רח', 'בניין', 'לקוח', 'אצל')]
        if terms:
            from sqlalchemy import or_
            for term in terms:
                term_q = f"%{term}%"
                q = q.filter(
                    or_(
                        Elevator.address.ilike(term_q),
                        Elevator.city.ilike(term_q),
                        Elevator.building_name.ilike(term_q),
                        Elevator.serial_number.ilike(term_q)
                    )
                )
        else:
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
            "מספר_קריאה": f"S{c.call_number:05d}" if c.call_number else str(c.id)[:8],
            "תאריך": c.created_at.strftime("%d/%m/%Y %H:%M") if c.created_at else "",
            "כתובת": f"{elevator.address}, {elevator.city}" if elevator else "לא ידוע",
            "בניין": elevator.building_name or "" if elevator else "",
            "סוג_תקלה": c.fault_type,
            "עדיפות": c.priority,
            "סטטוס": c.status,
            "טכנאי": tech_name_found or "לא שובץ",
            "תיאור": c.description or "",
            "נסגר_על_ידי": c.resolved_by or "",
            "הערות_סגירה": c.resolution_notes or "",
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
    now = datetime.now(timezone.utc)
    stale_techs = []  # collect techs with stale location so we can request a pull

    # Send FCM silent push to relevant technicians so their app wakes up and
    # sends fresh GPS.  We fire-and-forget — the existing 15s polling loop will
    # pick up the updated location; we return whatever is currently in the DB.
    for t in techs:
        if technician_name and technician_name.lower() not in t.name.lower():
            continue
        if t.fcm_token:
            try:
                from app.services.fcm_service import send_location_request
                send_location_request(t.fcm_token)
            except Exception:
                pass

    for t in techs:
        if technician_name and technician_name.lower() not in t.name.lower():
            continue

        # A location is "live" only if last_location_at is within the last 60 minutes
        has_coords = bool(t.current_latitude and t.current_longitude)
        if has_coords and t.last_location_at:
            loc_age = now - t.last_location_at.replace(tzinfo=timezone.utc) if t.last_location_at.tzinfo is None else now - t.last_location_at
            age_minutes = int(loc_age.total_seconds() / 60)
            is_live = age_minutes <= 60
        else:
            is_live = False
            age_minutes = None

        # Flag location request on the DB record so the app picks it up within 15 s
        # Always request a refresh regardless of staleness so the next query gets fresh data
        try:
            t.location_requested_at = now
        except Exception:
            pass

        if has_coords and is_live:
            lat, lng = t.current_latitude, t.current_longitude
            location_type = f"חי (לפני {age_minutes} דק')" if age_minutes is not None else "חי"
        elif has_coords:
            lat, lng = t.current_latitude, t.current_longitude
            if age_minutes is not None and age_minutes < 1440:
                hours = age_minutes // 60
                location_type = f"ישן — לפני {hours} שעות" if hours > 0 else f"ישן — לפני {age_minutes} דק'"
            else:
                location_type = "ישן (יותר מיום)"
            # Mark as stale so we can append the pull-request notice
            if age_minutes is not None and age_minutes > 3:
                stale_techs.append(t.name)
        elif t.base_latitude and t.base_longitude:
            lat, lng = t.base_latitude, t.base_longitude
            location_type = "מיקום_בסיס (לא חי)"
            stale_techs.append(t.name)
        else:
            if technician_name:
                results.append({"שם": t.name, "מיקום": "לא הוגדר מיקום ולא שודר מיקום חי"})
            stale_techs.append(t.name)
            continue

        try:
            from app.services.maps_service import reverse_geocode
            place_name = reverse_geocode(lat, lng)
        except Exception:
            place_name = "לא ידוע"

        results.append({
            "שם": t.name,
            "מיקום": place_name,
            "קואורדינטות": f"{lat:.6f}, {lng:.6f}",
            "קישור_מפה": f"https://maps.google.com/?q={lat},{lng}",
            "סוג_מיקום": location_type,
            "זמין": t.is_available,
            "_הנחיה": "השתמש בשדה 'מיקום' כשם המקום — אל תנחש ואל תמציא שמות ערים אחרים.",
        })

    # Persist location_requested_at for all matched technicians
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    if not results:
        return {"תוצאה": "לא נמצא מיקום זמין — ודא שהטכנאי שידר מיקום מהאפליקציה"}

    response: dict = {"טכנאים": results}
    if stale_techs:
        response["הודעה"] = "🔄 שלחתי בקשה לעדכון מיקום בזמן אמת. ניתן לשאול שוב בעוד 30 שניות."
    return response


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


def _transfer_to_monitoring(db: Session, call_id: str, notes: str = "") -> dict:
    """Set service call status to MONITORING."""
    import uuid as _uuid
    try:
        cid = _uuid.UUID(call_id)
    except ValueError:
        return {"error": "מזהה קריאה לא תקין"}
    call = db.query(ServiceCall).filter(ServiceCall.id == cid).first()
    if not call:
        return {"error": "הקריאה לא נמצאה"}
    call.status = "MONITORING"
    if notes:
        existing = call.resolution_notes or ""
        call.resolution_notes = f"{existing}\n[מעקב]: {notes}".strip()
    db.commit()
    return {"success": True, "call_number": call.call_number, "status": "MONITORING"}


def _get_technician_route(db: Session, tech_id: str = None, technician_name: str = None) -> dict:
    """Return open assigned calls for a technician — mirrors what the technician app UI shows."""
    from app.models.assignment import Assignment
    if tech_id:
        tech = db.query(Technician).filter(Technician.id == tech_id).first()
    else:
        tech = db.query(Technician).filter(Technician.name.ilike(f"%{technician_name}%")).first()
    if not tech:
        return {"error": f"הטכנאי לא נמצא"}

    assignments = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id,
                Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION", "AUTO_ASSIGNED"]))
        .all()
    )

    active = []       # CONFIRMED/AUTO_ASSIGNED, non-maintenance — what UI shows as "active"
    maintenance = []  # all maintenance calls
    pending = []      # PENDING_CONFIRMATION awaiting technician reply

    for a in assignments:
        call = db.query(ServiceCall).filter(
            ServiceCall.id == a.service_call_id,
            ServiceCall.status.notin_(["CLOSED", "RESOLVED", "CANCELLED"])
        ).first()
        if not call:
            continue
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        entry = {
            "מספר_קריאה": f"S{call.call_number:05d}" if call.call_number else str(call.id)[:8],
            "כתובת": f"{elev.address}, {elev.city}" if elev else "לא ידוע",
            "עדיפות": call.priority,
            "סטטוס_קריאה": call.status,
            "תיאור": (call.description or "")[:80],
            "תאריך_פתיחה": call.created_at.strftime("%d/%m %H:%M") if call.created_at else "",
        }
        if call.fault_type == "MAINTENANCE":
            maintenance.append(entry)
        elif a.status == "PENDING_CONFIRMATION":
            pending.append(entry)
        else:
            active.append(entry)

    active.sort(key=lambda x: ("CRITICAL" not in x["עדיפות"], "HIGH" not in x["עדיפות"]))

    from app.config import get_settings
    base_url = getattr(get_settings(), "app_base_url", "").rstrip("/")
    portal_url = f"{base_url}/tech" if base_url else ""
    return {
        "טכנאי": tech.name,
        "קריאות_פעילות": active,
        "סה_כ_פעילות": len(active),
        "ממתינות_לאישור_שלך": len(pending),
        "תחזוקה_פתוחה": len(maintenance),
        "לינק_לניהול": portal_url,
        "_הנחיה": "הצג רק את 'קריאות_פעילות'. ציין בנפרד את מספר הממתינות לאישור ותחזוקה אם יש.",
    }


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
    return _get_technician_route(db, tech_id=tech.id)


def _get_my_confirmed_calls(db: Session, phone: str) -> dict:
    """Return calls the technician explicitly confirmed (CONFIRMED or AUTO_ASSIGNED assignments)."""
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

    confirmed_assignments = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status.in_(["CONFIRMED", "AUTO_ASSIGNED"]),
        )
        .order_by(Assignment.assigned_at.desc())
        .limit(20)
        .all()
    )
    if not confirmed_assignments:
        return {"תוצאה": f"לא נמצאו קריאות מאושרות עבור {tech.name}"}

    results = []
    for a in confirmed_assignments:
        call = db.query(ServiceCall).filter(ServiceCall.id == a.service_call_id).first()
        if not call:
            continue
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first() if call.elevator_id else None
        results.append({
            "מספר_קריאה": f"S{call.call_number:05d}" if call.call_number else str(call.id)[:8],
            "כתובת": f"{elev.address}, {elev.city}" if elev else "לא ידוע",
            "סטטוס_קריאה": call.status,
            "סוג_תקלה": call.fault_type,
            "תיאור": (call.description or "")[:80],
            "נפתחה": call.created_at.strftime("%d/%m/%Y %H:%M") if call.created_at else None,
            "אושר_ב": a.assigned_at.strftime("%d/%m/%Y %H:%M") if a.assigned_at else None,
        })
    return {"קריאות_מאושרות": results, "סה_כ": len(results)}


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
        .order_by(Assignment.assigned_at.desc())
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
    from sqlalchemy import or_
    terms = [t for t in query.split() if len(t) > 1]
    if not terms:
        terms = [query]
    
    q_filter = db.query(Customer).filter(Customer.is_active == True)  # noqa
    for term in terms:
        t = f"%{term}%"
        q_filter = q_filter.filter(
            or_(
                Customer.name.ilike(t),
                Customer.phone.ilike(t),
                Customer.city.ilike(t),
                Customer.contact_person.ilike(t),
            )
        )
        
    customers = q_filter.limit(8).all()
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


def _search_inspection_reports(db: Session, city: str = "", has_open_deficiencies: bool = False, limit: int = 10) -> list:
    """Search inspection reports across elevators, optionally filtered by city and open deficiencies."""
    q = db.query(InspectionReport)
    if city:
        q = q.join(Elevator, InspectionReport.elevator_id == Elevator.id).filter(Elevator.city.ilike(f"%{city}%"))
    if has_open_deficiencies:
        q = q.filter(InspectionReport.report_status.in_(["OPEN", "PARTIAL"]))
    reports = q.order_by(InspectionReport.inspection_date.desc()).limit(limit).all()
    if not reports:
        return [{"תוצאה": "לא נמצאו דוחות בודק התואמים לחיפוש"}]
    result = []
    for r in reports:
        elev = db.query(Elevator).filter(Elevator.id == r.elevator_id).first()
        open_defs = [d for d in (r.deficiencies or []) if not d.get("done")]
        result.append({
            "id": str(r.id),
            "כתובת": f"{elev.address}, {elev.city}" if elev else "לא ידוע",
            "תאריך_בדיקה": r.inspection_date.strftime("%d/%m/%Y") if r.inspection_date else None,
            "בודק": r.inspector_name,
            "ליקויים_פתוחים": len(open_defs),
            "ליקויים_סה_כ": r.deficiency_count,
            "סטטוס_דוח": r.report_status,
            "ליקויים": [{"תיאור": d.get("description", ""), "חומרה": d.get("severity", "")} for d in open_defs[:5]],
        })
    return result


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


def _get_upcoming_maintenance(db: Session, days_ahead: int = 14, overdue_only: bool = False, city: str = None) -> list:
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
    
    if city:
        q = q.join(Elevator, MaintenanceRecord.elevator_id == Elevator.id).filter(Elevator.city.ilike(f"%{city}%"))
        
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


def _find_tech_by_phone(db: Session, phone: str):
    """Find a technician by any phone format."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    last9 = digits[-9:] if len(digits) >= 9 else digits
    if not last9:
        return None
    return db.query(Technician).filter(
        (Technician.phone.contains(last9)) | (Technician.whatsapp_number.contains(last9))
    ).first()


def _take_service_call(db: Session, phone: str, address_hint: str = "", call_id: str = "") -> dict:
    """Self-assign an open service call to the technician identified by phone."""
    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return {"error": "הטכנאי לא זוהה במערכת — פנה למוקד"}

    from app.models.assignment import Assignment
    import uuid as _uuid
    from sqlalchemy import or_

    call = None
    if call_id:
        try:
            call = db.query(ServiceCall).filter(ServiceCall.id == _uuid.UUID(call_id)).first()
        except Exception:
            pass

    if not call:
        q = (db.query(ServiceCall)
             .join(Elevator, ServiceCall.elevator_id == Elevator.id)
             .filter(ServiceCall.status.in_(["OPEN", "ASSIGNED"]))
             .order_by(ServiceCall.created_at.desc()))
        if address_hint:
            for term in [t for t in address_hint.split() if len(t) > 1]:
                q = q.filter(or_(
                    Elevator.address.ilike(f"%{term}%"),
                    Elevator.city.ilike(f"%{term}%"),
                    Elevator.building_name.ilike(f"%{term}%"),
                ))
        call = q.first()

    if not call:
        return {"error": "לא נמצאה קריאה פתוחה מתאימה לכתובת שצוינה"}

    elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    addr = f"{elev.address}, {elev.city}" if elev else "לא ידוע"

    for existing in db.query(Assignment).filter(
        Assignment.service_call_id == call.id,
        Assignment.status == "PENDING_CONFIRMATION"
    ).all():
        existing.status = "REJECTED"

    new_assign = Assignment(
        service_call_id=call.id,
        technician_id=tech.id,
        assignment_type="MANUAL",
        status="CONFIRMED",
    )
    db.add(new_assign)
    call.status = "ASSIGNED"
    db.commit()

    try:
        from app.services.route_service import send_route_to_technician
        send_route_to_technician(db, tech)
    except Exception:
        pass

    return {
        "success": True,
        "מספר_קריאה": f"S{call.call_number:05d}" if call.call_number else None,
        "כתובת": addr,
        "הודעה": f"✅ שויכת לקריאה ב-{addr}",
    }


def _close_my_active_call(db: Session, phone: str, resolution_notes: str = "", quote_needed: bool = False) -> dict:
    """Close the active call for the technician identified by phone."""
    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return {"error": "הטכנאי לא זוהה במערכת"}

    from app.models.assignment import Assignment

    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"]),
        )
        .order_by(Assignment.assigned_at.desc())
        .first()
    )
    if not assignment:
        return {"error": "לא נמצאה קריאה פעילה לסגירה — אולי כבר נסגרה?"}

    call = db.query(ServiceCall).filter(
        ServiceCall.id == assignment.service_call_id,
        ServiceCall.status.notin_(["CLOSED", "RESOLVED"]),
    ).first()
    if not call:
        return {"error": "הקריאה לא נמצאה או שכבר סגורה"}

    call.status = "CLOSED"
    if resolution_notes:
        call.resolution_notes = resolution_notes
    call.resolved_at = datetime.now(timezone.utc)
    call.resolved_by = tech.name
    if quote_needed:
        call.quote_needed = True
    assignment.status = "COMPLETED"
    db.commit()

    try:
        from app.services.service_call_service import _advance_next_service_date
        _advance_next_service_date(db, call)
    except Exception:
        pass

    elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    addr = f"{elev.address}, {elev.city}" if elev else "לא ידוע"

    return {
        "success": True,
        "מספר_קריאה": f"S{call.call_number:05d}" if call.call_number else None,
        "כתובת": addr,
        "הצעת_מחיר": quote_needed,
        "הודעה": "✅ הקריאה נסגרה בהצלחה",
    }


def _get_my_route_by_phone(db: Session, phone: str) -> dict:
    """Return the optimized current route for the technician identified by phone, with a Google Maps link."""
    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return {"error": "לא נמצא טכנאי מקושר למספר הטלפון הזה"}

    from app.services.route_service import build_route, format_route_message, RouteStop
    from app.services.maps_service import ensure_elevator_coords
    from app.models.assignment import Assignment

    stops, suggestions = build_route(db, tech)

    # Fallback: if no GPS — build priority-ordered route without nearest-neighbor
    if not stops:
        assigned_ids = {
            a.service_call_id
            for a in db.query(Assignment)
            .filter(Assignment.technician_id == tech.id,
                    Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION", "AUTO_ASSIGNED"]))
            .all()
        }
        _PRI_W = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        pool = []
        for cid in assigned_ids:
            call = db.query(ServiceCall).filter(
                ServiceCall.id == cid, ServiceCall.status.notin_(["CLOSED", "RESOLVED"])
            ).first()
            if not call:
                continue
            elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
            if not elev:
                continue
            lat, lng = ensure_elevator_coords(db, elev)
            _FAULT_HE = {"STUCK": "מעלית תקועה 🚨", "DOOR": "תקלת דלת", "ELECTRICAL": "חשמלית",
                         "MECHANICAL": "מכנית", "SOFTWARE": "תוכנה", "OTHER": "כללית"}
            pool.append(RouteStop(
                call_id=str(call.id), elevator_id=str(elev.id),
                address=elev.address, city=elev.city, building=elev.building_name or "",
                fault_type=_FAULT_HE.get(call.fault_type, call.fault_type),
                priority=call.priority, lat=lat, lng=lng, travel_minutes=0,
            ))
        stops = sorted(pool, key=lambda s: _PRI_W.get(s.priority, 2))

    msg = format_route_message(tech.name, stops, suggestions)
    return {
        "תוצאה": "המסלול חושב בהצלחה",
        "טקסט_מסלול_מלא": msg,
        "_הנחיה": "עליך להציג את 'טקסט_מסלול_מלא' במלואו בדיוק כפי שהוא (כולל אימוג'ים, קישורים למפה, והמלצות), מבלי לשנות או לתמצת כלום."
    }


def _request_call_from_dispatcher(db: Session, phone: str, address_hint: str = "") -> dict:
    """Create a REQUEST-type assignment pending dispatcher approval."""
    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return {"error": "הטכנאי לא זוהה במערכת"}

    from app.models.assignment import Assignment
    from sqlalchemy import or_

    q = (db.query(ServiceCall)
         .join(Elevator, ServiceCall.elevator_id == Elevator.id)
         .filter(ServiceCall.status.in_(["OPEN", "ASSIGNED"]))
         .order_by(ServiceCall.created_at.desc()))
    if address_hint:
        for term in [t for t in address_hint.split() if len(t) > 1]:
            q = q.filter(or_(
                Elevator.address.ilike(f"%{term}%"),
                Elevator.city.ilike(f"%{term}%"),
            ))
    call = q.first()
    if not call:
        return {"error": "לא נמצאה קריאה פתוחה מתאימה"}

    elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    addr = f"{elev.address}, {elev.city}" if elev else "לא ידוע"

    existing = db.query(Assignment).filter(
        Assignment.service_call_id == call.id,
        Assignment.technician_id == tech.id,
        Assignment.assignment_type == "REQUEST",
        Assignment.status == "PENDING_CONFIRMATION",
    ).first()
    if existing:
        return {"error": f"כבר שלחת בקשה לקריאה ב-{addr} — ממתין לאישור מוקד"}

    db.add(Assignment(
        service_call_id=call.id,
        technician_id=tech.id,
        assignment_type="REQUEST",
        status="PENDING_CONFIRMATION",
        notes=f"{tech.name} ביקש לטפל דרך הסוכן",
    ))
    db.commit()

    try:
        from app.services.whatsapp_service import notify_dispatcher
        notify_dispatcher(
            f"🙋 *{tech.name} מבקש לטפל בקריאה*\n"
            f"📍 {addr}\n⚡ {call.fault_type} | {call.priority}"
        )
    except Exception:
        pass

    return {
        "success": True,
        "כתובת": addr,
        "הודעה": f"✅ בקשתך לטפל בקריאה ב-{addr} נשלחה למוקד — תקבל עדכון לאחר אישור",
    }


def _mark_call_in_progress(db: Session, phone: str) -> dict:
    """Mark the technician's active call as IN_PROGRESS."""
    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return {"error": "הטכנאי לא זוהה"}

    from app.models.assignment import Assignment

    assignment = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id, Assignment.status == "CONFIRMED")
        .order_by(Assignment.assigned_at.desc())
        .first()
    )
    if not assignment:
        return {"error": "אין קריאה פעילה לסימון"}

    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    if not call:
        return {"error": "הקריאה לא נמצאה"}

    call.status = "IN_PROGRESS"
    db.commit()
    elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    addr = f"{elev.address}, {elev.city}" if elev else "לא ידוע"

    return {
        "success": True,
        "כתובת": addr,
        "הודעה": f"✅ הקריאה ב-{addr} סומנה כבטיפול",
    }


def _plan_weekly_route(db: Session, phone: str, calls_per_day: int = 8, days: int = 5) -> dict:
    """Split all open calls for the technician across upcoming days by priority + geography."""
    from app.models.assignment import Assignment
    from datetime import date, timedelta

    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return {"error": "הטכנאי לא זוהה במערכת"}

    # Collect all open/assigned calls
    assigned_call_ids = {
        a.service_call_id
        for a in db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION", "AUTO_ASSIGNED"]),
        )
        .all()
    }
    calls_raw = []
    for call_id in assigned_call_ids:
        call = db.query(ServiceCall).filter(
            ServiceCall.id == call_id,
            ServiceCall.status.notin_(["CLOSED", "RESOLVED", "CANCELLED"]),
        ).first()
        if not call:
            continue
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if not elev:
            continue
        from app.services.maps_service import ensure_elevator_coords
        lat, lng = ensure_elevator_coords(db, elev)
        calls_raw.append({
            "call": call,
            "elev": elev,
            "lat": lat,
            "lng": lng,
            "priority_w": {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(call.priority, 2),
        })

    if not calls_raw:
        return {"תוצאה": "אין קריאות פתוחות ממתינות לתכנון"}

    # Sort: CRITICAL first, then greedy nearest-neighbor within each priority tier
    calls_raw.sort(key=lambda x: x["priority_w"])

    # Greedy nearest-neighbor pass across ALL calls
    from app.services.route_service import _haversine_km
    start_lat = tech.current_latitude or 32.08
    start_lng = tech.current_longitude or 34.78
    ordered = []
    pool = list(calls_raw)
    cur_lat, cur_lng = start_lat, start_lng

    while pool:
        best_idx = 0
        best_score = float("inf")
        for i, item in enumerate(pool):
            dist = _haversine_km(cur_lat, cur_lng, item["lat"], item["lng"])
            score = dist + item["priority_w"] * 5  # weight priority
            if score < best_score:
                best_score = score
                best_idx = i
        chosen = pool.pop(best_idx)
        ordered.append(chosen)
        cur_lat, cur_lng = chosen["lat"], chosen["lng"]

    # Split into daily chunks; skip Saturdays
    _PRIORITY_HE = {"CRITICAL": "קריטי 🔴", "HIGH": "גבוה 🟠", "MEDIUM": "בינוני 🟡", "LOW": "נמוך 🟢"}
    plan = []
    today = date.today()
    chunk_start = 0
    for day_offset in range(days * 2):  # extra range to skip Saturdays
        if chunk_start >= len(ordered):
            break
        day = today + timedelta(days=day_offset + 1)
        if day.weekday() == 5:  # Saturday
            continue
        chunk = ordered[chunk_start: chunk_start + calls_per_day]
        chunk_start += calls_per_day
        day_calls = []
        for item in chunk:
            call = item["call"]
            elev = item["elev"]
            day_calls.append({
                "קריאה": f"S{call.call_number:05d}" if call.call_number else str(call.id)[:8],
                "כתובת": f"{elev.address}, {elev.city}",
                "עדיפות": _PRIORITY_HE.get(call.priority, call.priority),
                "תיאור": (call.description or "")[:60],
            })
        plan.append({
            "יום": day.strftime("%A %d/%m").replace("Monday", "שני").replace("Tuesday", "שלישי")
                       .replace("Wednesday", "רביעי").replace("Thursday", "חמישי")
                       .replace("Friday", "שישי").replace("Sunday", "ראשון"),
            "תאריך": day.strftime("%d/%m/%Y"),
            "מספר_קריאות": len(day_calls),
            "קריאות": day_calls,
        })
        if len(plan) >= days:
            break

    return {
        "טכנאי": tech.name,
        "סה_כ_קריאות": len(ordered),
        "ימים_בתוכנית": len(plan),
        "תוכנית": plan,
        "_הנחיה": "הצג את התוכנית יום אחד אחרי השני עם כל הקריאות. ציין בכל יום את מספר הקריאות ואת הכתובות לפי סדר.",
    }


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _run_tool(db: Session, tool_name: str, tool_input: dict, phone: str = "") -> Any:
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
    elif tool_name == "transfer_to_monitoring":
        return _transfer_to_monitoring(db, tool_input["call_id"], tool_input.get("notes", ""))
    elif tool_name == "get_technician_route":
        return _get_technician_route(db, technician_name=tool_input["technician_name"])
    elif tool_name == "get_my_calls":
        return _get_my_calls(db, tool_input.get("phone", ""))
    elif tool_name == "get_my_confirmed_calls":
        return _get_my_confirmed_calls(db, tool_input.get("phone", ""))
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
    elif tool_name == "search_inspection_reports":
        return _search_inspection_reports(db, tool_input.get("city", ""), tool_input.get("has_open_deficiencies", False), tool_input.get("limit", 10))
    elif tool_name == "get_upcoming_maintenance":
        return _get_upcoming_maintenance(db, tool_input.get("days_ahead", 14), tool_input.get("overdue_only", False), tool_input.get("city"))
    elif tool_name == "get_pending_unmatched_calls":
        return _get_pending_unmatched_calls(db, tool_input.get("limit", 10))
    elif tool_name == "get_document_analysis":
        return _get_document_analysis(db, tool_input["entity_type"], tool_input["entity_id"])
    elif tool_name == "take_service_call":
        return _take_service_call(db, phone, tool_input.get("address_hint", ""), tool_input.get("call_id", ""))
    elif tool_name == "close_my_active_call":
        return _close_my_active_call(db, phone, tool_input.get("resolution_notes", ""), tool_input.get("quote_needed", False))
    elif tool_name == "get_my_route":
        return _get_my_route_by_phone(db, phone)
    elif tool_name == "plan_weekly_route":
        return _plan_weekly_route(
            db, phone,
            calls_per_day=int(tool_input.get("calls_per_day", 8)),
            days=int(tool_input.get("days", 5)),
        )
    elif tool_name == "request_call_from_dispatcher":
        return _request_call_from_dispatcher(db, phone, tool_input.get("address_hint", ""))
    elif tool_name == "mark_call_in_progress":
        return _mark_call_in_progress(db, phone)
    elif tool_name == "create_service_call":
        from app.services.service_call_service import create_service_call
        from app.schemas.service_call import ServiceCallCreate
        import uuid as _uuid
        try:
            eid = _uuid.UUID(tool_input["elevator_id"])
        except ValueError:
            return {"error": "מזהה מעלית לא תקין"}
        data = ServiceCallCreate(
            elevator_id=eid,
            reported_by=tool_input.get("reported_by") or "סוכן AI",
            description=tool_input["description"],
            priority=tool_input.get("priority", "MEDIUM"),
            fault_type=tool_input.get("fault_type", "OTHER"),
        )
        try:
            call = create_service_call(db, data, current_user_email=f"ai_agent_{phone}")
            
            try:
                from app.services.whatsapp_service import notify_dispatcher
                from app.models.elevator import Elevator
                elev = db.query(Elevator).filter(Elevator.id == eid).first()
                addr = f"{elev.address}, {elev.city}" if elev else "לא ידוע"
                notify_dispatcher(f"🤖 *קריאה חדשה נפתחה ע\"י סוכן AI*\n📍 {addr}\n⚡ {data.fault_type}\n📝 {data.description}")
            except Exception:
                pass
                
            return {
                "success": True,
                "מספר_קריאה": f"S{call.call_number:05d}" if call.call_number else str(call.id)[:8],
                "הודעה": "הקריאה נפתחה בהצלחה"
            }
        except Exception as exc:
            return {"error": f"שגיאה בפתיחת קריאה: {str(exc)}"}
    elif tool_name == "match_unmatched_call_to_elevator":
        from app.services.service_call_service import create_service_call
        from app.schemas.service_call import ServiceCallCreate
        import uuid as _uuid
        try:
            iid = _uuid.UUID(tool_input["incoming_call_id"])
            eid = _uuid.UUID(tool_input["elevator_id"])
        except ValueError:
            return {"error": "מזהה לא תקין"}
        log = db.query(IncomingCallLog).filter(IncomingCallLog.id == iid).first()
        if not log:
            return {"error": "הקריאה הממתינה לא נמצאה"}
        data = ServiceCallCreate(
            elevator_id=eid,
            reported_by=log.caller_name or log.caller_phone or "מוקד",
            description=f"שויך ידנית ע\"י סוכן AI. \n{log.extracted_description or ''}",
            priority=log.priority or "MEDIUM",
            fault_type=log.fault_type or "OTHER",
        )
        try:
            call = create_service_call(db, data, current_user_email=f"ai_agent_{phone}")
            log.match_status = "MATCHED"
            log.elevator_id = eid
            log.service_call_id = call.id
            db.commit()
            
            try:
                from app.services.whatsapp_service import notify_dispatcher
                from app.models.elevator import Elevator
                elev = db.query(Elevator).filter(Elevator.id == eid).first()
                addr = f"{elev.address}, {elev.city}" if elev else "לא ידוע"
                notify_dispatcher(f"🤖 *קריאה ממתינה שויכה ונפתחה ע\"י AI*\n📍 {addr}\n⚡ {data.fault_type}\n📝 {data.description}")
            except Exception:
                pass
                
            return {
                "success": True,
                "מספר_קריאה": f"S{call.call_number:05d}" if call.call_number else str(call.id)[:8],
                "הודעה": "הקריאה שויכה ונפתחה בהצלחה"
            }
        except Exception as exc:
            return {"error": f"שגיאה בשיוך הקריאה: {str(exc)}"}
    elif tool_name == "save_to_qa":
        from app.models.bot_qa import BotQA
        try:
            entry = BotQA(
                question=tool_input["question"],
                answer=tool_input["answer"],
                tags=tool_input.get("tags", ""),
                created_by=f"ai_agent_{phone}"
            )
            db.add(qa)
            db.commit()
            return {"success": True, "message": "המידע נשמר בהצלחה למאגר הידע של הבוט"}
        except Exception as exc:
            db.rollback()
            return {"error": f"שגיאה בשמירת QA: {str(exc)}"}
    else:
        return {"error": f"כלי לא מוכר: {tool_name}"}


# ── Main chat function ────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """אתה עוזר דיגיטלי זמין לצוות דרך ווצאפ.
יש לך גישה למערכת דרך כלים — מעליות, קריאות שירות, טכנאים, לקוחות, חברות ניהול, בדיקות, תחזוקה וקריאות ממתינות.

השתמש בכלים לשליפת מידע חי. אל תמציא תשובות.
ענה בעברית קצרה וישירה. תאריכים בפורמט DD/MM/YYYY.

══ כלל ריצה מיידית ויוזמה ══
שאלות מידע או בקשות עזרה כלליות ("מה יש לי לעשות בעפולה?"): אל תשאל "האם תרצה שאבדוק X או Y?". קח יוזמה! קרא לכל הכלים הרלוונטיים (למשל גם קריאות וגם תחזוקה), ואז תן תשובה מסכמת של מה שמצאת.
שלוף מידע מיד, לעולם אל תשאל אישור לשלוף נתונים.
• "רשימת מעליות בעיר X" → search_elevators(city=X, limit=100)
• "הקפץ לי קריאה 42" → get_call_by_number → הצג פרטים
• "מה יש לי היום?" → get_my_calls → הצג רשימה

══ כלל מיקוד בהודעה האחרונה ══
חובה! ענה אך ורק על הבקשה האחרונה של המשתמש. אל תחזור על שאלות או בקשות ישנות מהיסטוריית השיחה ואל תציף במידע שלא נתבקשת (כמו מיקומי טכנאים או תוצאות חיפוש ישנות). היסטוריית השיחה נועדה אך ורק להקשר רציף.

══ מענה על שיבוצים ומיקום ══
• אם שואלים איפה טכנאי נמצא (למשל: "באיזה אזור X נמצא?") — חובה להשתמש בכלי get_technician_location. 
• כאשר אתה מציג מיקום של טכנאי, לעולם אל תרשום קואורדינטות מספריות (קו רוחב/אורך). הצג תמיד אך ורק את קישור המפה (Google Maps) שהתקבל מהכלי, או ציין עיר/רחוב אם ידוע.
• שדה "סוג_מיקום" בתוצאת הכלי מציין אם המיקום עדכני — הצג אותו למשתמש! "חי (לפני X דק')" = מיקום GPS אמיתי, "ישן — לפני X שעות" = מיקום ישן, "מיקום_בסיס" = כתובת ביתית בלבד. אל תאמר "נמצא כרגע" כאשר המיקום ישן.
• אם שואלים למה טכנאי הומלץ או שובץ לקריאה — הסבר במדויק שמערכת השיבוץ האוטומטית (AI) מחשבת זמן הגעה חי (פקקים, מרחק), עומס קריאות פתוחות לטכנאי, ורמות מיומנות ספציפיות הנדרשות לאותה מעלית/תקלה.

══ הפרדה בין תקלות לתחזוקה ══
שים לב היטב לבקשות של "קריאות שירות" (תקלות - השתמש ב-get_recent_calls או get_elevator_calls) לעומת "קריאות תחזוקה/טיפול מונע" (השתמש ב-get_upcoming_maintenance או get_elevator_maintenance).

══ כלל תוצאות חלקיות ══
אם חיפוש מחזיר "מוצגות X מתוך Y" — הרץ שוב עם limit גדול יותר.
אל תאמר "הנה הרשימה" לפני שמשכת את הכל.
כאשר מבקשים רשימה מפורטת (למשל רשימת מעליות בעיר מסוימת), עליך להציג את התוצאות שהתקבלו מהכלי בתשובה שלך (רשימה עם פרטים), ולא רק לומר "יש X תוצאות".

══ הצגת פרטי קריאות ══
חובה! כאשר אתה מציג קריאה או רשימת קריאות למשתמש, תמיד כלול את מספר הקריאה (למשל S00123) בתשובתך. זה קריטי כדי שבשאלות המשך המשתמש ואתה תוכלו להתייחס לקריאה ספציפית דרך get_call_by_number.

══ כלל אישור — לכל פעולה שמשנה נתונים ══
כל פעולה שמשנה, יוצרת או מוחקת נתונים חייבת אישור מפורש לפני הביצוע.
כולל: סגירת קריאה, שיבוץ טכנאי, העברה להצעת מחיר, העברה למעקב, ועוד.
אזהרה חמורה לגבי סגירת קריאות: לעולם אל תסגור מספר קריאות במקביל, גם אם נראה לך שהתבקשת. סגור אך ורק קריאה בודדת אחת, לאחר וידוא זהותה (מס' קריאה), ולעולם אל תשתמש בהודעה הקולית כ"הערות סגירה" אלא אם התבקשת מפורשות!
אישור תקף: כן / לא / 1 / 2 / אישור / ביטול / בסדר / אוקיי / ok / yep.
כלל ברזל: אם שאלת "האם לבצע X?" ובתגובה הבאה המשתמש כתב רק "כן" או "אישור" או "בסדר" — בצע מיד. אסור לשאול שוב "האם...?". שאלת אישור אחת בלבד לכל פעולה.

══ כלל הרשאות ══
פרטי ההרשאות של המשתמש יסופקו בהקשר. הצג רק מידע שהתפקיד שלו מורשה לראות.
אם אין לו הרשאה למידע מבוקש — השב: "אין לך הרשאה לצפות במידע זה (תפקידך: [תפקיד])".
אם המשתמש לא זוהה במערכת — התייחס כטכנאי (הרשאות מוגבלות לקריאות שירות בלבד).

אם המשתמש מבקש משהו שאין לך כלי עבורו — ציין: "פעולה זו אינה זמינה כרגע (חסר: [תיאור])".

══ כלי פעולות לטכנאים ══
כלים אלה מזהים את הטכנאי אוטומטית לפי מספר הטלפון — אין צורך לבקש פרטים נוספים.

• "לקחתי / הולך / אני על זה / אני מגיע" + כתובת → take_service_call(address_hint=...)  [בצע מיד]
• "סיימתי / בוצע / טיפלתי / גמרתי" + הערות → close_my_active_call(resolution_notes=..., quote_needed=...)  [בצע מיד]
• "מה יש לי / שלח מסלול / הקריאות שלי / סדר יום" → get_my_route()
• "מבקש לטפל / אשמח לטפל / רוצה לטפל" → request_call_from_dispatcher(address_hint=...)
• "התחלתי / אני שם / מתחיל לטפל" → mark_call_in_progress()

כלל ברזל: close_my_active_call ו-take_service_call — בצע מיד כשהכוונה ברורה. אל תבקש אישור חוזר.
כלל ברזל: close_service_call (הכלי הישן לסגירה לפי call_id) — דורש אישור מפורש לפני ביצוע.
• "העבר למעקב / מעקב" + מספר קריאה → get_call_by_number → transfer_to_monitoring(call_id=..., notes=...)  [דורש אישור]"""


def _load_conversation_history(db: Session, phone: str, limit: int = 20) -> list:
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
        # Strip model responses that contain location data — they go stale instantly
        # and cause Gemini to reuse cached coordinates instead of calling the tool
        def _is_location_response(text: str) -> bool:
            return "maps.google.com" in text or "קואורדינטות" in text or "סוג מיקום" in text

        turns = [t for t in turns if not (t["role"] == "model" and _is_location_response(t["parts"][0]["text"]))]

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
            return _answer_gemini(db, s, contents, extra_system=extra, phone=phone)
        except Exception as exc:
            logger.warning("Gemini unavailable (%s) — trying Anthropic fallback", exc)

    if s.anthropic_api_key:
        try:
            return _answer_anthropic(s, question, asker_name, db=db, extra_system=extra)
        except Exception as exc:
            logger.warning("Anthropic fallback also failed: %s", exc)

    return "השירות אינו זמין כרגע — נסה שוב בעוד מספר דקות."


def _answer_gemini(db, s, contents: list, extra_system: str = "", phone: str = "") -> str:
    """Run the Gemini tool-use loop and return Hebrew answer."""
    from sqlalchemy import text
    import json
    
    # Try to load prompt from DB
    system_text = _SYSTEM_PROMPT
    try:
        row = db.execute(text("SELECT value FROM system_settings WHERE key = 'wa_agent_config'")).fetchone()
        if row and row[0]:
            config = json.loads(row[0])
            if config.get("system_prompt"):
                system_text = config["system_prompt"]
    except Exception as exc:
        logger.warning("Could not load system prompt from DB: %s", exc)

    if extra_system:
        system_text += f"\n\n{extra_system}"

    # Inject current timestamp so Gemini knows history is stale
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
    system_text += (
        f"\n\nהשעה הנוכחית היא {now_str}. "
        "חשוב מאוד: מיקום טכנאים מתעדכן בזמן אמת ומידע על מיקום בהיסטוריית השיחה מיושן ואינו מהימן. "
        "בכל שאלה על מיקום טכנאי — חובה לקרוא לכלי get_technician_location מחדש, ללא יוצא מן הכלל."
    )

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
                result = _run_tool(db, name, args, phone=phone)
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
        "name": "transfer_to_monitoring",
        "description": "מעביר קריאה לסטטוס מעקב (MONITORING). השתמש רק לאחר קבלת אישור מפורש.",
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
