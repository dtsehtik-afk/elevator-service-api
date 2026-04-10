"""
Manager/dispatcher WhatsApp command handler.
Supports: CLOSE_CALL, ASSIGN_TECH, STATUS_QUERY, UNKNOWN
"""
import logging
import re
import json as _json
import httpx
from app.services.whatsapp_service import _send_message, notify_dispatcher

logger = logging.getLogger(__name__)

_COMMAND_PROMPT = """אתה מנתח פקודות מנהל של חברת מעליות. החזר JSON בלבד:
{{"command": "CLOSE_CALL|ASSIGN_TECH|STATUS_QUERY|UNKNOWN", "address": "כתובת אם קיימת", "tech_name": "שם טכנאי אם קיים"}}

דוגמאות:
"סגור קריאה ברחוב הרצל 5" → CLOSE_CALL
"שבץ תומר לקריאה ברחוב ביאליק" → ASSIGN_TECH
"מה הסטטוס" → STATUS_QUERY
"בוקר טוב" → UNKNOWN

הודעה: {text}"""


def handle_dispatcher_command(db, phone: str, text: str, settings) -> None:
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from datetime import datetime, timezone

    api_key = getattr(settings, "gemini_api_key", "")

    # Parse command with Gemini
    command, address, tech_name = "UNKNOWN", "", ""
    if api_key:
        try:
            prompt = _COMMAND_PROMPT.format(text=text)
            payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 150}}
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            resp = httpx.post(url, json=payload, timeout=10)
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            parsed = _json.loads(raw)
            command = parsed.get("command", "UNKNOWN")
            address = parsed.get("address", "")
            tech_name = parsed.get("tech_name", "")
        except Exception as exc:
            logger.error("Dispatcher command parse failed: %s", exc)

    logger.warning("🎯 Dispatcher command: %s | address: %s | tech: %s", command, address, tech_name)

    if command == "STATUS_QUERY":
        _cmd_status(db, phone)
    elif command == "CLOSE_CALL":
        _cmd_close_call(db, phone, address, text)
    elif command == "ASSIGN_TECH":
        _cmd_assign_tech(db, phone, address, tech_name)
    else:
        # Free question — route to chat agent
        from app.services.scheduler import _handle_chat_question
        _handle_chat_question(db, phone, text, settings)


def _cmd_status(db, phone: str) -> None:
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.services.working_hours import is_working_hours

    open_count     = db.query(ServiceCall).filter(ServiceCall.status == "OPEN").count()
    assigned_count = db.query(ServiceCall).filter(ServiceCall.status == "ASSIGNED").count()
    progress_count = db.query(ServiceCall).filter(ServiceCall.status == "IN_PROGRESS").count()

    on_call = db.query(Technician).filter(Technician.is_on_call == True).first()  # noqa: E712
    on_call_name = on_call.name if on_call else "לא הוגדר"
    hours_str = "שעות עבודה" if is_working_hours() else "מחוץ לשעות"

    _send_message(phone,
        f"📊 *סטטוס מערכת — {hours_str}*\n"
        f"🔴 פתוחות: *{open_count}*\n"
        f"🟡 ממתינות לאישור: *{assigned_count}*\n"
        f"🔵 בטיפול: *{progress_count}*\n"
        f"🌙 תורן: *{on_call_name}*"
    )


def _find_call_by_address(db, address: str):
    """Fuzzy-find an open service call by address hint."""
    from app.models.service_call import ServiceCall
    from app.models.elevator import Elevator

    open_calls = db.query(ServiceCall).filter(
        ServiceCall.status.in_(["OPEN", "ASSIGNED", "IN_PROGRESS"])
    ).all()

    if not address:
        # Return most urgent
        return sorted(open_calls, key=lambda c: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(c.priority, 2))[0] if open_calls else None

    address_lower = address.lower()
    for call in open_calls:
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if elev and (address_lower in (elev.address or "").lower() or address_lower in (elev.city or "").lower()):
            return call
    # Word-level fuzzy
    words = set(address_lower.split())
    for call in open_calls:
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if elev:
            elev_words = set(((elev.address or "") + " " + (elev.city or "")).lower().split())
            if words & elev_words:
                return call
    return None


def _cmd_close_call(db, phone: str, address: str, original_text: str) -> None:
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from datetime import datetime, timezone

    call = _find_call_by_address(db, address)
    if not call:
        _send_message(phone, f"❌ לא נמצאה קריאה פתוחה עם הכתובת: *{address or 'לא צוינה'}*")
        return

    elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    addr = f"{elev.address}, {elev.city}" if elev else "כתובת לא ידועה"

    old_status = call.status
    call.status = "RESOLVED"
    call.resolved_at = datetime.now(timezone.utc)
    call.resolution_notes = f"נסגרה על ידי מנהל: {original_text}"

    # Close any pending assignments
    for a in db.query(Assignment).filter(Assignment.service_call_id == call.id, Assignment.status.in_(["PENDING_CONFIRMATION", "CONFIRMED"])).all():
        a.status = "CANCELLED"

    audit = AuditLog(service_call_id=call.id, changed_by="dispatcher", old_status=old_status, new_status="RESOLVED", notes="נסגרה ע\"י מנהל")
    db.add(audit)
    db.commit()

    _send_message(phone, f"✅ הקריאה ב*{addr}* נסגרה בהצלחה.")
    logger.warning("🗂️ Dispatcher closed call %s at %s", call.id, addr)


def _cmd_assign_tech(db, phone: str, address: str, tech_name: str) -> None:
    from app.models.technician import Technician
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from datetime import datetime, timezone

    # Find technician by name
    tech = None
    if tech_name:
        tech = db.query(Technician).filter(Technician.name.ilike(f"%{tech_name}%")).first()
    if not tech:
        _send_message(phone, f"❌ לא נמצא טכנאי בשם: *{tech_name or 'לא צוין'}*")
        return

    call = _find_call_by_address(db, address)
    if not call:
        _send_message(phone, f"❌ לא נמצאה קריאה פתוחה בכתובת: *{address or 'לא צוינה'}*")
        return

    elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    addr = f"{elev.address}, {elev.city}" if elev else "כתובת לא ידועה"

    # Cancel existing pending assignments
    for a in db.query(Assignment).filter(Assignment.service_call_id == call.id, Assignment.status == "PENDING_CONFIRMATION").all():
        a.status = "CANCELLED"

    assignment = Assignment(
        service_call_id=call.id,
        technician_id=tech.id,
        assignment_type="MANUAL",
        status="PENDING_CONFIRMATION",
        notes="שובץ ידנית ע\"י מנהל",
    )
    db.add(assignment)
    call.status = "ASSIGNED"

    audit = AuditLog(service_call_id=call.id, changed_by="dispatcher", old_status="OPEN", new_status="ASSIGNED", notes=f"שובץ {tech.name} ע\"י מנהל")
    db.add(audit)
    db.commit()

    # Notify technician
    tech_phone = tech.whatsapp_number or tech.phone
    if tech_phone:
        _send_message(tech_phone,
            f"🔧 *קריאה חדשה*\n📍 {addr}\n\nאשר קבלה:\n1️⃣ אישור\n2️⃣ דחייה"
        )

    _send_message(phone, f"✅ *{tech.name}* שובץ לקריאה ב*{addr}* — ממתין לאישורו.")
    notify_dispatcher(f"📋 קריאה שובצה ל*{tech.name}* — {addr} (ע\"י מנהל)")
