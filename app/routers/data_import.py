"""
Excel data import router.
Supports two file formats from the legacy system and merges them by internal_number (מס"ד).

File 1 (main): sysnumber, sysname, contactName, mainPhone, lastprev, lastinspect, service type, sherut, Field46/48
File 2 (details): מעלית, שם, ד.בודק, ט.מ, תחילת חיוב, תום אחריות, סוג שרות, מיקוד, מס' מע', טכנאי
"""

import io
import logging
import re
from datetime import date, datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.building import Building
from app.models.contact import Contact
from app.models.elevator import Elevator
from app.models.technician import Technician

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/import", tags=["Data Import"])

# Cities known from the data — used to split "address city" strings
_KNOWN_CITIES = [
    "עפולה", "נצרת", "יוקנעם עלית", "יוקנעם", "טירת כרמל", "קרית שמואל",
    "חיפה", "תל אביב", "ירושלים", "באר שבע", "אשדוד", "אשקלון",
    "יפיע", "שפרעם", "סחנין", "עראבה", "מגדל העמק", "בית שאן",
    "אור עקיבא", "זכרון יעקב", "פרדס חנה", "בנימינה", "קיסריה",
]

_DUMMY_DATES = {"01/01/51", "1/1/51", "01/01/2051", "1/1/2051"}


def _normalize_phone(raw: str) -> Optional[str]:
    """Add leading 0 if missing, strip non-digits."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", str(raw))
    if not digits:
        return None
    if len(digits) == 9 and digits[0] != "0":
        digits = "0" + digits
    return digits


def _parse_date(raw: str) -> Optional[date]:
    """Parse DD/MM/YY or DD/MM/YYYY; return None for dummy/empty dates."""
    if not raw or str(raw).strip() in _DUMMY_DATES or str(raw).strip() == "0":
        return None
    raw = str(raw).strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(raw, fmt).date()
            if d.year > 2040:
                return None
            return d
        except ValueError:
            continue
    return None


def _split_address_city(sysname: str) -> tuple[str, str]:
    """
    Split 'רחוב 7012 נצרת' → ('רחוב 7012', 'נצרת').
    Tries known cities first; falls back to last word.
    """
    sysname = sysname.strip()
    # Remove duplex suffix for address parsing
    clean = re.sub(r"\s*-\s*(מעלית\s+(?:ימנית|שמאלית|.*))$", "", sysname).strip()

    for city in sorted(_KNOWN_CITIES, key=len, reverse=True):
        idx = clean.find(city)
        if idx != -1:
            address = clean[:idx].strip()
            return address, city

    # Fallback: last word = city
    parts = clean.rsplit(" ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return clean, ""


def _geocode_nominatim(address: str, city: str) -> tuple[Optional[float], Optional[float]]:
    """Free geocoding via OpenStreetMap Nominatim. Used for bulk import only."""
    query = f"{address}, {city}, ישראל"
    try:
        with httpx.Client(timeout=10, headers={"User-Agent": "AkordElevators/1.0"}) as client:
            r = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "il"},
            )
            results = r.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as exc:
        logger.warning("Nominatim geocoding failed for %s: %s", query, exc)
    return None, None


def _parse_tsv(content: bytes) -> list[dict]:
    """Parse tab-separated or whitespace-delimited content into list of row dicts."""
    text = content.decode("utf-8-sig", errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []

    # Detect delimiter
    delimiter = "\t" if "\t" in lines[0] else None

    rows = []
    header = None
    for line in lines:
        if delimiter:
            parts = line.split("\t")
        else:
            parts = line.split()

        if header is None:
            header = [p.strip() for p in parts]
            continue
        if len(parts) < 2:
            continue
        row = {}
        for i, h in enumerate(header):
            row[h] = parts[i].strip() if i < len(parts) else ""
        rows.append(row)
    return rows


def _cell_str(c) -> str:
    """Convert a cell value to a clean string, handling dates and floats."""
    if c is None:
        return ""
    from datetime import datetime, date
    if isinstance(c, (datetime, date)):
        return c.strftime("%d/%m/%Y")
    s = str(c).strip()
    # Excel stores integers as floats: "121.0" → "121"
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    return s


def _parse_xlsx(content: bytes) -> list[dict]:
    """Parse .xlsx (openpyxl) or .xls (xlrd) into list of row dicts."""
    import io
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
        rows_iter = list(ws.iter_rows(values_only=True))
    except Exception:
        # Fallback for legacy .xls
        import xlrd
        wb = xlrd.open_workbook(file_contents=content)
        ws = wb.sheet_by_index(0)
        rows_iter = [ws.row_values(i) for i in range(ws.nrows)]

    header = None
    rows = []
    for row in rows_iter:
        values = [_cell_str(c) for c in row]
        if not any(values):
            continue
        if header is None:
            header = values
            continue
        rows.append(dict(zip(header, values)))
    return rows


def _parse_file(content: bytes, filename: str) -> list[dict]:
    """Dispatch to xlsx or tsv parser based on file extension."""
    if filename.lower().endswith((".xlsx", ".xls")):
        return _parse_xlsx(content)
    return _parse_tsv(content)



def _process_file1(rows: list[dict]) -> dict[str, dict]:
    """Parse main file rows into dict keyed by internal_number."""
    result = {}
    for row in rows:
        num = str(row.get("sysnumber", row.get("מעלית", ""))).strip()
        if not num or not num.isdigit():
            continue

        sysname = row.get("sysname", row.get("שם", "")).strip()
        address, city = _split_address_city(sysname)

        # Duplex description (e.g. "מעלית ימנית")
        duplex_match = re.search(r"(מעלית\s+(?:ימנית|שמאלית|\w+))\s*$", sysname)
        building_name = duplex_match.group(1) if duplex_match else ""

        # field46/48 as additional description
        f46 = row.get("Field46", "").strip()
        f48 = row.get("Field48", "").strip()
        extra = f46 or f48
        if extra and not building_name:
            building_name = extra

        service_raw = str(row.get("sherut", row.get("service type", "1"))).strip()
        try:
            service_num = int(service_raw)
        except ValueError:
            service_num = 1
        service_type = "COMPREHENSIVE" if service_num == 2 else "REGULAR"

        # shcut3 = labor file number (מ.ע)
        labor_raw = str(row.get("shcut3", "")).strip()
        labor = labor_raw if labor_raw and labor_raw != "0" and labor_raw.isdigit() else None

        result[num] = {
            "internal_number": num,
            "address": address,
            "city": city,
            "building_name": building_name or None,
            "contact_name": row.get("contactName", "").strip() or None,
            "main_phone": _normalize_phone(row.get("mainPhone", "")),
            "labor_file_number": labor,
            "last_service_date": _parse_date(row.get("lastprev", "")),
            "last_inspection_date": _parse_date(row.get("lastinspect", "")),
            "contract_start": _parse_date(row.get("begineservice", "")),
            "installation_date": _parse_date(row.get("installdate", "")),
            "service_type": service_type,
            "service_contract": "ANNUAL_12" if service_type == "COMPREHENSIVE" else "ANNUAL_6",
            "maintenance_interval_days": 30 if service_type == "COMPREHENSIVE" else 60,
        }
    return result


def _process_file2(rows: list[dict]) -> dict[str, dict]:
    """Parse details file rows into dict keyed by internal_number."""
    result = {}
    for row in rows:
        # Column names vary — try multiple
        num = str(row.get("מעלית", row.get("sysnumber", ""))).strip()
        if not num or not num.isdigit():
            continue

        labor = str(row.get("מס' מע'", row.get("מס מע", ""))).strip()
        if labor == "0" or not labor.isdigit():
            labor = None

        service_raw = str(row.get("סוג שרות", row.get("סוג שירות", "1"))).strip()
        try:
            service_num = int(service_raw)
        except ValueError:
            service_num = 1
        service_type = "COMPREHENSIVE" if service_num == 2 else "REGULAR"

        result[num] = {
            "labor_file_number": labor,
            "last_inspection_date": _parse_date(row.get("ד. בודק", row.get("ד.בודק", ""))),
            "next_service_date": _parse_date(row.get("ט.מ", "")),
            "contract_start": _parse_date(row.get("תחילת חיוב", "")),
            "warranty_end": _parse_date(row.get("תום אחריות", "")),
            "service_type": service_type,
            "service_contract": "ANNUAL_12" if service_type == "COMPREHENSIVE" else "ANNUAL_6",
            "maintenance_interval_days": 30 if service_type == "COMPREHENSIVE" else 60,
        }
    return result


@router.post("/elevators/preview")
def preview_import(
    file1: UploadFile = File(..., description="Main Excel/CSV file (sysnumber, sysname, contactName...)"),
    file2: Optional[UploadFile] = File(None, description="Details file (מעלית, מס' מע', ד.בודק...)"),
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    """
    Dry-run: parse both files and return what would be imported.
    Does NOT write to DB.
    """
    rows1 = _parse_file(file1.file.read(), file1.filename or "")
    print(f"[IMPORT DEBUG] rows={len(rows1)} cols={list(rows1[0].keys()) if rows1 else []}", flush=True)
    if rows1:
        print(f"[IMPORT DEBUG] row0={dict(list(rows1[0].items())[:6])}", flush=True)
    data1 = _process_file1(rows1)
    print(f"[IMPORT DEBUG] data1 entries={len(data1)}", flush=True)

    data2 = {}
    if file2:
        rows2 = _parse_file(file2.file.read(), file2.filename or "")
        data2 = _process_file2(rows2)

    # Merge
    merged = {}
    for num, d in data1.items():
        merged[num] = {**d, **(data2.get(num, {}))}
    for num, d in data2.items():
        if num not in merged:
            merged[num] = d

    # Check existing
    existing = {
        e.internal_number: e.id
        for e in db.query(Elevator).filter(Elevator.internal_number.in_(merged.keys())).all()
    }

    preview = []
    for num, d in sorted(merged.items(), key=lambda x: int(x[0])):
        preview.append({
            "internal_number": num,
            "action": "UPDATE" if num in existing else "CREATE",
            "address": d.get("address", ""),
            "city": d.get("city", ""),
            "contact_name": d.get("contact_name"),
            "main_phone": d.get("main_phone"),
            "labor_file_number": d.get("labor_file_number"),
            "service_type": d.get("service_type"),
            "last_service_date": str(d.get("last_service_date") or ""),
            "last_inspection_date": str(d.get("last_inspection_date") or ""),
            "next_service_date": str(d.get("next_service_date") or ""),
        })

    return {
        "total": len(preview),
        "create": sum(1 for p in preview if p["action"] == "CREATE"),
        "update": sum(1 for p in preview if p["action"] == "UPDATE"),
        "rows": preview,
    }


@router.post("/elevators/commit")
def commit_import(
    file1: UploadFile = File(..., description="Main file"),
    file2: Optional[UploadFile] = File(None, description="Details file"),
    geocode: bool = False,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    """
    Actually import elevators. Merges both files by internal_number.
    - Creates new elevators
    - Updates existing ones (only fills missing fields, never overwrites existing data)
    - Creates Building records for shared addresses
    - Creates Contact records for ועד contacts
    - Optionally geocodes new elevators via Nominatim (free)
    """
    rows1 = _parse_file(file1.file.read(), file1.filename or "")
    data1 = _process_file1(rows1)

    data2 = {}
    if file2:
        rows2 = _parse_file(file2.file.read(), file2.filename or "")
        data2 = _process_file2(rows2)

    # Merge: file2 wins for fields it provides
    merged = {}
    for num, d in data1.items():
        merged[num] = {**d, **(data2.get(num, {}))}
    for num, d in data2.items():
        if num not in merged:
            merged[num] = d

    created = updated = skipped = 0
    errors = []

    # Cache buildings by (address, city) to avoid duplicates
    building_cache: dict[tuple, Building] = {}

    def _get_or_create_building(address: str, city: str) -> Optional[Building]:
        key = (address.lower().strip(), city.lower().strip())
        if key in building_cache:
            return building_cache[key]
        b = db.query(Building).filter(
            Building.address.ilike(address), Building.city.ilike(city)
        ).first()
        if not b:
            b = Building(address=address, city=city)
            db.add(b)
            db.flush()
        building_cache[key] = b
        return b

    for num, d in sorted(merged.items(), key=lambda x: int(x[0])):
        try:
            address = (d.get("address") or "").strip()
            city = (d.get("city") or "").strip()

            existing = db.query(Elevator).filter(Elevator.internal_number == num).first()

            if existing:
                # UPDATE — only fill missing fields
                for field in ("labor_file_number", "last_service_date", "last_inspection_date",
                              "next_service_date", "contract_start", "warranty_end",
                              "installation_date"):
                    if not getattr(existing, field, None) and d.get(field):
                        setattr(existing, field, d[field])
                if not existing.service_type and d.get("service_type"):
                    existing.service_type = d["service_type"]
                    existing.service_contract = d.get("service_contract")
                    existing.maintenance_interval_days = d.get("maintenance_interval_days")
                updated += 1
            else:
                # CREATE
                building = _get_or_create_building(address, city) if address and city else None

                lat, lon = None, None
                if geocode and address and city:
                    lat, lon = _geocode_nominatim(address, city)

                elev = Elevator(
                    internal_number=num,
                    labor_file_number=d.get("labor_file_number"),
                    building_id=building.id if building else None,
                    address=address,
                    city=city,
                    building_name=d.get("building_name"),
                    latitude=lat,
                    longitude=lon,
                    service_type=d.get("service_type"),
                    service_contract=d.get("service_contract"),
                    maintenance_interval_days=d.get("maintenance_interval_days"),
                    last_service_date=d.get("last_service_date"),
                    last_inspection_date=d.get("last_inspection_date"),
                    next_service_date=d.get("next_service_date"),
                    contract_start=d.get("contract_start"),
                    warranty_end=d.get("warranty_end"),
                    installation_date=d.get("installation_date"),
                    floor_count=1,
                )
                db.add(elev)
                db.flush()

                # Create ועד contact if provided
                contact_name = d.get("contact_name")
                main_phone = d.get("main_phone")
                if contact_name and building:
                    existing_contact = db.query(Contact).filter(
                        Contact.building_id == building.id,
                        Contact.name == contact_name,
                    ).first()
                    if not existing_contact:
                        db.add(Contact(
                            building_id=building.id,
                            name=contact_name,
                            phone=main_phone,
                            role="VAAD",
                        ))

                created += 1

        except Exception as exc:
            logger.error("Import error for elevator %s: %s", num, exc)
            errors.append({"internal_number": num, "error": str(exc)})
            db.rollback()
            continue

    db.commit()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": created + updated + skipped + len(errors),
    }
