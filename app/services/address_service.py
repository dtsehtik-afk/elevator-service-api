import httpx
from typing import List, Optional
import difflib

# In-memory cache: city_name -> list of official streets
_STREET_CACHE = {}

def get_streets_for_city(city: str) -> List[str]:
    """Fetch official streets for a city from data.gov.il CKAN API. Results are cached."""
    if not city:
        return []
    
    city = city.strip()
    if city in _STREET_CACHE:
        return _STREET_CACHE[city]

    url = "https://data.gov.il/api/3/action/datastore_search"
    params = {
        "resource_id": "9ad3862c-8391-4b2f-84a4-2d4c68625f4b",
        "q": city,
        "limit": 5000
    }
    
    try:
        resp = httpx.get(url, params=params, timeout=5)
        if resp.is_success:
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            streets = []
            for r in records:
                if city in r.get("שם_ישוב", ""):
                    streets.append(r.get("שם_רחוב", "").strip())
            
            unique_streets = sorted(list(set(streets)))
            if unique_streets:
                _STREET_CACHE[city] = unique_streets
            return unique_streets
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Error fetching streets for {city}: {e}")
    
    return []

def correct_street_name(city: str, street: str) -> str:
    """
    Attempt to correct a typo in a street name using official city streets.
    Returns the corrected official street name, or the original if no good match.
    """
    if not city or not street:
        return street
        
    official_streets = get_streets_for_city(city)
    if not official_streets:
        return street
        
    # Exact match
    if street in official_streets:
        return street
        
    # Find closest match
    matches = difflib.get_close_matches(street, official_streets, n=1, cutoff=0.7)
    if matches:
        return matches[0]
        
    return street
