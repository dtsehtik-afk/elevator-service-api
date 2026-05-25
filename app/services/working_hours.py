"""Working hours helper for Accord Elevators (Israel timezone)."""
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

_IL_TZ = ZoneInfo("Asia/Jerusalem")

# Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
_SCHEDULE = {
    6: (7, 30, 16, 30),  # Sun
    0: (7, 30, 16, 30),  # Mon
    1: (7, 30, 16, 30),  # Tue
    2: (7, 30, 16, 30),  # Wed
    3: (7, 30, 16, 30),  # Thu
    4: (7, 30, 13,  0),  # Fri
    # 5 = Sat: not present → closed
}

# Set of closed dates in YYYY-MM-DD format (holidays, special closures).
# Loaded from DB on startup; updated via POST /settings/holidays without restart.
_HOLIDAYS: set[str] = set()

_DAY_NAMES = {6: "ראשון", 0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי"}


def is_working_hours(now: datetime | None = None) -> bool:
    """Return True if current Israel time is within working hours."""
    now = (now or datetime.now(_IL_TZ)).astimezone(_IL_TZ)
    if now.strftime("%Y-%m-%d") in _HOLIDAYS:
        return False
    slot = _SCHEDULE.get(now.weekday())
    if not slot:
        return False
    sh, sm, eh, em = slot
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end   = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start <= now < end


def fetch_holidays_from_hebcal(year: int) -> list[dict]:
    """Fetch Israeli public holiday dates from Hebcal API for a given year.

    Uses Israel mode (i=on) so only first-day Yom Tov is returned — no diaspora second days.
    Filters exclusively for statutory public holidays (Yemei Shabaton).
    Returns sorted list of dicts: {"date": "YYYY-MM-DD", "name": "Holiday Name"}.
    """
    import httpx
    url = (
        f"https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&min=off"
        f"&mod=on&nx=off&year={year}&month=x&ss=off&mf=off&c=off"
        f"&geo=none&M=on&s=off&i=on"
    )
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    dates_dict = {}
    
    for item in data.get("items", []):
        title = item.get("title", "")
        # Only keep statutory public holidays
        is_valid = False
        if title.startswith("Rosh Hashana"): is_valid = True
        elif title.startswith("Yom HaAtzma"): is_valid = True
        elif title in ("Yom Kippur", "Sukkot I", "Shmini Atzeret", "Pesach I", "Pesach VII", "Shavuot"): is_valid = True
        
        if is_valid:
            d = item.get("date", "")
            if d and len(d) == 10:
                # Use Hebrew names if we can map them, otherwise English
                hebrew_name = title
                if title.startswith("Rosh Hashana"): hebrew_name = "ראש השנה"
                elif title == "Yom Kippur": hebrew_name = "יום כיפור"
                elif title == "Sukkot I": hebrew_name = "סוכות (ראשון)"
                elif title == "Shmini Atzeret": hebrew_name = "שמחת תורה"
                elif title == "Pesach I": hebrew_name = "פסח (ראשון)"
                elif title == "Pesach VII": hebrew_name = "שביעי של פסח"
                elif title == "Shavuot": hebrew_name = "שבועות"
                elif title.startswith("Yom HaAtzma"): hebrew_name = "יום העצמאות"
                dates_dict[d] = hebrew_name
                
    result = [{"date": d, "name": dates_dict[d]} for d in sorted(dates_dict.keys())]
    logger.info(f"Hebcal: fetched {len(result)} statutory holiday dates for {year}")
    return result


def get_working_hours_str() -> str:
    """Return a formatted Hebrew string of the working schedule."""
    return "יום ראשון-חמישי: 07:30–16:30\nיום שישי: 07:30–13:00"


def get_time_greeting() -> str:
    """Return Hebrew greeting based on current Israel time."""
    h = datetime.now(_IL_TZ).hour
    if 5 <= h < 12:
        return "בוקר טוב"
    if 12 <= h < 17:
        return "צהריים טובים"
    if 17 <= h < 21:
        return "ערב טוב"
    return "לילה טוב"
