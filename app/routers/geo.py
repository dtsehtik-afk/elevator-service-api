"""Geo endpoints — Israeli cities and streets autocomplete."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.services.geo_service import get_cities, get_streets

router = APIRouter(prefix="/geo", tags=["Geo"])


@router.get("/cities", response_model=List[str])
def cities(q: str = Query(default="", description="Prefix to filter cities")):
    """Return Israeli cities/localities matching the given prefix."""
    return get_cities(q)


@router.get("/streets", response_model=List[str])
def streets(
    city: str = Query(..., description="City name"),
    q: str = Query(default="", description="Street prefix"),
):
    """Return streets in the given Israeli city matching the given prefix."""
    return get_streets(city, q)
