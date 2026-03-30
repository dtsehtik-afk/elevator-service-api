"""Parse incoming telephony emails and match elevators from the database."""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy.orm import Session

from app.models.elevator import Elevator


# ── Fault-type keyword mapping ──────────────────────────────────────────────

_FAULT_KEYWORDS: list[tuple[list[str], str]] = [
    (["תקוע", "תקועה", "ללא אנשים", "עם אנשים"], "STUCK"),
    (["דלת"], "DOOR"),
    (["חשמל", "חשמלי", "חשמלית"], "ELECTRICAL"),
    (["מכני", "מכאני", "מכנית", "מכאנית"], "MECHANICAL"),
    (["תוכנה", "בקר", "שגיאה"], "SOFTWARE"),
]

_PRIORITY_MAP: list[tuple[list[str], str]] = [
    (["עם אנשים", "אנשים כלואים", "כלוא"], "CRITICAL"),
    (["תקוע", "תקועה", "ללא אנשים"], "HIGH"),
    (["חירום", "דחוף"], "HIGH"),
]


def _detect_fault_type(text: str) -> str:
    for keywords, fault in _FAULT_KEYWORDS:
        if any(kw in text for kw in keywords):
            return fault
    return "OTHER"


def _detect_priority(text: str) -> str:
    for keywords, priority in _PRIORITY_MAP:
        if any(kw in text for kw in keywords):
            return priority
    return "MEDIUM"


# ── Email field extractor ────────────────────────────────────────────────────

_FIELD_PATTERNS: dict[str, str] = {
    "call_time":    r"מועד התקשרות\s*[:\-]\s*(.+)",
    "call_type":    r"סוג פניה\s*[:\-]\s*(.+)",
    "name":         r"שם\s*[:\-]\s*(.+)",
    "city":         r"עיר\s*[:\-]\s*(.+)",
    "street":       r"רחוב\s*[:\-]\s*(.+)",
    "house_number": r"מס[\'׳]?\s*בית\s*[:\-]\s*(.*)",
    "floor":        r"קומה\s*[:\-]\s*(.+)",
    "phone":        r"טלפון\s*[:\-]\s*(.+)",
    "context":      r"הקשר פניה\s*[:\-]\s*(.+)",
}

_EMPTY_VALUES = {"", "לא נמסר", "לא ידוע", "-", "—", "אין", "none"}


@dataclass
class ParsedCall:
    name: str
    phone: str
    city: str
    street: str
    house_number: str
    floor: str
    call_type: str
    context: str
    call_time: str
    fault_type: str
    priority: str
    description: str


def parse_email(email_body: str) -> ParsedCall:
    """Extract structured fields from a telephony provider email."""
    fields: dict[str, str] = {}

    for key, pattern in _FIELD_PATTERNS.items():
        match = re.search(pattern, email_body, re.MULTILINE)
        raw = match.group(1).strip() if match else ""
        fields[key] = "" if raw.lower() in _EMPTY_VALUES else raw

    call_type = fields.get("call_type", "")
    context   = fields.get("context", "")
    combined  = f"{call_type} {context}"

    fault_type = _detect_fault_type(combined)
    priority   = _detect_priority(combined)

    # Build human-readable description
    parts = []
    if call_type:
        parts.append(call_type)
    caller = fields.get("name", "")
    phone  = fields.get("phone", "")
    if caller:
        parts.append(f"דיווח מ: {caller}")
    if phone:
        parts.append(f"טל׳: {phone}")
    description = " | ".join(parts) if parts else (context or "קריאת שירות")

    return ParsedCall(
        name=fields.get("name", ""),
        phone=fields.get("phone", ""),
        city=fields.get("city", ""),
        street=fields.get("street", ""),
        house_number=fields.get("house_number", ""),
        floor=fields.get("floor", ""),
        call_type=call_type,
        context=context,
        call_time=fields.get("call_time", ""),
        fault_type=fault_type,
        priority=priority,
        description=description,
    )


# ── Fuzzy elevator matcher ───────────────────────────────────────────────────

@dataclass
class MatchResult:
    elevator: Optional[Elevator]
    score: float          # 0.0 – 1.0
    match_status: str     # MATCHED | PARTIAL | UNMATCHED
    match_notes: str = ""


def _similarity(a: str, b: str) -> float:
    """Normalized similarity ratio between two strings."""
    a, b = a.strip().lower(), b.strip().lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _score_elevator(elevator: Elevator, parsed: ParsedCall) -> float:
    """
    Compute a combined match score (0–1) for a single elevator.

    Weights:
      street similarity  — 60 %
      city similarity    — 30 %
      house-number bonus — 10 %
    """
    street_score = _similarity(parsed.street, elevator.address or "")

    city_score = 0.0
    if parsed.city:
        city_score = _similarity(parsed.city, elevator.city or "")
    else:
        city_score = 0.5  # neutral if caller didn't provide a city

    house_bonus = 0.0
    if parsed.house_number and parsed.house_number in (elevator.address or ""):
        house_bonus = 0.1

    return street_score * 0.6 + city_score * 0.3 + house_bonus


_MATCH_THRESHOLD   = 0.55   # above this → MATCHED
_PARTIAL_THRESHOLD = 0.30   # above this → PARTIAL (manual review needed)


def find_elevator(db: Session, parsed: ParsedCall) -> MatchResult:
    """
    Fuzzy-match an elevator using city + street from the parsed call.

    Returns a MatchResult with the best candidate and a confidence score.
    Score thresholds:
      ≥ 0.55 → MATCHED   (auto-create service call)
      ≥ 0.30 → PARTIAL   (suggest to secretary for review)
       < 0.30 → UNMATCHED (logged only)
    """
    if not parsed.street:
        return MatchResult(elevator=None, score=0.0, match_status="UNMATCHED",
                           match_notes="לא סופקה כתובת בקריאה")

    # Pre-filter by city to keep the candidate set small
    query = db.query(Elevator)
    if parsed.city:
        query = query.filter(Elevator.city.ilike(f"%{parsed.city}%"))
    candidates = query.all()

    # Fall back to all elevators if city filter yielded nothing
    if not candidates:
        candidates = db.query(Elevator).all()

    if not candidates:
        return MatchResult(elevator=None, score=0.0, match_status="UNMATCHED",
                           match_notes="אין מעליות במסד הנתונים")

    scored = [(e, _score_elevator(e, parsed)) for e in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    best_elevator, best_score = scored[0]

    if best_score >= _MATCH_THRESHOLD:
        return MatchResult(
            elevator=best_elevator,
            score=round(best_score, 3),
            match_status="MATCHED",
            match_notes=f"התאמה אוטומטית ({best_score:.0%})",
        )
    elif best_score >= _PARTIAL_THRESHOLD:
        return MatchResult(
            elevator=best_elevator,
            score=round(best_score, 3),
            match_status="PARTIAL",
            match_notes=f"התאמה חלקית ({best_score:.0%}) — דורש אישור",
        )
    else:
        return MatchResult(
            elevator=None,
            score=round(best_score, 3),
            match_status="UNMATCHED",
            match_notes=f"לא נמצאה התאמה (ציון מרבי: {best_score:.0%})",
        )


def enrich_elevator(db: Session, elevator: Elevator, parsed: ParsedCall) -> bool:
    """
    Fill in missing fields on the matched elevator using data from the call.
    Only updates fields that are currently empty/None.
    Returns True if any field was updated.
    """
    changed = False

    # Update building name if caller provided a company/contact name and elevator has none
    if parsed.name and not elevator.building_name:
        elevator.building_name = parsed.name
        changed = True

    if changed:
        db.commit()
        db.refresh(elevator)

    return changed
