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
  "address": "כתובת מלאה של המעלית כולל עיר (לדוגמה: רחוב הרצל 5, חיפה)",
  "inspection_date": "YYYY-MM-DD או null אם לא ידוע",
  "result": "PASS אם הכל תקין, FAIL אם יש ליקויים",
  "deficiencies": [
    {"description": "תיאור הליקוי בעברית", "severity": "HIGH|MEDIUM|LOW"}
  ],
  "inspector_name": "שם הבודק או null",
  "serial_number": "מספר סידורי של המעלית או null"
}

חוקים:
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

    address = (parsed.get("address") or "").strip()
    inspection_date_str = parsed.get("inspection_date")
    result_str = parsed.get("result", "UNKNOWN").upper()
    deficiencies = parsed.get("deficiencies") or []
    inspector_name = parsed.get("inspector_name")
    serial_number = parsed.get("serial_number")

    # Parse inspection date
    inspection_date = None
    if inspection_date_str:
        try:
            inspection_date = datetime.strptime(inspection_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Find elevator — try serial number first, then address fuzzy match
    elevator = None
    if serial_number:
        elevator = db.query(Elevator).filter(Elevator.serial_number == str(serial_number)).first()

    if not elevator and address:
        city, street = "", address
        if "," in address:
            parts = [p.strip() for p in address.rsplit(",", 1)]
            street, city = parts[0], parts[1]
        parsed_call = ParsedCall(
            name="inspection", phone="", city=city, street=street,
            house_number="", floor="", call_type="", context="",
            call_time="", fault_type="OTHER", priority="MEDIUM",
            description="ביקורת תקינות",
        )
        match = find_elevator(db, parsed_call)
        if match.elevator and match.score >= 0.3:
            elevator = match.elevator

    # Create inspection report record
    report = InspectionReport(
        elevator_id=elevator.id if elevator else None,
        source=source,
        file_name=file_name,
        raw_address=address,
        inspection_date=inspection_date,
        result=result_str if result_str in ("PASS", "FAIL") else "UNKNOWN",
        inspector_name=inspector_name,
        deficiency_count=len(deficiencies),
        deficiencies=deficiencies if deficiencies else None,
    )
    db.add(report)

    if not elevator:
        msg = f"⚠️ דוח ביקורת — לא נמצאה מעלית לכתובת: {address or 'לא ידוע'}"
        logger.warning(msg)
        db.commit()
        db.refresh(report)
        for num in (settings.dispatcher_whatsapp or "").split(","):
            n = num.strip()
            if n:
                send_whatsapp_message(n, msg)
        return {"status": "no_elevator", "report_id": str(report.id), "message": msg}

    # Update elevator last service date
    if inspection_date:
        elevator.last_service_date = inspection_date
        db.commit()

    # No deficiencies — clean inspection
    if not deficiencies or result_str == "PASS":
        db.commit()
        db.refresh(report)
        msg = f"✅ ביקורת תקינה: {elevator.address}, {elevator.city}"
        if inspection_date:
            msg += f" ({inspection_date.strftime('%d/%m/%Y')})"
        for num in (settings.dispatcher_whatsapp or "").split(","):
            n = num.strip()
            if n:
                send_whatsapp_message(n, msg)
        return {"status": "clean", "report_id": str(report.id), "elevator_id": str(elevator.id), "message": msg}

    # Has deficiencies — create service call
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
