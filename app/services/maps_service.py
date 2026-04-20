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
_last_nominatim_call = 0.0   # rate-limit: 1 req/sec


def geocode_address(address: str, city: str) -> Optional[tuple[float, float]]:
    """
    Convert a street address to (lat, lng) using OpenStreetMap Nominatim.
    Free, no API key required. Rate-limited to 1 req/sec per Nominatim policy.
    Returns None on failure.
    """
    global _last_nominatim_call
    query = f"{address}, {city}, ישראל"
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
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
        logger.warning("Nominatim: no result for '%s'", query)
    except Exception as exc:
        logger.error("Nominatim geocoding error: %s", exc)
    return None


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
