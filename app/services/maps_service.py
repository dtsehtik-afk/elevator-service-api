"""Geocoding and travel-time calculations — uses OpenStreetMap Nominatim (free, no API key)."""

import logging
import math
import time
from typing import Optional

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Fallback city-center coordinates for common Israeli cities
CITY_COORDS: dict[str, tuple[float, float]] = {
    "עפולה":        (32.6080, 35.2896),
    "שפרעם":        (32.8040, 35.1700),
    "נצרת":         (32.6996, 35.3035),
    "חיפה":         (32.7940, 34.9896),
    "תל אביב":      (32.0853, 34.7818),
    "ירושלים":      (31.7683, 35.2137),
    "באר שבע":      (31.2530, 34.7915),
    "ראשון לציון":  (31.9730, 34.7895),
    "פתח תקווה":    (32.0870, 34.8870),
    "אשדוד":        (31.8010, 34.6450),
    "נתניה":        (32.3215, 34.8532),
    "חולון":        (32.0115, 34.7740),
    "טירת הכרמל":  (32.7586, 34.9697),
    "קריית אתא":   (32.8050, 35.1090),
    "קריית ביאליק": (32.8350, 35.0850),
    "קריית מוצקין": (32.8367, 35.0778),
    "קריית ים":     (32.8495, 35.0672),
    "עכו":          (32.9235, 35.0727),
    "נהריה":        (33.0036, 35.0952),
    "טבריה":        (32.7948, 35.5310),
    "צפת":          (32.9646, 35.4966),
    "רמת גן":       (32.0824, 34.8137),
    "בני ברק":      (32.0839, 34.8339),
    "גבעתיים":      (32.0704, 34.8126),
    "כפר סבא":      (32.1751, 34.9060),
    "הרצליה":       (32.1622, 34.8438),
    "רעננה":        (32.1849, 34.8706),
    "מודיעין":      (31.8969, 35.0095),
    "לוד":          (31.9516, 34.8950),
    "רמלה":         (31.9296, 34.8681),
    "אשקלון":       (31.6688, 34.5742),
    "רחובות":       (31.8928, 34.8115),
}

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_last_nominatim_call = 0.0   # rate-limit: 1 req/sec
_geocode_cache: dict[str, Optional[tuple[float, float]]] = {}  # avoid repeated calls
_reverse_cache: dict[str, str] = {}  # (lat3, lon3) → place label

# Israel bounding box — same limits used in the GPS ingest endpoint
_IL_LAT_MIN, _IL_LAT_MAX = 29.0, 33.5
_IL_LON_MIN, _IL_LON_MAX = 34.0, 35.95  # 35.95 covers Golan Heights


def is_israel_coords(lat: float, lon: float) -> bool:
    """Return True iff (lat, lon) falls within Israel's bounding box."""
    return (
        lat is not None and lon is not None
        and _IL_LAT_MIN <= lat <= _IL_LAT_MAX
        and _IL_LON_MIN <= lon <= _IL_LON_MAX
    )


def geocode_address(address: str, city: str) -> Optional[tuple[float, float]]:
    """
    Convert a street address to (lat, lng) using OpenStreetMap Nominatim.
    Free, no API key required. Rate-limited to 1 req/sec per Nominatim policy.
    Results are cached in memory to prevent repeated calls for the same address.
    Returns None on failure.
    """
    global _last_nominatim_call
    query = f"{address}, {city}, ישראל"

    # Return cached result immediately (including None = "already tried, no result")
    if query in _geocode_cache:
        return _geocode_cache[query]

    try:
        # Respect Nominatim 1 req/sec rate limit
        elapsed = time.monotonic() - _last_nominatim_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)

        resp = httpx.get(
            _NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "il"},
            headers={"User-Agent": "elevator-service-api/1.0 (contact@akord.co.il)"},
            timeout=8,
        )
        _last_nominatim_call = time.monotonic()
        if not resp.is_success:
            logger.warning("Nominatim HTTP %s for '%s'", resp.status_code, query)
        else:
            results = resp.json()
            if results:
                coords = float(results[0]["lat"]), float(results[0]["lon"])
                _geocode_cache[query] = coords
                return coords
            logger.warning("Nominatim: no result for '%s'", query)
    except Exception as exc:
        logger.warning("Nominatim geocoding error: %s", exc)

    _geocode_cache[query] = None  # cache the failure too
    return None



def reverse_geocode(lat: float, lon: float) -> str:
    """Return a human-readable place name for the given coordinates (Hebrew where possible).
    Uses Nominatim reverse geocoding with in-memory cache (rounded to ~100 m grid).
    Returns 'לא ידוע' on failure.
    """
    global _last_nominatim_call
    # Round to 3 decimal places (~100 m) for cache key
    cache_key = f"{lat:.3f},{lon:.3f}"
    if cache_key in _reverse_cache:
        return _reverse_cache[cache_key]

    try:
        elapsed = time.monotonic() - _last_nominatim_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)

        resp = httpx.get(
            _NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "json", "accept-language": "he"},
            headers={"User-Agent": "elevator-service-api/1.0 (contact@akord.co.il)"},
            timeout=8,
        )
        _last_nominatim_call = time.monotonic()
        if resp.is_success:
            data = resp.json()
            addr = data.get("address", {})
            # Prefer village/suburb/neighbourhood over city for accurate small-settlement names
            place = (
                addr.get("village")
                or addr.get("hamlet")
                or addr.get("suburb")
                or addr.get("neighbourhood")
                or addr.get("town")
                or addr.get("city")
                or addr.get("county")
                or data.get("display_name", "לא ידוע").split(",")[0]
            )
            _reverse_cache[cache_key] = place
            return place
    except Exception as exc:
        logger.warning("Nominatim reverse geocoding error: %s", exc)

    _reverse_cache[cache_key] = "לא ידוע"
    return "לא ידוע"


def ensure_elevator_coords(db: Session, elevator) -> tuple[float, float]:
    """
    Return (lat, lng) for an elevator.
    1. Use cached DB coords if available.
    2. Try Nominatim geocoding and persist.
    3. Fall back to known city-center coordinates.
    4. Default to Tel Aviv if city unknown.
    """
    if elevator.latitude and elevator.longitude:
        return float(elevator.latitude), float(elevator.longitude)

    coords = geocode_address(elevator.address, elevator.city)
    if coords:
        elevator.latitude, elevator.longitude = coords
        db.commit()
        return coords

    fallback = CITY_COORDS.get(elevator.city)
    if fallback:
        logger.info("Using city-center fallback for %s (%s)", elevator.address, elevator.city)
        return fallback

    logger.warning("No coords for elevator %s — using Tel Aviv default", elevator.id)
    return (32.0853, 34.7818)


def haversine_minutes(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Straight-line distance × 1.3 road factor at 60 km/h → driving minutes estimate."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    dist_km = 2 * R * math.asin(math.sqrt(a)) * 1.3
    return max(1, int(dist_km / 60 * 60))


def travel_time_minutes(
    origin_lat: float, origin_lng: float,
    dest_lat: float,   dest_lng: float,
) -> int:
    """Travel time in minutes — Haversine estimate, no external API needed."""
    return haversine_minutes(origin_lat, origin_lng, dest_lat, dest_lng)


# Kept for backwards compatibility — not called internally anymore
def get_travel_minutes(*args, **kwargs) -> Optional[int]:
    return None
