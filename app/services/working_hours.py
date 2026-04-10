"""Working hours helper for Accord Elevators (Israel timezone)."""
from datetime import datetime
from zoneinfo import ZoneInfo

_IL_TZ = ZoneInfo("Asia/Jerusalem")

# Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
_SCHEDULE = {
    6: (8, 30, 16, 30),  # Sun
    0: (8, 30, 16, 30),  # Mon
    1: (8, 30, 16, 30),  # Tue
    2: (8, 30, 16, 30),  # Wed
    3: (8, 30, 16, 30),  # Thu
    4: (8, 30, 13,  0),  # Fri
    # 5 = Sat: not present → closed
}

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
