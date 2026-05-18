from fastapi import APIRouter, Depends
from typing import List
from app.auth.dependencies import get_current_user
from app.services.address_service import get_streets_for_city

router = APIRouter(prefix="/addresses", tags=["Addresses"])

@router.get("/cities", summary="Get list of common cities (Stub)")
def get_cities(current_user=Depends(get_current_user)) -> List[str]:
    # Returning a static list of common cities, or the UI can use its own
    return ["עפולה", "תל אביב", "ירושלים", "חיפה", "ראשון לציון", "פתח תקווה", "אשדוד", "נתניה"]

@router.get("/streets", summary="Get official streets for a city from data.gov.il")
def get_streets(city: str, current_user=Depends(get_current_user)) -> List[str]:
    """Return autocomplete list of official street names for the given city."""
    if not city:
        return []
    return get_streets_for_city(city)
