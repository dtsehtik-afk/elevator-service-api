"""Working hours helper for Accord Elevators (Israel timezone)."""
from datetime import datetime
from zoneinfo import ZoneInfo

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

_DAY_NAMES = {6: "ראשון", 0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי"}


def is_working_hours(now: datetime | None = None) -> bool:
    """Return True if current Israel time is within working hours."""
    now = (now or datetime.now(_IL_TZ)).astimezone(_IL_TZ)
    slot = _SCHEDULE.get(now.weekday())
    if not slot:
        return False
    sh, sm, eh, em = slot
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end   = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start <= now < end


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
