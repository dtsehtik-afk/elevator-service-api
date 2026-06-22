from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from app.auth.dependencies import get_current_user
from app.services.address_service import get_streets_for_city

router = APIRouter(prefix="/addresses", tags=["Addresses"])

@router.get("/cities", summary="Get list of common cities (Stub)")
def get_cities(current_user=Depends(get_current_user)) -> List[str]:
    return ["עפולה", "תל אביב", "ירושלים", "חיפה", "ראשון לציון", "פתח תקווה", "אשדוד", "נתניה",
            "באר שבע", "רחובות", "הרצליה", "כפר סבא", "חדרה", "רמת גן", "בני ברק", "אשקלון",
            "נהריה", "עכו", "טבריה", "נצרת", "אום אל פחם", "עראבה", "שפרעם", "טייבה", "קריית אתא",
            "קריית ביאליק", "קריית מוצקין", "קריית גת", "יקנעם", "עפולה", "מגדל העמק", "טירת כרמל"]

@router.get("/streets", summary="Get official streets for a city from data.gov.il")
def get_streets(city: str, current_user=Depends(get_current_user)) -> List[str]:
    """Return autocomplete list of official street names for the given city."""
    if not city:
        return []
    return get_streets_for_city(city)


@router.get("/geocode", summary="Geocode an Israeli address to lat/lng")
def geocode(
    street: str = Query(...),
    city: str = Query(...),
    house_number: Optional[str] = Query(default=""),
    current_user=Depends(get_current_user),
):
    """Convert a street address to GPS coordinates using Google Maps."""
    from app.services.maps_service import geocode_address
    full_address = f"{street} {house_number}".strip()
    coords = geocode_address(full_address, city)
    if not coords:
        return {"lat": None, "lng": None, "error": "לא נמצאו קואורדינטות לכתובת זו"}
    return {"lat": coords[0], "lng": coords[1]}
