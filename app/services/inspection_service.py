"""
Inspection report processing service.
Reads PDF/image files, extracts structured data using Gemini Vision,
then updates elevator records or opens service calls for deficiencies.
"""

import base64
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_INSPECTION_PROMPT = """אתה מנתח דוחות ביקורת תקינות מעליות בישראל.
קרא את המסמך המצורף וחלץ את המידע הבא. החזר JSON בלבד ללא כל טקסט נוסף, ללא markdown:

{
  "street": "שם הרחוב ומספר הבית בלבד, ללא שם הבניין וללא שם העיר (לדוגמה: מנחם בגין 80)",
  "city": "שם העיר בלבד (לדוגמה: עפולה)",
  "labor_file_number": "מספר תיק במשרד העבודה — מספר שמופיע ליד הכיתוב 'מס תיק במשרד העבודה' או 'מס תיק'. לדוגמה: 7022",
  "inspection_date": "YYYY-MM-DD או null אם לא ידוע",
  "result": "PASS אם הכל תקין, FAIL אם יש ליקויים",
  "deficiencies": [
    {"description": "תיאור הליקוי בעברית", "severity": "HIGH|MEDIUM|LOW"}
  ],
  "inspector_name": "שם הבודק או null",
  "serial_number": "מספר סידורי של המעלית או null"
}

חוקים:
- street: רחוב + מספר בית בלבד — לא לכלול שם בניין, לא לכלול עיר
- city: עיר בלבד
- labor_file_number: מספר ספרות בלבד, ללא טקסט (לדוגמה: "7022" ולא "מס 7022")
- אם אין ליקויים, deficiencies = []
- severity: HIGH=מסוכן/דחוף, MEDIUM=רגיל, LOW=קוסמטי/קל
- אם result לא ברור, הסק לפי נוכחות ליקויים
- החזר JSON תקני בלבד"""


def _call_gemini_vision(file_bytes: bytes, mime_type: str, api_key: str) -> Optional[dict]:
    """Send file to Gemini Vision and return parsed inspection data."""
    b64 = base64.b64encode(file_bytes).decode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": _INSPECTION_PROMPT},
                {"inline_data": {"mime_type": mime_type, "data": b64}},
            ]
        }],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1500},
    }
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            raw = (
                resp.json()
                .get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
    except Exception as exc:
        logger.error("Gemini Vision failed: %s", exc)
        return None


def process_inspection_report(
    db: Session,
    file_bytes: bytes,
    mime_type: str,
    file_name: str = "",
    source: str = "upload",
) -> dict:
    """
    Process a single inspection report file.
    Returns result dict with: status, report_id, elevator_id, call_id, message
    """
    from app.config import get_settings
    from app.models.elevator import Elevator
    from app.models.inspection_report import InspectionReport
    from app.schemas.service_call import ServiceCallCreate
    from app.services import service_call_service
    from app.services.call_parser import find_elevator, ParsedCall
    from app.services.whatsapp_service import _send_message as send_whatsapp_message

    settings = get_settings()
    if not settings.gemini_api_key:
        return {"status": "error", "message": "Gemini API key not configured"}

    parsed = _call_gemini_vision(file_bytes, mime_type, settings.gemini_api_key)
    if not parsed:
        return {"status": "error", "message": "Failed to parse inspection report with Gemini"}

    logger.info("Inspection parsed from %s: %s", file_name, parsed)

    street = (parsed.get("street") or "").strip()
    city = (parsed.get("city") or "").strip()
    # Backwards-compat: if old "address" field returned instead of street/city
    if not street and not city:
        address = (parsed.get("address") or "").strip()
        if "," in address:
            parts = [p.strip() for p in address.split(",", 1)]
            street, city = parts[0], parts[1]
        else:
            street = address
    address = f"{street}, {city}".strip(", ")

    inspection_date_str = parsed.get("inspection_date")
    result_str = parsed.get("result", "UNKNOWN").upper()
    deficiencies = parsed.get("deficiencies") or []
    inspector_name = parsed.get("inspector_name")
    serial_number = parsed.get("serial_number")
    labor_file_number = (parsed.get("labor_file_number") or "").strip() or None

    # Parse inspection date
    inspection_date = None
    if inspection_date_str:
        try:
            inspection_date = datetime.strptime(inspection_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # ── Elevator matching — ספק = אין ספק ──────────────────────────────────────
    # Tier 1: serial number → definitive match (AUTO_MATCHED)
    # Tier 2: fuzzy score >= 0.65 → confident address match (AUTO_MATCHED)
    # Tier 3: 0.30 <= score < 0.65 → uncertain, ask dispatcher (PENDING_REVIEW)
    # Tier 4: score < 0.30 or no street → cannot match (UNMATCHED)

    _PARTIAL_THRESHOLD = 0.30  # minimum score to suggest a candidate for review

    elevator = None
    suggested_elevator = None
    match_score = None
    match_status = "UNMATCHED"

    # Tier 0: Labor Ministry file number — definitive, unique per elevator
    if labor_file_number:
        elevator = db.query(Elevator).filter(Elevator.labor_file_number == labor_file_number).first()
        if elevator:
            match_status = "AUTO_MATCHED"
            match_score = 1.0

    # Tier 1: serial number
    if not elevator and serial_number:
        elevator = db.query(Elevator).filter(Elevator.serial_number == str(serial_number)).first()
        if elevator:
            match_status = "AUTO_MATCHED"
            match_score = 1.0

    if not elevator and street:
        # Extract house number from street string (trailing digits) so the
        # penalty/bonus logic in _score_elevator applies correctly.
        import re as _re
        _hn_match = _re.search(r'(\d+)\s*$', street)
        house_number = _hn_match.group(1) if _hn_match else ""

        parsed_call = ParsedCall(
            name="inspection", phone="", city=city, street=street,
            house_number=house_number, floor="", call_type="", context="",
            call_time="", fault_type="OTHER", priority="MEDIUM",
            description="ביקורת תקינות",
        )
        match = find_elevator(db, parsed_call)
        match_score = match.score if match.elevator else 0.0

        # Address fuzzy matching always requires human confirmation.
        # Only labor_file_number and serial_number are trusted for auto-match.
        if match.elevator and match_score >= _PARTIAL_THRESHOLD:
            suggested_elevator = match.elevator
            match_status = "PENDING_REVIEW"
        else:
            match_status = "UNMATCHED"

    # Create inspection report record
    report = InspectionReport(
        elevator_id=elevator.id if elevator else None,
        suggested_elevator_id=suggested_elevator.id if suggested_elevator else None,
        source=source,
        file_name=file_name,
        raw_address=address,
        raw_street=street,
        raw_city=city,
        labor_file_number=labor_file_number,
        inspection_date=inspection_date,
        result=result_str if result_str in ("PASS", "FAIL") else "UNKNOWN",
        inspector_name=inspector_name,
        deficiency_count=len(deficiencies),
        deficiencies=deficiencies if deficiencies else None,
        match_status=match_status,
        match_score=round(match_score, 3) if match_score is not None else None,
    )
    db.add(report)

    # Enrich elevator with new data learned from this report
    if elevator:
        if labor_file_number and not elevator.labor_file_number:
            elevator.labor_file_number = labor_file_number

    # ── PENDING_REVIEW: notify dispatcher to confirm ──────────────────────────
    if match_status == "PENDING_REVIEW":
        suggested_addr = f"{suggested_elevator.address}, {suggested_elevator.city}" if suggested_elevator else "—"
        # Explain why confirmation is needed
        if suggested_elevator and house_number and house_number not in (suggested_elevator.address or ""):
            reason = f"מספר בית בדוח: *{house_number}* — לא תואם לכתובת המוצעת"
        else:
            reason = f"ציון התאמה: {match_score:.0%} — מתחת לסף הוודאות"
        msg = (
            f"🔍 *דוח ביקורת ממתין לאישור*\n"
            f"כתובת בדוח: *{address or 'לא ידוע'}*\n"
            f"מעלית מוצעת: {suggested_addr}\n"
            f"סיבה: {reason}\n"
            f"בודק: {inspector_name or 'לא ידוע'}\n"
            f"אנא אשר/דחה בדשבורד תחת 'דוחות ביקורת'."
        )
        logger.warning("Inspection PENDING_REVIEW: %s → suggested %s (%.0f%%)", address, suggested_addr, (match_score or 0) * 100)
        db.commit()
        db.refresh(report)
        for num in (settings.dispatcher_whatsapp or "").split(","):
            n = num.strip()
            if n:
                send_whatsapp_message(n, msg)
        return {"status": "pending_review", "report_id": str(report.id), "message": msg}

    # ── UNMATCHED: notify dispatcher ─────────────────────────────────────────
    if match_status == "UNMATCHED":
        msg = f"⚠️ דוח ביקורת — לא נמצאה מעלית לכתובת: {address or 'לא ידוע'}"
        logger.warning(msg)
        db.commit()
        db.refresh(report)
        for num in (settings.dispatcher_whatsapp or "").split(","):
            n = num.strip()
            if n:
                send_whatsapp_message(n, msg)
        return {"status": "no_elevator", "report_id": str(report.id), "message": msg}

    # ── AUTO_MATCHED: proceed with update ────────────────────────────────────
    db.commit()
    db.refresh(report)
    return _apply_inspection_to_elevator(db, report, elevator)


def _apply_inspection_to_elevator(db: Session, report, elevator) -> dict:
    """
    Apply a confirmed inspection report to an elevator:
    - Update last_service_date
    - Send WhatsApp notification
    - Open a service call if deficiencies found
    Called for both AUTO_MATCHED and MANUALLY_CONFIRMED reports.
    """
    from app.services.whatsapp_service import _send_message as send_whatsapp_message
    from app.schemas.service_call import ServiceCallCreate
    from app.services import service_call_service
    from app.config import get_settings

    settings = get_settings()
    deficiencies = report.deficiencies or []
    inspection_date = report.inspection_date
    inspector_name = report.inspector_name

    # Enrich elevator with any new data learned from this report
    if getattr(report, "labor_file_number", None) and not elevator.labor_file_number:
        elevator.labor_file_number = report.labor_file_number

    if inspection_date:
        elevator.last_service_date = inspection_date
        db.commit()

    if not deficiencies or report.result == "PASS":
        db.refresh(report)
        msg = f"✅ ביקורת תקינה: {elevator.address}, {elevator.city}"
        if inspection_date:
            msg += f" ({inspection_date.strftime('%d/%m/%Y')})"
        for num in (settings.dispatcher_whatsapp or "").split(","):
            n = num.strip()
            if n:
                send_whatsapp_message(n, msg)
        return {"status": "clean", "report_id": str(report.id), "elevator_id": str(elevator.id), "message": msg}

    severities = [d.get("severity", "MEDIUM") for d in deficiencies]
    priority = "HIGH" if "HIGH" in severities else ("MEDIUM" if "MEDIUM" in severities else "LOW")
    deficiency_text = "\n".join(
        f"• {d.get('description', '')} [{d.get('severity', 'MEDIUM')}]"
        for d in deficiencies
    )
    call_data = ServiceCallCreate(
        elevator_id=elevator.id,
        reported_by=f"ביקורת תקינות — {inspector_name or 'בודק לא ידוע'}",
        description=f"ליקויים שנמצאו בביקורת ({inspection_date or 'תאריך לא ידוע'}):\n{deficiency_text}",
        priority=priority,
        fault_type="OTHER",
    )

    call = None
    try:
        call = service_call_service.create_service_call(db, call_data, "inspection@system")
        report.service_call_id = call.id
        db.commit()
        db.refresh(report)
    except Exception as exc:
        logger.error("Failed to create service call for inspection: %s", exc)
        db.commit()
        db.refresh(report)

    msg = (
        f"🔍 דוח ביקורת — {elevator.address}, {elevator.city}\n"
        f"נמצאו {len(deficiencies)} ליקויים (עדיפות: {priority}):\n"
        f"{deficiency_text}\n"
        f"{'נפתחה קריאת שירות אוטומטית' if call else 'שגיאה בפתיחת קריאה'}"
    )
    for num in (settings.dispatcher_whatsapp or "").split(","):
        n = num.strip()
        if n:
            send_whatsapp_message(n, msg)

    return {
        "status": "deficiencies_found",
        "report_id": str(report.id),
        "elevator_id": str(elevator.id),
        "call_id": str(call.id) if call else None,
        "deficiency_count": len(deficiencies),
        "message": msg,
    }
