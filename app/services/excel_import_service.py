"""Parse elevator report Excel (.xlsx) and import into database."""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass


@dataclass
class ParsedElevatorXL:
    serial_number: str
    address: str
    city: str
    last_service_date: Optional[str]
    next_service_date: Optional[str]
    billing_start: Optional[str]


# Column indices (0-based) in the Excel sheet
_COL_SERIAL = 19       # מעלית — elevator number
_COL_NAME = 18         # שם — full address + city ("קרן היסוד 26 עפולה")
_COL_LAST_SERVICE = 8  # ד. בודק — last inspection date
_COL_NEXT_SERVICE = 12 # ט.מ — next service date
_COL_BILLING = 14      # תחילת חיוב — billing start date

# Data starts at row index 2 (0-based), i.e. Excel row 3
_DATA_START_ROW = 2

# Sentinel years used in the report to indicate "no date"
_SENTINEL_YEARS = {2050, 2051}


def _fix_date(value) -> Optional[str]:
    """Convert a datetime cell value to YYYY-MM-DD, or None for sentinel/missing dates."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.year in _SENTINEL_YEARS:
            return None
        return value.strftime("%Y-%m-%d")
    # Sometimes openpyxl returns a date string
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
            if dt.year in _SENTINEL_YEARS:
                return None
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _parse_address(name_field: str):
    """
    Split 'קרן היסוד 26 עפולה' into (city='עפולה', address='קרן היסוד 26').
    The last space-separated token is the city; the rest is the street + house number.
    """
    if not name_field or not name_field.strip():
        return "—", "—"
    parts = name_field.strip().split()
    if len(parts) == 1:
        return parts[0], "—"
    city = parts[-1]
    address = " ".join(parts[:-1])
    return city, address


def parse_excel(excel_bytes: bytes) -> list[ParsedElevatorXL]:
    """
    Parse the elevator report Excel file.

    Expected sheet layout:
      Row 1 (index 0): report title
      Row 2 (index 1): column headers
      Row 3+ (index 2+): data rows
    """
    import openpyxl
    import io

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb.active

    elevators: list[ParsedElevatorXL] = []
    seen_serials: set[str] = set()

    rows = list(ws.iter_rows(min_row=_DATA_START_ROW + 1, values_only=True))

    for row in rows:
        # Skip short or empty rows
        if not row or len(row) <= _COL_SERIAL:
            continue

        serial_raw = row[_COL_SERIAL]
        if serial_raw is None:
            continue

        # Serial must be a positive integer
        try:
            serial = str(int(serial_raw))
        except (ValueError, TypeError):
            continue

        if int(serial) < 100:
            continue  # skip page numbers / noise

        if serial in seen_serials:
            continue
        seen_serials.add(serial)

        name_field = row[_COL_NAME]
        if not name_field:
            continue

        city, address = _parse_address(str(name_field))

        last_service = _fix_date(row[_COL_LAST_SERVICE] if len(row) > _COL_LAST_SERVICE else None)
        next_service = _fix_date(row[_COL_NEXT_SERVICE] if len(row) > _COL_NEXT_SERVICE else None)
        billing_start = _fix_date(row[_COL_BILLING] if len(row) > _COL_BILLING else None)

        elevators.append(ParsedElevatorXL(
            serial_number=serial,
            address=address,
            city=city,
            last_service_date=last_service,
            next_service_date=next_service,
            billing_start=billing_start,
        ))

    return elevators


def import_elevators_from_excel(db, excel_bytes: bytes) -> dict:
    """Import elevators from Excel into database. Returns stats."""
    from app.models.elevator import Elevator

    parsed = parse_excel(excel_bytes)
    created = 0
    updated = 0
    skipped = 0

    for e in parsed:
        existing = db.query(Elevator).filter(
            Elevator.serial_number == e.serial_number
        ).first()

        if existing:
            changed = False
            if not existing.last_service_date and e.last_service_date:
                existing.last_service_date = e.last_service_date
                changed = True
            if not existing.next_service_date and e.next_service_date:
                existing.next_service_date = e.next_service_date
                changed = True
            # Always update address/city from Excel (more reliable than PDF)
            if existing.city in ("—", "", None) or len(existing.city) <= 1:
                existing.city = e.city
                existing.address = e.address
                changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
        else:
            elevator = Elevator(
                serial_number=e.serial_number,
                address=e.address,
                city=e.city,
                last_service_date=e.last_service_date,
                next_service_date=e.next_service_date,
                floor_count=1,
                status="ACTIVE",
            )
            db.add(elevator)
            created += 1

    db.commit()
    return {
        "total_parsed": len(parsed),
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }
