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
{{"command": "CLOSE_CALL|ASSIGN_TECH|STATUS_QUERY|REASSIGN_CALL|UPDATE_ADDRESS|DAILY_REPORT|WEEKLY_REPORT|MONTHLY_REPORT|FIND_BY_PHONE|APPROVE_REQUEST|REJECT_REQUEST|ADD_ELEVATOR|UNKNOWN", "address": "כתובת אם קיימת", "tech_name": "שם טכנאי אם קיים", "new_address": "כתובת חדשה אם קיימת", "phone": "מספר טלפון אם קיים"}}

דוגמאות:
"סגור קריאה ברחוב הרצל 5" → CLOSE_CALL
"שבץ תומר לקריאה ברחוב ביאליק" → ASSIGN_TECH
"מה הסטטוס" → STATUS_QUERY
"כמה קריאות פתוחות" → STATUS_QUERY
"בוקר טוב" → UNKNOWN
"העבר קריאה ברחוב X לתומר" → REASSIGN_CALL (tech_name, address)
"הקריאה בכתובת X שייכת לכתובת Y" → UPDATE_ADDRESS (address=X, new_address=Y)
"דוח יומי" → DAILY_REPORT
"דוח שבועי" → WEEKLY_REPORT
"דוח חודשי" → MONTHLY_REPORT
"איזו מעלית שייכת למספר 05XXXXXXXX?" → FIND_BY_PHONE (address contains the phone)
"אשר בקשת תומר" → APPROVE_REQUEST (tech_name=תומר)
"אשר" → APPROVE_REQUEST (tech_name ריק — אשר את כל הבקשות הממתינות)
"דחה בקשת תומר" → REJECT_REQUEST (tech_name=תומר)
"דחה" → REJECT_REQUEST (tech_name ריק — דחה את כל הבקשות הממתינות)
"כן, תוסיף מעלית" → ADD_ELEVATOR
"הוסף מעלית" → ADD_ELEVATOR
"הוסף" → ADD_ELEVATOR (רק אם ההודעה קצרה ומתייחסת להוספת מעלית)

חשוב מאוד — שאלות על מיקום טכנאים, קרבה לאזור, היכן נמצא טכנאי — תמיד UNKNOWN (לא STATUS_QUERY):
"יש לנו מישהו באזור עפולה?" → UNKNOWN
"איפה תומר?" → UNKNOWN
"מי קרוב לחיפה?" → UNKNOWN
"יש טכנאי ליד נצרת?" → UNKNOWN

הודעה: {text}"""


def handle_dispatcher_command(db, phone: str, text: str, settings) -> None:
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from datetime import datetime, timezone

    api_key = getattr(settings, "gemini_api_key", "")

    # Parse command with Gemini
    command, address, tech_name, phone_number = "UNKNOWN", "", "", ""
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
            phone_number = parsed.get("phone", "")
        except Exception as exc:
            logger.error("Dispatcher command parse failed: %s", exc)

    logger.warning("🎯 Dispatcher command: %s | address: %s | tech: %s", command, address, tech_name)

    if command == "STATUS_QUERY":
        _cmd_status(db, phone)
    elif command == "CLOSE_CALL":
        _cmd_close_call(db, phone, address, text)
    elif command == "ASSIGN_TECH":
        _cmd_assign_tech(db, phone, address, tech_name)
    elif command == "REASSIGN_CALL":
        _cmd_reassign_call(db, phone, address, tech_name)
    elif command == "UPDATE_ADDRESS":
        new_addr = parsed.get("new_address", "")
        _cmd_update_address(db, phone, address, new_addr)
    elif command in ("DAILY_REPORT", "WEEKLY_REPORT", "MONTHLY_REPORT"):
        days = 1 if command == "DAILY_REPORT" else 7 if command == "WEEKLY_REPORT" else 30
        _cmd_daily_report(db, phone, days)
    elif command == "FIND_BY_PHONE":
        _cmd_find_by_phone(db, phone, phone_number)
    elif command == "APPROVE_REQUEST":
        _cmd_approve_request(db, phone, tech_name)
    elif command == "REJECT_REQUEST":
        _cmd_reject_request(db, phone, tech_name)
    elif command == "ADD_ELEVATOR":
        _cmd_add_elevator(db, phone)
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


def _cmd_reassign_call(db, phone: str, address: str, tech_name: str) -> None:
    """Reassign a call from one technician to another."""
    from app.models.technician import Technician
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator

    if not tech_name:
        _send_message(phone, "❌ לא צוין שם טכנאי להעברה.")
        return

    tech = db.query(Technician).filter(Technician.name.ilike(f"%{tech_name}%")).first()
    if not tech:
        _send_message(phone, f"❌ לא נמצא טכנאי בשם: *{tech_name}*")
        return

    call = _find_call_by_address(db, address)
    if not call:
        _send_message(phone, f"❌ לא נמצאה קריאה פתוחה בכתובת: *{address or 'לא צוינה'}*")
        return

    elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    addr = f"{elev.address}, {elev.city}" if elev else "כתובת לא ידועה"

    # Cancel existing confirmed/pending assignments
    for a in db.query(Assignment).filter(
        Assignment.service_call_id == call.id,
        Assignment.status.in_(["PENDING_CONFIRMATION", "CONFIRMED"])
    ).all():
        a.status = "CANCELLED"

    # Create new PENDING_CONFIRMATION assignment for the new tech
    assignment = Assignment(
        service_call_id=call.id,
        technician_id=tech.id,
        assignment_type="MANUAL",
        status="PENDING_CONFIRMATION",
        notes=f"הועבר ע\"י מנהל",
    )
    db.add(assignment)
    call.status = "ASSIGNED"

    audit = AuditLog(service_call_id=call.id, changed_by="dispatcher", old_status=call.status, new_status="ASSIGNED",
                     notes=f"הועבר ל{tech.name} ע\"י מנהל")
    db.add(audit)
    db.commit()

    # Notify new tech
    tech_phone = tech.whatsapp_number or tech.phone
    if tech_phone:
        _send_message(tech_phone,
            f"🔧 *קריאה חדשה הועברה אליך*\n📍 {addr}\n\nאשר קבלה:\n1️⃣ אישור\n2️⃣ דחייה"
        )

    _send_message(phone, f"✅ הקריאה ב*{addr}* הועברה ל*{tech.name}* — ממתין לאישורו.")
    logger.warning("🔄 Dispatcher reassigned call %s to %s", call.id, tech.name)


def _cmd_update_address(db, phone: str, old_address: str, new_address: str) -> None:
    """Update the elevator linked to a service call (wrong elevator was matched)."""
    from app.models.elevator import Elevator
    from app.models.assignment import Assignment

    if not new_address:
        _send_message(phone, "❌ לא צוינה כתובת חדשה.")
        return

    call = _find_call_by_address(db, old_address)
    if not call:
        _send_message(phone, f"❌ לא נמצאה קריאה פתוחה בכתובת: *{old_address or 'לא צוינה'}*")
        return

    # Find elevator by new address
    new_elev = (
        db.query(Elevator)
        .filter(
            Elevator.address.ilike(f"%{new_address}%") |
            Elevator.city.ilike(f"%{new_address}%")
        )
        .first()
    )
    if not new_elev:
        _send_message(phone, f"❌ לא נמצאה מעלית בכתובת: *{new_address}*")
        return

    old_elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    old_addr = f"{old_elev.address}, {old_elev.city}" if old_elev else "כתובת לא ידועה"
    new_addr = f"{new_elev.address}, {new_elev.city}"

    # Update call elevator
    call.elevator_id = new_elev.id
    db.commit()

    # Notify assigned technician of address change
    assignment = db.query(Assignment).filter(
        Assignment.service_call_id == call.id,
        Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"])
    ).first()
    if assignment:
        from app.models.technician import Technician
        tech = db.query(Technician).filter(Technician.id == assignment.technician_id).first()
        if tech:
            tech_phone = tech.whatsapp_number or tech.phone
            _send_message(tech_phone,
                f"⚠️ *עדכון כתובת לקריאה שלך*\n"
                f"הכתובת עודכנה:\n"
                f"מ: {old_addr}\n"
                f"ל: *{new_addr}*"
            )

    _send_message(phone, f"✅ הקריאה עודכנה מ*{old_addr}* ל*{new_addr}*.")
    logger.warning("📍 Dispatcher updated call %s address from %s to %s", call.id, old_addr, new_addr)


def _cmd_daily_report(db, phone: str, days: int = 1) -> None:
    """Send a summary report for the last N days."""
    from app.models.service_call import ServiceCall
    from datetime import datetime, timezone, timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)
    resolved = db.query(ServiceCall).filter(
        ServiceCall.status == "RESOLVED",
        ServiceCall.resolved_at >= since
    ).count()
    open_count = db.query(ServiceCall).filter(ServiceCall.status == "OPEN").count()
    in_progress = db.query(ServiceCall).filter(ServiceCall.status == "IN_PROGRESS").count()

    period = "יומי" if days == 1 else "שבועי" if days == 7 else "חודשי"
    _send_message(phone,
        f"📊 *דוח {period}*\n"
        f"✅ טופלו: *{resolved}*\n"
        f"🔴 פתוחות כרגע: *{open_count}*\n"
        f"🔵 בטיפול: *{in_progress}*"
    )


def _cmd_find_by_phone(db, dispatcher_phone: str, search_phone: str) -> None:
    """Find elevators associated with a caller phone number."""
    from app.models.elevator import Elevator

    if not search_phone:
        _send_message(dispatcher_phone, "❌ לא צוין מספר טלפון לחיפוש.")
        return

    digits = "".join(c for c in search_phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    last9 = digits[-9:] if len(digits) >= 9 else digits

    all_elevs = db.query(Elevator).all()
    matches = []
    for e in all_elevs:
        for cp in (e.caller_phones or []):
            cp_d = "".join(c for c in cp if c.isdigit())
            if cp_d[-9:] == last9:
                matches.append(f"• {e.address}, {e.city}" + (f" ({e.building_name})" if e.building_name else ""))
                break

    if not matches:
        _send_message(dispatcher_phone, f"❌ לא נמצאו מעליות עם מספר {search_phone}")
        return

    lines = "\n".join(matches)
    _send_message(dispatcher_phone, f"📞 מעליות עם מספר *{search_phone}*:\n{lines}")


def _cmd_approve_request(db, dispatcher_phone: str, tech_name: str) -> None:
    """
    Approve a technician's pending assignment request (type=REQUEST, status=PENDING_CONFIRMATION).
    Confirms the assignment, sets call to ASSIGNED, and notifies the technician.
    """
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from app.models.technician import Technician
    from datetime import datetime, timezone

    # Find pending technician requests
    pending_requests = (
        db.query(Assignment)
        .filter(
            Assignment.assignment_type == "REQUEST",
            Assignment.status == "PENDING_CONFIRMATION",
        )
        .all()
    )

    if not pending_requests:
        _send_message(dispatcher_phone, "ℹ️ אין בקשות טכנאי ממתינות לאישור.")
        return

    # Filter by tech name if provided
    if tech_name:
        filtered = []
        for a in pending_requests:
            tech = db.query(Technician).filter(Technician.id == a.technician_id).first()
            if tech and tech_name.lower() in tech.name.lower():
                filtered.append((a, tech))
        if not filtered:
            _send_message(dispatcher_phone, f"❌ לא נמצאה בקשה ממתינה מטכנאי בשם: *{tech_name}*")
            return
    else:
        # No name given — approve all pending requests
        filtered = []
        for a in pending_requests:
            tech = db.query(Technician).filter(Technician.id == a.technician_id).first()
            if tech:
                filtered.append((a, tech))

    approved = []
    for assignment, tech in filtered:
        from app.models.service_call import ServiceCall
        call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
        if not call:
            continue

        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"

        # Confirm the assignment
        assignment.status = "CONFIRMED"
        call.status = "ASSIGNED"
        call.assigned_at = datetime.now(timezone.utc)

        audit = AuditLog(
            service_call_id=call.id,
            changed_by="dispatcher",
            old_status="OPEN",
            new_status="ASSIGNED",
            notes=f"בקשת {tech.name} אושרה על ידי מוקד",
        )
        db.add(audit)

        # Notify technician
        tech_phone = tech.whatsapp_number or tech.phone
        if tech_phone:
            travel_str = f"\n🚗 זמן נסיעה משוער: ~{assignment.travel_minutes} דק'" if assignment.travel_minutes else ""
            _send_message(
                tech_phone,
                f"✅ *בקשתך אושרה!*\n"
                f"📍 קריאה ב*{addr}* שובצה אליך."
                f"{travel_str}\n\n"
                f"בסיום הטיפול, שלח *דוח* + תיאור קצר לסגירה."
            )

        approved.append(f"{tech.name} → {addr}")
        logger.warning("✅ Dispatcher approved request: %s → call %s at %s", tech.name, call.id, addr)

    db.commit()

    if approved:
        lines = "\n".join(f"• {item}" for item in approved)
        _send_message(dispatcher_phone, f"✅ *אושרו {len(approved)} בקשות:*\n{lines}")
    else:
        _send_message(dispatcher_phone, "❌ לא נמצאו בקשות מתאימות לאישור.")


def _cmd_reject_request(db, dispatcher_phone: str, tech_name: str) -> None:
    """
    Reject a technician's pending assignment request.
    Cancels the assignment, returns call to OPEN, and notifies the technician.
    """
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from app.models.technician import Technician

    pending_requests = (
        db.query(Assignment)
        .filter(
            Assignment.assignment_type == "REQUEST",
            Assignment.status == "PENDING_CONFIRMATION",
        )
        .all()
    )

    if not pending_requests:
        _send_message(dispatcher_phone, "ℹ️ אין בקשות טכנאי ממתינות לדחייה.")
        return

    if tech_name:
        filtered = []
        for a in pending_requests:
            tech = db.query(Technician).filter(Technician.id == a.technician_id).first()
            if tech and tech_name.lower() in tech.name.lower():
                filtered.append((a, tech))
        if not filtered:
            _send_message(dispatcher_phone, f"❌ לא נמצאה בקשה ממתינה מטכנאי בשם: *{tech_name}*")
            return
    else:
        filtered = []
        for a in pending_requests:
            tech = db.query(Technician).filter(Technician.id == a.technician_id).first()
            if tech:
                filtered.append((a, tech))

    rejected = []
    for assignment, tech in filtered:
        from app.models.service_call import ServiceCall
        call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
        if not call:
            continue

        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"

        assignment.status = "CANCELLED"
        # Call stays OPEN — available for other technicians or dispatcher

        audit = AuditLog(
            service_call_id=call.id,
            changed_by="dispatcher",
            old_status="OPEN",
            new_status="OPEN",
            notes=f"בקשת {tech.name} נדחתה על ידי מוקד",
        )
        db.add(audit)

        tech_phone = tech.whatsapp_number or tech.phone
        if tech_phone:
            _send_message(
                tech_phone,
                f"❌ בקשתך לטפל בקריאה ב*{addr}* נדחתה על ידי המוקד.\n"
                f"ניתן לפנות למוקד לפרטים נוספים."
            )

        rejected.append(f"{tech.name} → {addr}")
        logger.warning("❌ Dispatcher rejected request: %s → call %s at %s", tech.name, call.id, addr)

    db.commit()

    if rejected:
        lines = "\n".join(f"• {item}" for item in rejected)
        _send_message(dispatcher_phone, f"✅ *נדחו {len(rejected)} בקשות:*\n{lines}")
    else:
        _send_message(dispatcher_phone, "❌ לא נמצאו בקשות מתאימות לדחייה.")


def _cmd_add_elevator(db, dispatcher_phone: str) -> None:
    """Create a new elevator from the most recent unmatched incoming call."""
    from app.models.incoming_call import IncomingCallLog
    from app.models.elevator import Elevator
    from app.services.call_parser import parse_email
    from app.services import service_call_service, ai_assignment_agent
    from app.schemas.service_call import ServiceCallCreate

    log = (
        db.query(IncomingCallLog)
        .filter(
            IncomingCallLog.match_status.in_(["PARTIAL", "UNMATCHED"]),
            IncomingCallLog.service_call_id.is_(None),
        )
        .order_by(IncomingCallLog.created_at.desc())
        .first()
    )

    if not log:
        _send_message(dispatcher_phone, "ℹ️ אין קריאות ממתינות ללא מעלית משויכת.")
        return

    # Re-parse to get house_number
    parsed = parse_email(log.raw_text or "")
    address_parts = [log.call_street or parsed.street]
    if parsed.house_number:
        address_parts.append(parsed.house_number)
    full_address = " ".join(p for p in address_parts if p).strip() or "כתובת לא ידועה"
    city = log.call_city or parsed.city or "לא ידוע"

    elevator = Elevator(
        address=full_address,
        city=city,
        floor_count=5,
        caller_phones=[log.caller_phone] if log.caller_phone else [],
    )
    db.add(elevator)
    db.flush()

    call_data = ServiceCallCreate(
        elevator_id=elevator.id,
        reported_by=log.caller_name or log.caller_phone or "מוקד טלפוני",
        description=log.call_type or "קריאת שירות",
        priority=log.priority or "MEDIUM",
        fault_type=log.fault_type or "OTHER",
    )
    service_call = service_call_service.create_service_call(db, call_data, "dispatcher@whatsapp")

    log.elevator_id = elevator.id
    log.service_call_id = service_call.id
    log.match_status = "MATCHED"
    log.match_notes = "מעלית חדשה נוספה על ידי מנהל"
    db.commit()

    try:
        ai_assignment_agent.assign_with_confirmation(db, service_call)
    except Exception as exc:
        logger.warning("AI assignment after WhatsApp add-elevator failed: %s", exc)

    _send_message(
        dispatcher_phone,
        f"✅ *מעלית חדשה נוספה ושובצה*\n"
        f"📍 {full_address}, {city}\n"
        f"🔧 קריאת שירות נפתחה — מחפש טכנאי."
    )
    logger.warning("🏗️ Dispatcher added elevator: %s, %s via WhatsApp", full_address, city)
