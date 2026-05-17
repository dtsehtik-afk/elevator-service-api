"""
AI-powered Excel elevator import.
Uses Gemini to map arbitrary column names → elevator model fields.
Row = one elevator (or customer).
"""

import io
import json
import logging
import os
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)

# All elevator model fields that can be imported, with descriptions for the AI
FIELD_DESCRIPTIONS = {
    "internal_number": "מספר מס\"ד / מזהה ממערכת ישנה / מספר פנימי",
    "labor_file_number": "מספר תיק משרד העבודה / מספר מעלית / מס' מע'",
    "address": "כתובת רחוב ומספר",
    "city": "עיר / ישוב",
    "building_name": "שם בניין / כינוי",
    "floor_count": "מספר קומות / קומות",
    "manufacturer": "יצרן / חברה מייצרת",
    "model": "דגם / מודל",
    "serial_number": "מספר סידורי / מס' סידורי",
    "installation_date": "תאריך התקנה",
    "warranty_end": "תום אחריות / תאריך סיום אחריות",
    "service_type": "סוג שירות / סוג חוזה (ערכים: REGULAR/רגיל, COMPREHENSIVE/מקיף)",
    "maintenance_times_per_year": "תדירות תחזוקה / ביקורים בשנה (מספר: 2/4/6/12)",
    "contract_start": "תחילת חיוב / תחילת חוזה",
    "contract_renewal": "תאריך חידוש חוזה",
    "contract_end": "תום חוזה / סיום חוזה",
    "last_service_date": "תאריך תחזוקה אחרון / ד.ת אחרון / ביקור אחרון",
    "next_service_date": "תאריך תחזוקה הבא / ט.מ / ביקור הבא",
    "last_inspection_date": "תאריך בדיקה אחרון / ד. בודק",
    "next_inspection_date": "תאריך בדיקה הבא",
    "inspector_name": "שם בודק / בודק מוסמך",
    "inspector_phone": "טלפון בודק",
    "intercom_phone": "טלפון חייגן / חייגן",
    "contact_phone": "טלפון ועד / טלפון קשר",
    "is_coded": "קוד כניסה / קודן (כן/לא/true/false)",
    "entry_code": "קוד כניסה / קוד",
    "has_debt": "חוב (כן/לא/true/false)",
    "motor_type": "סוג מנוע",
    "controller_model": "דגם בקר / פיקוד",
    "door_type": "סוג דלת",
    "pit_depth_cm": "עומק בור (ס\"מ)",
    "headroom_cm": "גובה חדר מכונות (ס\"מ)",
    "safety_certificate_expiry": "תוקף תעודת בטיחות",
    "engine_serial": "מספר סידורי מנוע",
    "controller_serial": "מספר סידורי פיקוד / בקר",
    "load_capacity_kg": "משקל נשיאה / קיבולת (ק\"ג)",
    "max_persons": "מספר נוסעים / תפוסה",
    "speed_m_s": "מהירות (מ/ש)",
    "stops_count": "מספר תחנות",
    "doors_count": "מספר דלתות",
    "door_width_cm": "רוחב דלת (ס\"מ)",
    "cabin_finish": "גימור תא / ציפוי",
    "floor_type": "סוג רצפה",
    "accessibility_compliant": "תקן נגישות (כן/לא)",
    "fire_system_connected": "גלאי אש (כן/לא)",
    "generator_connected": "גנרטור (כן/לא)",
    "iot_gateway_ip": "כתובת IP / IoT",
    "installation_status": "סטטוס התקנה (פעיל/בבניה/מושבת)",
    "handover_date": "תאריך מסירה ללקוח",
    "dismantle_date": "תאריך פירוק",
    "notes": "הערות",
    "lead_source": "נכנסה מ / מקור לקוח",
    "status": "סטטוס (ACTIVE/INACTIVE/UNDER_REPAIR)",
}

_SENTINEL_YEARS = {2050, 2051}
_DUMMY_DATE_STRINGS = {"01/01/51", "1/1/51", "01/01/2051", "1/1/2051", "0"}


def _fix_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.year in _SENTINEL_YEARS:
            return None
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s in _DUMMY_DATE_STRINGS:
        return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            d = datetime.strptime(s, fmt).date()
            if d.year in _SENTINEL_YEARS or d.year > 2040:
                return None
            return d
        except ValueError:
            continue
    return None


def _fix_bool(value) -> Optional[bool]:
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("כן", "yes", "true", "1", "y", "t"):
        return True
    if s in ("לא", "no", "false", "0", "n", "f"):
        return False
    return None


def _fix_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None


def _fix_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return None


def _fix_str(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _fix_service_type(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if s in ("2", "מקיף", "COMPREHENSIVE", "comprehensive"):
        return "COMPREHENSIVE"
    if s in ("1", "רגיל", "REGULAR", "regular"):
        return "REGULAR"
    return None


def _map_columns_with_ai(headers: list) -> dict:
    """Use Gemini to map arbitrary Excel column names → elevator field names."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set; using heuristic column mapping")
        return _heuristic_map(headers)

    field_list = "\n".join(f"  {k}: {v}" for k, v in FIELD_DESCRIPTIONS.items())
    prompt = f"""You are a data mapping assistant for an elevator service company.
Map each Excel column header to the correct elevator database field.

Available fields:
{field_list}

Excel column headers (list):
{json.dumps(headers, ensure_ascii=False)}

Return ONLY a JSON object mapping each header to a field name (or null if no match).
Example: {{"כתובת": "address", "עיר": "city", "מס\\"ד": "internal_number"}}
Only map to fields listed above. Return null for columns that don't match any field."""

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Extract JSON from response (strip markdown fences)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        mapping = json.loads(text)
        # Validate: only keep mappings to known fields
        return {k: v for k, v in mapping.items() if v in FIELD_DESCRIPTIONS and k in headers}
    except Exception as exc:
        logger.error("Gemini column mapping failed: %s", exc)
        return _heuristic_map(headers)


def _heuristic_map(headers: list) -> dict:
    """Fallback heuristic: try to match common column names without AI."""
    mapping = {}
    for h in headers:
        h_lower = h.lower().strip()
        if "כתובת" in h_lower:
            mapping[h] = "address"
        elif "עיר" in h_lower or "ישוב" in h_lower:
            mapping[h] = "city"
        elif "מס\"ד" in h_lower or "מסד" in h_lower or "פנימי" in h_lower:
            mapping[h] = "internal_number"
        elif "תיק" in h_lower and ("עבודה" in h_lower or "מע" in h_lower):
            mapping[h] = "labor_file_number"
        elif "יצרן" in h_lower:
            mapping[h] = "manufacturer"
        elif "דגם" in h_lower:
            mapping[h] = "model"
        elif "קומות" in h_lower:
            mapping[h] = "floor_count"
        elif "שירות" in h_lower and "סוג" in h_lower:
            mapping[h] = "service_type"
        elif "תחזוקה" in h_lower and "אחרון" in h_lower:
            mapping[h] = "last_service_date"
        elif "תחזוקה" in h_lower and "הבא" in h_lower:
            mapping[h] = "next_service_date"
        elif "בדיקה" in h_lower and "אחרון" in h_lower:
            mapping[h] = "last_inspection_date"
        elif "בדיקה" in h_lower and "הבא" in h_lower:
            mapping[h] = "next_inspection_date"
        elif "התקנה" in h_lower:
            mapping[h] = "installation_date"
        elif "אחריות" in h_lower:
            mapping[h] = "warranty_end"
        elif "חיוב" in h_lower or ("חוזה" in h_lower and "תחילת" in h_lower):
            mapping[h] = "contract_start"
        elif "הערות" in h_lower:
            mapping[h] = "notes"
        elif "טלפון" in h_lower and "חייגן" in h_lower:
            mapping[h] = "intercom_phone"
        elif "טלפון" in h_lower:
            mapping[h] = "contact_phone"
        elif "נוסעים" in h_lower:
            mapping[h] = "max_persons"
        elif "משקל" in h_lower or "נשיאה" in h_lower:
            mapping[h] = "load_capacity_kg"
        elif "מהירות" in h_lower:
            mapping[h] = "speed_m_s"
        elif "תחנות" in h_lower:
            mapping[h] = "stops_count"
        elif "דלתות" in h_lower and "מספר" in h_lower:
            mapping[h] = "doors_count"
        elif "דלת" in h_lower and "רוחב" in h_lower:
            mapping[h] = "door_width_cm"
        elif "דלת" in h_lower and "סוג" in h_lower:
            mapping[h] = "door_type"
        elif "גימור" in h_lower:
            mapping[h] = "cabin_finish"
        elif "רצפה" in h_lower:
            mapping[h] = "floor_type"
        elif "בור" in h_lower:
            mapping[h] = "pit_depth_cm"
        elif "מנוע" in h_lower and "סוג" in h_lower:
            mapping[h] = "motor_type"
        elif "מנוע" in h_lower and "סריאלי" in h_lower:
            mapping[h] = "engine_serial"
        elif ("בקר" in h_lower or "פיקוד" in h_lower) and "דגם" in h_lower:
            mapping[h] = "controller_model"
        elif ("בקר" in h_lower or "פיקוד" in h_lower) and "סריאלי" in h_lower:
            mapping[h] = "controller_serial"
        elif "נגישות" in h_lower:
            mapping[h] = "accessibility_compliant"
        elif "אש" in h_lower:
            mapping[h] = "fire_system_connected"
        elif "גנרטור" in h_lower:
            mapping[h] = "generator_connected"
        elif "ip" in h_lower or "iot" in h_lower:
            mapping[h] = "iot_gateway_ip"
        elif "מסירה" in h_lower:
            mapping[h] = "handover_date"
        elif "פירוק" in h_lower:
            mapping[h] = "dismantle_date"
        elif "קוד" in h_lower and "כניסה" in h_lower:
            mapping[h] = "entry_code"
    return mapping


DATE_FIELDS = {"installation_date", "warranty_end", "contract_start", "contract_renewal",
               "contract_end", "last_service_date", "next_service_date", "last_inspection_date",
               "next_inspection_date", "safety_certificate_expiry", "handover_date", "dismantle_date",
               "debt_freeze_date"}
BOOL_FIELDS = {"is_coded", "has_debt", "accessibility_compliant", "fire_system_connected", "generator_connected"}
INT_FIELDS = {"floor_count", "pit_depth_cm", "headroom_cm", "maintenance_times_per_year",
              "load_capacity_kg", "max_persons", "stops_count", "doors_count", "door_width_cm"}
FLOAT_FIELDS = {"speed_m_s", "risk_score"}


def _parse_row(row_dict: dict, col_map: dict) -> dict:
    """Convert a raw Excel row dict using the column mapping."""
    result = {}
    for col_name, field_name in col_map.items():
        raw = row_dict.get(col_name)
        if raw is None or str(raw).strip() == "":
            continue
        if field_name == "service_type":
            v = _fix_service_type(raw)
        elif field_name in DATE_FIELDS:
            v = _fix_date(raw)
        elif field_name in BOOL_FIELDS:
            v = _fix_bool(raw)
        elif field_name in INT_FIELDS:
            v = _fix_int(raw)
        elif field_name in FLOAT_FIELDS:
            v = _fix_float(raw)
        else:
            v = _fix_str(raw)
        if v is not None:
            result[field_name] = v
    return result


def import_elevators_from_excel(db, excel_bytes: bytes) -> dict:
    """Import elevators from Excel. Uses Gemini to map column names."""
    import openpyxl
    from app.models.elevator import Elevator

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb.active

    # Find the header row: first row where most cells are non-empty strings
    header_row_idx = None
    headers = []
    rows_data = list(ws.iter_rows(values_only=True))
    for i, row in enumerate(rows_data):
        non_empty = [str(c).strip() for c in row if c is not None and str(c).strip()]
        if len(non_empty) >= 3 and any(any(ch.isalpha() for ch in c) for c in non_empty):
            header_row_idx = i
            headers = [str(c).strip() if c is not None else "" for c in row]
            break

    if header_row_idx is None:
        return {"total_parsed": 0, "created": 0, "updated": 0, "skipped": 0, "errors": ["לא נמצאה שורת כותרת"]}

    # Use AI to map columns
    meaningful_headers = [h for h in headers if h]
    col_map = _map_columns_with_ai(meaningful_headers)
    logger.info("Column mapping: %s", col_map)

    if not col_map:
        return {"total_parsed": 0, "created": 0, "updated": 0, "skipped": 0,
                "errors": ["לא ניתן היה למפות עמודות. וודא שיש GEMINI_API_KEY."]}

    created = updated = skipped = 0
    errors = []

    for row in rows_data[header_row_idx + 1:]:
        if not row or all(c is None for c in row):
            continue
        row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
        parsed = _parse_row(row_dict, col_map)
        if not parsed:
            continue

        # Find identifier: prefer labor_file_number, then internal_number, then address+city
        existing = None
        if "labor_file_number" in parsed and parsed["labor_file_number"]:
            existing = db.query(Elevator).filter(
                Elevator.labor_file_number == str(parsed["labor_file_number"])
            ).first()
        if not existing and "internal_number" in parsed and parsed["internal_number"]:
            existing = db.query(Elevator).filter(
                Elevator.internal_number == str(parsed["internal_number"])
            ).first()
        if not existing and "address" in parsed and "city" in parsed:
            existing = db.query(Elevator).filter(
                Elevator.address.ilike(str(parsed["address"])),
                Elevator.city.ilike(str(parsed["city"])),
            ).first()

        if existing:
            # Update: fill in missing fields (never overwrite existing data with import data)
            changed = False
            for field, value in parsed.items():
                current = getattr(existing, field, None)
                bool_fields = ("is_coded", "has_debt", "accessibility_compliant",
                               "fire_system_connected", "generator_connected")
                if current is None or current == "" or (current is False and field not in bool_fields):
                    setattr(existing, field, value)
                    changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
        else:
            if "address" not in parsed or "city" not in parsed:
                skipped += 1
                continue
            elev = Elevator(
                floor_count=parsed.pop("floor_count", 1),
                status=parsed.pop("status", "ACTIVE"),
            )
            for field, value in parsed.items():
                if hasattr(Elevator, field):
                    setattr(elev, field, value)
            db.add(elev)
            created += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append(str(exc))

    return {
        "total_parsed": created + updated + skipped,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "column_mapping": col_map,
        "errors": errors,
    }
