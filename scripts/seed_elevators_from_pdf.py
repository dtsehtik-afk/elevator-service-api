"""
Seed script — imports elevators from PDF report into the database.

Usage:
    python -m scripts.seed_elevators_from_pdf

Requires the database to be running (docker-compose up -d db).
"""

import re
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import pdfplumber
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings

PDF_PATH = Path(__file__).parent.parent / "data" / "elevators_report.pdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_date(s: str) -> bool:
    return bool(re.match(r"^\d{2}/\d{2}/\d{2}$", s))


def _is_numeric(s: str) -> bool:
    return bool(re.match(r"^\d+$", s))


def _is_hebrew(s: str) -> bool:
    return any("\u0590" <= c <= "\u05FF" for c in s)


def _fix_rtl_word(word: str) -> str:
    """Reverse characters within a Hebrew word extracted from a visual-order PDF."""
    if _is_hebrew(word):
        return word[::-1]
    return word


def _parse_date(date_str: str) -> date | None:
    """Convert DD/MM/YY → Python date. Returns None for placeholder dates (≥ 2050)."""
    if not date_str:
        return None
    try:
        day, month, year = date_str.split("/")
        full_year = 2000 + int(year) if int(year) < 100 else int(year)
        if full_year >= 2050:
            return None
        return date(full_year, int(month), int(day))
    except (ValueError, AttributeError):
        return None


def _fix_address(raw_tokens: list[str]) -> str:
    """
    PDF extracts RTL Hebrew in visual (LTR) order.
    Fix by reversing the token list and reversing characters within each Hebrew token.
    """
    fixed = [_fix_rtl_word(t) for t in reversed(raw_tokens)]
    return " ".join(fixed)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_elevators(pdf_path: Path) -> list[dict]:
    elevators = []
    seen_numbers: set[int] = set()

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                tokens = line.split()

                # Skip headers / empty / too short
                if not tokens or len(tokens) < 4:
                    continue
                if any(kw in line for kw in ("יאנכט", "דוקימ", "תילעמ")):
                    continue

                # First token: technician flag (1 or 2)
                if tokens[0] not in ("1", "2"):
                    continue

                # Last token: elevator number (3–4 digits)
                if not _is_numeric(tokens[-1]):
                    continue
                elevator_num = int(tokens[-1])
                if not (100 <= elevator_num <= 9999):
                    continue
                if elevator_num in seen_numbers:
                    continue  # skip duplicates (same elevator on multiple pages)
                seen_numbers.add(elevator_num)

                # Locate all dates
                date_pos = [(i, t) for i, t in enumerate(tokens) if _is_date(t)]
                if not date_pos:
                    continue

                first_date_idx = date_pos[0][0]

                # Address tokens: between last date and elevator number, in visual order
                name_tokens = tokens[first_date_idx + len(date_pos):-1]
                address = _fix_address(name_tokens)

                # Dates (LTR extracted order: inspector?, warranty, tm, billing, production)
                dates = [d[1] for d in date_pos]
                production = inspector = tm = billing = warranty = None
                if len(dates) == 5:
                    inspector, warranty, tm, billing, production = dates
                elif len(dates) == 4:
                    warranty, tm, billing, production = dates
                elif len(dates) == 3:
                    tm, billing, production = dates
                elif len(dates) == 2:
                    billing, production = dates
                elif len(dates) == 1:
                    production = dates[0]

                # Prefix tokens (between technician and first date): [vat?] [postal?] service_type
                prefix = tokens[1:first_date_idx]
                service_type = prefix[-1] if prefix else None
                postal_code  = prefix[-2] if len(prefix) >= 2 else None
                vat_number   = prefix[-3] if len(prefix) >= 3 else None

                # Extract city from address.
                # The last token is sometimes a single Hebrew letter (e.g. "ה") that is
                # the feminine suffix of a city name split by PDF BiDi rendering.
                # In that case, join it with the preceding token (e.g. "עפול" + "ה" → "עפולה").
                addr_parts = address.split() if address else []
                if len(addr_parts) >= 2 and len(addr_parts[-1]) == 1 and _is_hebrew(addr_parts[-1]):
                    city = addr_parts[-2] + addr_parts[-1]
                    # Also fix the address itself
                    address = " ".join(addr_parts[:-2] + [city])
                elif addr_parts:
                    city = addr_parts[-1]
                else:
                    city = "לא ידוע"

                elevators.append({
                    "elevator_number": elevator_num,
                    "address": address,
                    "city": city,
                    "installation_date": _parse_date(production),
                    "last_service_date": _parse_date(inspector),
                    "next_service_date": _parse_date(tm),
                    "service_type": service_type,
                    "postal_code": postal_code if postal_code and postal_code != "0" else None,
                    "vat_number": vat_number if vat_number and vat_number != "0" else None,
                })

    return elevators


# ---------------------------------------------------------------------------
# DB insertion
# ---------------------------------------------------------------------------

INSERT_SQL = text("""
    INSERT INTO elevators (
        id, address, city, building_name, floor_count,
        serial_number, installation_date, last_service_date, next_service_date,
        status, risk_score, created_at, updated_at
    ) VALUES (
        :id, :address, :city, :building_name, :floor_count,
        :serial_number, :installation_date, :last_service_date, :next_service_date,
        'ACTIVE', 0.0, now(), now()
    )
    ON CONFLICT (serial_number) DO UPDATE SET
        address           = EXCLUDED.address,
        city              = EXCLUDED.city,
        installation_date = EXCLUDED.installation_date,
        last_service_date = EXCLUDED.last_service_date,
        next_service_date = EXCLUDED.next_service_date,
        updated_at        = now()
""")


def seed(pdf_path: Path, database_url: str) -> None:
    print(f"Parsing: {pdf_path}")
    records = parse_elevators(pdf_path)
    print(f"  → {len(records)} elevators found")

    engine = create_engine(database_url)
    inserted = updated = 0

    with Session(engine) as session:
        for r in records:
            result = session.execute(
                INSERT_SQL,
                {
                    "id": uuid.uuid4(),
                    "address": r["address"],
                    "city": r["city"],
                    "building_name": None,
                    "floor_count": 1,
                    "serial_number": str(r["elevator_number"]),
                    "installation_date": r["installation_date"],
                    "last_service_date": r["last_service_date"],
                    "next_service_date": r["next_service_date"],
                },
            )
            if result.rowcount:
                inserted += 1
        session.commit()

    print(f"  → Done: {inserted} rows inserted/updated")


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed elevators from PDF report")
    parser.add_argument(
        "--pdf",
        default=str(PDF_PATH),
        help="Path to the PDF file (default: data/elevators_report.pdf)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Database URL (default: reads from DATABASE_URL env / .env)",
    )
    args = parser.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"ERROR: PDF not found at {pdf}")
        print("Copy the report PDF to data/elevators_report.pdf or pass --pdf <path>")
        sys.exit(1)

    db_url = args.db or get_settings().database_url
    seed(pdf, db_url)
