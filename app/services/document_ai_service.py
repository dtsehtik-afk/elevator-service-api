"""
Document AI Analysis Service — extracts structured data from uploaded PDFs/contracts/agreements.

Flow:
  1. Receive PDF bytes + entity reference (type + id)
  2. Send to Gemini Vision with a structured extraction prompt
  3. Store result in document_analyses table
  4. Auto-populate empty fields on the linked entity
  5. Return the analysis record
"""

import base64
import json
import logging
import os
import uuid
from datetime import datetime, date

import httpx
from sqlalchemy.orm import Session

from app.models.document_analysis import DocumentAnalysis

logger = logging.getLogger(__name__)

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

_EXTRACT_PROMPT = """
אתה מנתח מסמכים עסקיים של חברות מעליות.
ניתח את המסמך המצורף ושלוף את המידע הבא בפורמט JSON בלבד — ללא טקסט נוסף, ללא markdown.

הפורמט הנדרש:
{
  "document_type": "SERVICE_AGREEMENT|MAINTENANCE_CONTRACT|INSPECTION_REPORT|QUOTE|SALES_CONTRACT|OTHER",
  "customer": {
    "name": null,
    "phone": null,
    "email": null,
    "address": null,
    "city": null
  },
  "elevator": {
    "address": null,
    "city": null,
    "floor_count": null,
    "serial_number": null,
    "labor_file_number": null,
    "elevator_type": null,
    "building_name": null,
    "manufacturer": null
  },
  "contract": {
    "type": null,
    "start_date": null,
    "end_date": null,
    "monthly_price": null,
    "total_value": null,
    "payment_terms_days": null,
    "services_included": [],
    "auto_renew": null
  },
  "inspection": {
    "date": null,
    "result": null,
    "inspector_name": null,
    "next_inspection_date": null,
    "deficiencies": []
  },
  "summary": "תקציר קצר בעברית של המסמך — שורה אחת"
}

כללים:
- החזר null לשדות שאינם מופיעים במסמך
- תאריכים בפורמט YYYY-MM-DD
- מחירים כמספר בלבד (ללא סימן מטבע)
- labor_file_number = מספר תיק עבודה / מספר רישיון / מספר משרד העבודה
- אם המסמך הוא חוזה שירות — מלא את contract, אם בדיקה — מלא את inspection
"""


def analyze_document(
    db: Session,
    file_bytes: bytes,
    filename: str,
    entity_type: str,
    entity_id: str | None,
    created_by: str = "",
    gemini_api_key: str = "",
) -> DocumentAnalysis:
    """
    Analyze a PDF/image document with Gemini Vision, persist result, and auto-fill entity fields.
    Returns the saved DocumentAnalysis record.
    """
    from app.config import get_settings
    if not gemini_api_key:
        gemini_api_key = get_settings().gemini_api_key or ""

    # Save file locally
    os.makedirs("uploads/documents", exist_ok=True)
    doc_id = uuid.uuid4()
    ext = os.path.splitext(filename)[-1].lower() or ".pdf"
    local_path = f"uploads/documents/{doc_id}{ext}"
    with open(local_path, "wb") as f:
        f.write(file_bytes)

    record = DocumentAnalysis(
        id=doc_id,
        entity_type=entity_type,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        filename=filename,
        file_path=local_path,
        status="PENDING",
        created_by=created_by,
    )
    db.add(record)
    db.flush()

    if not gemini_api_key:
        record.status = "ERROR"
        record.error_message = "GEMINI_API_KEY not configured"
        db.commit()
        return record

    try:
        extracted = _call_gemini(file_bytes, filename, gemini_api_key)
        record.extracted_data = extracted
        record.document_type = extracted.get("document_type")
        record.summary_text = extracted.get("summary")
        record.status = "PROCESSED"

        # Auto-fill linked entity
        filled = {}
        if entity_id:
            filled = _auto_fill(db, entity_type, entity_id, extracted)
        record.auto_filled = filled

    except Exception as exc:
        logger.error("Document analysis failed for %s: %s", filename, exc)
        record.status = "ERROR"
        record.error_message = str(exc)

    db.commit()
    db.refresh(record)
    return record


def _call_gemini(file_bytes: bytes, filename: str, api_key: str) -> dict:
    """Send file to Gemini Vision and return parsed extraction dict."""
    mime = "application/pdf"
    low = filename.lower()
    if low.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif low.endswith(".png"):
        mime = "image/png"
    elif low.endswith(".webp"):
        mime = "image/webp"

    b64 = base64.b64encode(file_bytes).decode()

    payload = {
        "contents": [{
            "parts": [
                {"text": _EXTRACT_PROMPT},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{_GEMINI_URL}?key={api_key}",
            json=payload,
        )
        resp.raise_for_status()

    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def _auto_fill(db: Session, entity_type: str, entity_id: str, data: dict) -> dict:
    """Write extracted fields into the linked entity, skipping non-empty fields."""
    filled: dict = {}
    try:
        eid = uuid.UUID(entity_id)
        if entity_type == "ELEVATOR":
            filled = _fill_elevator(db, eid, data)
        elif entity_type == "CONTRACT":
            filled = _fill_contract(db, eid, data)
        elif entity_type == "LEAD":
            filled = _fill_lead(db, eid, data)
        elif entity_type == "PROJECT":
            filled = _fill_project(db, eid, data)
        elif entity_type == "CUSTOMER":
            filled = _fill_customer(db, eid, data)
    except Exception as exc:
        logger.warning("Auto-fill failed for %s %s: %s", entity_type, entity_id, exc)
    return filled


def _set_if_empty(obj, field: str, value, filled: dict):
    if value is not None and not getattr(obj, field, None):
        setattr(obj, field, value)
        filled[field] = value


def _parse_date(val) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(str(val))
    except Exception:
        return None


def _fill_elevator(db: Session, eid: uuid.UUID, data: dict) -> dict:
    from app.models.elevator import Elevator
    elev = db.query(Elevator).filter(Elevator.id == eid).first()
    if not elev:
        return {}
    filled: dict = {}
    ev = data.get("elevator") or {}
    _set_if_empty(elev, "address", ev.get("address"), filled)
    _set_if_empty(elev, "city", ev.get("city"), filled)
    _set_if_empty(elev, "building_name", ev.get("building_name"), filled)
    _set_if_empty(elev, "serial_number", ev.get("serial_number"), filled)
    _set_if_empty(elev, "labor_file_number", ev.get("labor_file_number"), filled)
    if ev.get("floor_count") and not elev.floor_count:
        try:
            elev.floor_count = int(ev["floor_count"])
            filled["floor_count"] = elev.floor_count
        except (ValueError, TypeError):
            pass
    # Link customer if found by name
    cust = data.get("customer") or {}
    if cust.get("name") and not elev.customer_id:
        from app.models.customer import Customer
        c = db.query(Customer).filter(Customer.name.ilike(f"%{cust['name']}%")).first()
        if c:
            elev.customer_id = c.id
            filled["customer_id"] = str(c.id)
    db.flush()
    return filled


def _fill_contract(db: Session, eid: uuid.UUID, data: dict) -> dict:
    from app.models.contract import Contract
    contract = db.query(Contract).filter(Contract.id == eid).first()
    if not contract:
        return {}
    filled: dict = {}
    ct = data.get("contract") or {}
    _set_if_empty(contract, "notes", data.get("summary"), filled)
    if ct.get("start_date") and not contract.start_date:
        d = _parse_date(ct["start_date"])
        if d:
            contract.start_date = d
            filled["start_date"] = str(d)
    if ct.get("end_date") and not contract.end_date:
        d = _parse_date(ct["end_date"])
        if d:
            contract.end_date = d
            filled["end_date"] = str(d)
    if ct.get("monthly_price") and not contract.monthly_price:
        try:
            contract.monthly_price = float(ct["monthly_price"])
            filled["monthly_price"] = contract.monthly_price
        except (ValueError, TypeError):
            pass
    db.flush()
    return filled


def _fill_lead(db: Session, eid: uuid.UUID, data: dict) -> dict:
    from app.models.lead import Lead
    lead = db.query(Lead).filter(Lead.id == eid).first()
    if not lead:
        return {}
    filled: dict = {}
    cust = data.get("customer") or {}
    _set_if_empty(lead, "name", cust.get("name"), filled)
    _set_if_empty(lead, "phone", cust.get("phone"), filled)
    _set_if_empty(lead, "email", cust.get("email"), filled)
    _set_if_empty(lead, "company", cust.get("name"), filled)
    # Append summary to notes
    summary = data.get("summary")
    if summary:
        existing = lead.notes or ""
        lead.notes = (existing + "\n\n" + summary).strip() if existing else summary
        filled["notes"] = lead.notes
    db.flush()
    return filled


def _fill_project(db: Session, eid: uuid.UUID, data: dict) -> dict:
    from app.models.project import Project
    project = db.query(Project).filter(Project.id == eid).first()
    if not project:
        return {}
    filled: dict = {}
    summary = data.get("summary")
    if summary:
        existing = project.description or ""
        project.description = (existing + "\n\n" + summary).strip() if existing else summary
        filled["description"] = project.description
    db.flush()
    return filled


def _fill_customer(db: Session, eid: uuid.UUID, data: dict) -> dict:
    from app.models.customer import Customer
    customer = db.query(Customer).filter(Customer.id == eid).first()
    if not customer:
        return {}
    filled: dict = {}
    cust = data.get("customer") or {}
    _set_if_empty(customer, "phone", cust.get("phone"), filled)
    _set_if_empty(customer, "email", cust.get("email"), filled)
    _set_if_empty(customer, "address", cust.get("address"), filled)
    _set_if_empty(customer, "city", cust.get("city"), filled)
    db.flush()
    return filled
