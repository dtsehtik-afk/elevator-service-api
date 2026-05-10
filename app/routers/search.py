"""Global search endpoint — queries elevators, customers, service calls, and technicians."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.technician import Technician

router = APIRouter(prefix="/search", tags=["search"])


class SearchResult(BaseModel):
    id: str
    type: str          # elevator | customer | call | technician
    title: str
    subtitle: str
    url: str


@router.get("", response_model=List[SearchResult])
def global_search(
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Full-text search across elevators, customers, service calls, and technicians."""
    results: List[SearchResult] = []
    pattern = f"%{q}%"

    # Elevators
    from app.models.elevator import Elevator
    elevators = (
        db.query(Elevator)
        .filter(
            or_(
                Elevator.address.ilike(pattern),
                Elevator.building_name.ilike(pattern),
                Elevator.city.ilike(pattern),
                Elevator.serial_number.ilike(pattern),
                Elevator.internal_number.ilike(pattern),
            )
        )
        .limit(10)
        .all()
    )
    for e in elevators:
        name = e.building_name or e.address or "מעלית"
        results.append(SearchResult(
            id=str(e.id),
            type="elevator",
            title=name,
            subtitle=f"{e.city or ''} · {e.address or ''}".strip(" ·"),
            url=f"/elevators/{e.id}",
        ))

    # Customers
    from app.models.customer import Customer
    customers = (
        db.query(Customer)
        .filter(
            or_(
                Customer.name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.email.ilike(pattern),
            )
        )
        .limit(8)
        .all()
    )
    for c in customers:
        results.append(SearchResult(
            id=str(c.id),
            type="customer",
            title=c.name,
            subtitle=c.phone or c.email or "",
            url=f"/customers/{c.id}",
        ))

    # Service Calls
    from app.models.service_call import ServiceCall
    calls = (
        db.query(ServiceCall)
        .filter(
            or_(
                ServiceCall.description.ilike(pattern),
                ServiceCall.reported_by.ilike(pattern),
                ServiceCall.technician_notes.ilike(pattern),
            )
        )
        .order_by(ServiceCall.created_at.desc())
        .limit(8)
        .all()
    )
    for call in calls:
        results.append(SearchResult(
            id=str(call.id),
            type="call",
            title=call.description[:60] if call.description else "קריאת שירות",
            subtitle=f"#{call.call_number or ''} · {call.status}",
            url=f"/calls?search={call.id}",
        ))

    # Technicians
    technicians = (
        db.query(Technician)
        .filter(
            or_(
                Technician.name.ilike(pattern),
                Technician.phone.ilike(pattern),
                Technician.email.ilike(pattern),
            )
        )
        .limit(5)
        .all()
    )
    for t in technicians:
        results.append(SearchResult(
            id=str(t.id),
            type="technician",
            title=t.name,
            subtitle=t.phone or t.email or "",
            url=f"/technicians",
        ))

    return results[:30]
