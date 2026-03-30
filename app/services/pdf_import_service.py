"""Parse elevator report PDF and import into database."""

import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class ParsedElevator:
    serial_number: str
    address: str
    city: str
    last_service_date: Optional[str]
    next_service_date: Optional[str]
    billing_start: Optional[str]


def _reverse_hebrew(text: str) -> str:
    """Reverse RTL text that was extracted incorrectly from PDF."""
    return text[::-1].strip()


def _fix_date(date_str: str) -> Optional[str]:
    """Convert DD/MM/YY to YYYY-MM-DD."""
    if not date_str or date_str.strip() in ('', '01/01/51', '01/01/50'):
        return None
    try:
        parts = date_str.strip().split('/')
        if len(parts) == 3:
            day, month, year = parts
            year = int(year)
            if year < 100:
                year += 2000
            return f"{year:04d}-{int(month):02d}-{int(day):02d}"
    except Exception:
        pass
    return None


# Known cities (reversed Hebrew as they appear in PDF)
_KNOWN_CITIES = {
    'ה לופע': 'עפולה',
    'לופע': 'עפולה',
    'תרצנ': 'נצרת',
    'הרצנ': 'נצרת',
    'הפיח': 'חיפה',
    'היפיח': 'חיפה',
    'הימרכ': 'כרמיאל',
    'לאימרכ': 'כרמיאל',
    'ותי': 'יתד',
    'הירהנ': 'נהריה',
    'הירהנה': 'נהריה',
    'לאירשא': 'אשראל',
    'הלופע': 'עפולה',
    'תוילע': 'עלית',
    'מרעש': 'שפרעם',
    'הקמע': 'עמקה',
    'הכע': 'עכו',
    'וכע': 'עכו',
    'לאירשא': 'אשראל',
    'ןולקשא': 'אשקלון',
    'הלמר': 'רמלה',
    'הוקת חתפ': 'פתח תקווה',
    'ביבא לת': 'תל אביב',
    'םיסכנ': 'נחף',
    'אבס רפכ': 'כפר סבא',
    'ןיעה שאר': 'ראש העין',
    'הנומיד': 'דימונה',
    'תרצנ תילע': 'נצרת עילית',
    'אנח לא': 'אל חנא',
    'הרצנ תילע': 'נצרת עילית',
    'ס"ריב': 'באר שבע',
    'רמוע': 'עומר',
}


def _detect_city(reversed_city_token: str) -> str:
    """Try to match a reversed city token to a known city."""
    token = reversed_city_token.strip()
    if token in _KNOWN_CITIES:
        return _KNOWN_CITIES[token]
    # Try reversing it
    normal = token[::-1]
    return normal


def parse_pdf(pdf_bytes: bytes) -> list[ParsedElevator]:
    """
    Parse elevator report PDF.

    The PDF has RTL text extracted in reverse order.
    Each data line format (reversed):
    page_num  vat  0  service_type  last_service  warranty  next_service  billing_start  manufacture  city  house_num  street  elevator_num
    """
    import pdfplumber
    import io

    elevators = []
    seen_serials = set()

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # Each data line ends with a number (elevator serial)
                # Pattern: tokens ... city house_num street serial_num
                parts = line.split()
                if len(parts) < 5:
                    continue

                # Serial number is last token — must be numeric
                if not parts[-1].isdigit():
                    continue

                serial = parts[-1]
                if serial in seen_serials:
                    continue
                if int(serial) < 100:  # Skip page numbers etc
                    continue

                seen_serials.add(serial)

                # Find dates (format DD/MM/YY)
                date_pattern = re.compile(r'\d{2}/\d{2}/\d{2}')
                dates = date_pattern.findall(line)

                # Remove serial, dates and numeric tokens to get address parts
                remaining = parts[:-1]  # Remove serial
                address_parts = []
                for p in remaining:
                    if not date_pattern.match(p) and not p.isdigit() and p not in ('0', '1', '2', '3'):
                        address_parts.append(p)

                if not address_parts:
                    continue

                # The address in reversed PDF: [city_reversed] [house_num] [street_reversed]
                # Try to parse: last meaningful tokens are street + house + city
                street_reversed = ''
                house_num = ''
                city_reversed = ''

                # Find house number (numeric token in address)
                house_idx = None
                for i, p in enumerate(address_parts):
                    if p.isdigit() or (len(p) <= 4 and p.rstrip('א-ת').isdigit()):
                        house_idx = i
                        break

                if house_idx is not None:
                    city_part = ' '.join(address_parts[:house_idx]) if house_idx > 0 else ''
                    house_num = address_parts[house_idx]
                    street_part = ' '.join(address_parts[house_idx + 1:]) if house_idx + 1 < len(address_parts) else ''
                else:
                    city_part = address_parts[0] if address_parts else ''
                    street_part = ' '.join(address_parts[1:]) if len(address_parts) > 1 else ''

                city = _detect_city(city_part)
                street_fixed = street_part[::-1].strip() if street_part else ''
                address = f"{street_fixed} {house_num}".strip()

                # Dates: [last_service, warranty, next_service, billing_start, ...]
                last_service = _fix_date(dates[0]) if len(dates) > 0 else None
                next_service = _fix_date(dates[2]) if len(dates) > 2 else None
                billing_start = _fix_date(dates[3]) if len(dates) > 3 else None

                elevators.append(ParsedElevator(
                    serial_number=serial,
                    address=address if address else '—',
                    city=city if city else '—',
                    last_service_date=last_service,
                    next_service_date=next_service,
                    billing_start=billing_start,
                ))

    return elevators


def import_elevators_from_pdf(db, pdf_bytes: bytes) -> dict:
    """Import elevators from PDF into database. Returns stats."""
    from app.models.elevator import Elevator

    parsed = parse_pdf(pdf_bytes)
    created = 0
    updated = 0
    skipped = 0

    for e in parsed:
        existing = db.query(Elevator).filter(
            Elevator.serial_number == e.serial_number
        ).first()

        if existing:
            # Update dates if missing
            changed = False
            if not existing.last_service_date and e.last_service_date:
                existing.last_service_date = e.last_service_date
                changed = True
            if not existing.next_service_date and e.next_service_date:
                existing.next_service_date = e.next_service_date
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
                status='ACTIVE',
            )
            db.add(elevator)
            created += 1

    db.commit()
    return {
        'total_parsed': len(parsed),
        'created': created,
        'updated': updated,
        'skipped': skipped,
    }
