"""Israeli geo data: cities and streets from the government open-data API.

Cities are fetched once at startup from data.gov.il and cached in memory.
Streets are queried on demand (proxied to gov API) with a 100-item cache.
A hardcoded fallback list of ~300 major localities is used if the API is unreachable.
"""

import logging
import threading
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

_GOV_API = "https://data.gov.il/api/3/action/datastore_search"
_LOCALITIES_RESOURCE = "5c78e9fa-c2e2-4771-93ff-7f400a12f7ba"
_STREETS_RESOURCE = "9ad3862c-8391-4b2f-84a4-2d4c68625f4b"

# ── Fallback cities list (major Israeli localities) ───────────────────────────
_FALLBACK_CITIES: List[str] = sorted([
    "אבו גוש", "אבו סנאן", "אום אל-פחם", "אופקים", "אור יהודה", "אור עקיבא",
    "אורנית", "אחיהוד", "איילת השחר", "אילת", "אכסאל", "אלעד", "אפרת",
    "ארד", "ארד", "אריאל", "אשדוד", "אשקלון",
    "באר יעקב", "באר שבע", "בועיינה-נוג'ידאת", "בית אריה", "בית גן",
    "בית דגן", "בית שאן", "בית שמש", "בית שערים", "בנימינה-גבעת עדה",
    "בני ברק", "בסמה", "בסמת טבעון", "בפועל", "בקה אל-גרביה",
    "בת ים", "גבעת שמואל", "גבעתיים", "גדרה", "גן יבנה",
    "גני תקווה", "גשר הזיו", "דאלית אל-כרמל", "דימונה", "הוד השרון",
    "הרצליה", "זיכרון יעקב", "זכרון יעקב", "חדרה", "חולון",
    "חיפה", "חריש", "טבריה", "טייבה", "טירה", "טירת הכרמל",
    "טמרה", "יבנה", "יהוד-מונוסון", "יוקנעם עילית", "ירושלים",
    "כאבול", "כוכב יאיר-צור יגאל", "כפר יאסיף", "כפר כנא", "כפר מנדא",
    "כפר סבא", "כפר קאסם", "כרמיאל", "לוד", "מגד אל-כרום",
    "מודיעין-מכבים-רעות", "מודיעין עילית", "מועוויה", "מזכרת בתיה",
    "מוצא עילית", "מעלה אדומים", "מעלות-תרשיחא", "מצפה רמון",
    "נהריה", "נס ציונה", "נצרת", "נצרת עילית", "נשר", "נתיבות",
    "נתניה", "עכו", "עפולה", "ערד", "עראבה",
    "פרדס חנה-כרכור", "פתח תקווה", "צפת", "קדימה-צורן", "קיסריה",
    "קלנסווה", "קרית אונו", "קרית ארבע", "קרית אתא", "קרית ביאליק",
    "קרית גת", "קרית ים", "קרית מוצקין", "קרית מלאכי", "קרית שמונה",
    "ראש העין", "ראש פינה", "ראשון לציון", "רהט", "רחובות",
    "רמלה", "רמת גן", "רמת השרון", "רעננה", "שדרות",
    "שפרעם", "תל אביב-יפו", "תל מונד",
    # Additional common cities and villages
    "אבן יהודה", "אור הגנוז", "אלוני הבשן", "אמירים", "בני עי\"ש",
    "גבעת אלה", "גבעת ברנר", "גבעת זאב", "גני עם", "דורות",
    "הגושרים", "זיתן", "חצור הגלילית", "יסוד המעלה", "ינוב",
    "כפר ביאליק", "כפר גלעדי", "כפר הנגיד", "כפר חסידים", "כפר יונה",
    "כפר סירקין", "כפר עציון", "כפר שמריהו", "כפר תבור",
    "לביא", "מגדל", "מגדל העמק", "מגידו", "מחנה יתיר",
    "מטולה", "מיתר", "מכמורת", "מסעדה", "מעגן מיכאל",
    "מעלה גבעה", "מצובה", "מצפה רמון", "מרחביה", "נאות גולן",
    "נהלל", "ניר דוד", "ניר עוז", "סביון", "סח'נין",
    "עין גב", "עין גדי", "עין החורש", "עין הים", "עין חרוד",
    "עין מאהל", "עפולה", "פקיעין", "צור הדסה", "צור יצחק",
    "קצרין", "קרני שומרון", "ראמה", "רמות", "רמת דוד",
    "שגב-שלום", "שמיר", "שפיים", "תקומה",
])

# ── In-memory cache ───────────────────────────────────────────────────────────
_cities_cache: List[str] = []
_cache_lock = threading.Lock()
_cache_loaded = False
_streets_cache: dict = {}   # (city, prefix) → [streets]


def _load_cities_from_api() -> List[str]:
    """Fetch all Israeli localities from the government open-data API."""
    try:
        resp = httpx.get(
            _GOV_API,
            params={
                "resource_id": _LOCALITIES_RESOURCE,
                "limit": 2000,
                "fields": "שם_ישוב",
            },
            timeout=12.0,
        )
        data = resp.json()
        records = data.get("result", {}).get("records", [])
        cities = sorted({r["שם_ישוב"].strip() for r in records if r.get("שם_ישוב")})
        if cities:
            logger.info("🗺 Loaded %d Israeli localities from gov API", len(cities))
            return cities
    except Exception as exc:
        logger.warning("🗺 Gov API unreachable, using fallback city list: %s", exc)
    return _FALLBACK_CITIES


def _ensure_cities_loaded() -> None:
    global _cities_cache, _cache_loaded
    if _cache_loaded:
        return
    with _cache_lock:
        if _cache_loaded:
            return
        _cities_cache = _load_cities_from_api()
        _cache_loaded = True


def load_cities_background() -> None:
    """Called at startup — loads cities in a background thread so server doesn't block."""
    t = threading.Thread(target=_ensure_cities_loaded, daemon=True)
    t.start()


def get_cities(prefix: str = "") -> List[str]:
    """Return Israeli cities matching the given prefix (case-insensitive)."""
    _ensure_cities_loaded()
    prefix = prefix.strip()
    if not prefix:
        return _cities_cache  # full list — frontend does client-side filtering
    pl = prefix.lower()
    return [c for c in _cities_cache if c.lower().startswith(pl)][:50]


def get_all_cities() -> List[str]:
    """Return the full cities list (for normalization logic)."""
    _ensure_cities_loaded()
    return _cities_cache


def get_streets(city: str, prefix: str = "") -> List[str]:
    """Return streets in a city matching the given prefix (calls gov API)."""
    cache_key = (city, prefix)
    if cache_key in _streets_cache:
        return _streets_cache[cache_key]
    try:
        import json as _json
        params: dict = {
            "resource_id": _STREETS_RESOURCE,
            "limit": 20,
            "fields": "שם_רחוב",
            "filters": _json.dumps({"שם_ישוב": city}),
        }
        if prefix:
            params["q"] = prefix
        resp = httpx.get(_GOV_API, params=params, timeout=6.0)
        data = resp.json()
        records = data.get("result", {}).get("records", [])
        streets = sorted({r["שם_רחוב"].strip() for r in records if r.get("שם_רחוב")})
        # Cap cache size
        if len(_streets_cache) > 500:
            # Remove oldest 100 entries
            for k in list(_streets_cache.keys())[:100]:
                del _streets_cache[k]
        _streets_cache[cache_key] = streets
        return streets
    except Exception as exc:
        logger.warning("🗺 Streets API error for city=%s prefix=%s: %s", city, prefix, exc)
        return []


# ── Address normalization ─────────────────────────────────────────────────────

def normalize_city_street(street: str, city: str) -> Optional[tuple]:
    """
    Detect when part of the city name has leaked into the street field, or
    when the city is misspelled / partial.

    Returns (new_street, new_city) if a fix is found, otherwise None.

    Example: street="שמואלזון קרית", city="אתא" → ("שמואלזון", "קרית אתא")
    """
    _ensure_cities_loaded()
    cities = _cities_cache

    # Build a set for fast lookup
    city_set = set(cities)

    # 1. If city is already valid — nothing to fix
    if city in city_set:
        return None

    # 2. Try to find the correct city in the combined string
    combined = f"{street} {city}".strip()

    # Try longest-matching city name first to avoid partial matches
    for candidate in sorted(cities, key=len, reverse=True):
        if candidate in combined:
            # Extract the remainder as the street
            remainder = combined.replace(candidate, "").strip(" ,–-")
            # Sanity: remainder should be shorter than original combined
            if len(remainder) <= len(combined) and remainder:
                return (remainder, candidate)

    return None
