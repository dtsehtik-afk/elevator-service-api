"""Google Maps integration — geocoding and travel-time calculations."""

import logging
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Base coordinates for known technician home cities (fallback when GPS unavailable)
CITY_COORDS: dict[str, tuple[float, float]] = {
    "עפולה":   (32.6080, 35.2896),
    "שפרעם":   (32.8040, 35.1700),
    "נצרת":    (32.6996, 35.3035),
    "חיפה":    (32.7940, 34.9896),
    "תל אביב": (32.0853, 34.7818),
    "ירושלים": (31.7683, 35.2137),
}

_GEOCODE_URL      = "https://maps.googleapis.com/maps/api/geocode/json"
_DISTANCE_URL     = "https://maps.googleapis.com/maps/api/distancematrix/json"


# ── Geocoding ────────────────────────────────────────────────────────────────

def geocode_address(address: str, city: str) -> Optional[tuple[float, float]]:
    """
    Convert a street address to (latitude, longitude) via the Google Geocoding API.
    Returns None if the API key is not configured or the address is not found.
    """
    api_key = settings.google_maps_api_key
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY not set — geocoding skipped")
        return None

    query = f"{address}, {city}, ישראל"
    try:
        resp = httpx.get(
            _GEOCODE_URL,
            params={"address": query, "key": api_key, "language": "he"},
            timeout=5,
        )
        data = resp.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
        logger.warning("Geocode failed for '%s': %s", query, data.get("status"))
    except Exception as exc:
        logger.error("Geocode error: %s", exc)
    return None


def ensure_elevator_coords(db: Session, elevator) -> tuple[float, float]:
    """
    Return (lat, lng) for an elevator.
    If not yet geocoded, calls the API and persists the result.
    Falls back to the city's known coordinate if geocoding fails.
    """
    if elevator.latitude and elevator.longitude:
        return elevator.latitude, elevator.longitude

    coords = geocode_address(elevator.address, elevator.city)

    if coords:
        elevator.latitude, elevator.longitude = coords
        db.commit()
        return coords

    # Fallback: use city center
    fallback = CITY_COORDS.get(elevator.city)
    if fallback:
        logger.info("Using city-center fallback coords for %s", elevator.city)
        return fallback

    logger.warning("No coords for elevator %s — using Tel Aviv default", elevator.id)
    return (32.0853, 34.7818)


# ── Distance Matrix ───────────────────────────────────────────────────────────

def get_travel_minutes(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> Optional[int]:
    """
    Return estimated driving time in minutes via Google Distance Matrix API.
    Returns None if the API key is missing or the call fails.
    """
    api_key = settings.google_maps_api_key
    if not api_key:
        return None

    origin = f"{origin_lat},{origin_lng}"
    dest   = f"{dest_lat},{dest_lng}"
    try:
        resp = httpx.get(
            _DISTANCE_URL,
            params={
                "origins":      origin,
                "destinations": dest,
                "mode":         "driving",
                "key":          api_key,
                "language":     "he",
            },
            timeout=5,
        )
        data = resp.json()
        if data.get("status") == "OK":
            element = data["rows"][0]["elements"][0]
            if element.get("status") == "OK":
                return element["duration"]["value"] // 60   # seconds → minutes
        logger.warning("Distance Matrix failed: %s", data.get("status"))
    except Exception as exc:
        logger.error("Distance Matrix error: %s", exc)
    return None


def haversine_minutes(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """
    Rough driving-time estimate using straight-line distance × 1.3 factor
    at an average speed of 60 km/h. Used as fallback when Google Maps is unavailable.
    """
    import math
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi   = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    dist_km = 2 * R * math.asin(math.sqrt(a)) * 1.3   # road factor
    return max(1, int(dist_km / 60 * 60))              # minutes at 60 km/h


def travel_time_minutes(
    origin_lat: float, origin_lng: float,
    dest_lat: float,   dest_lng: float,
) -> int:
    """
    Travel time estimate in minutes using Haversine (straight-line × 1.3 road factor).
    Avoids the costly Google Distance Matrix API — accurate enough for technician ranking.
    """
    return haversine_minutes(origin_lat, origin_lng, dest_lat, dest_lng)
