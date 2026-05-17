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

    # Service Calls — search by description, reporter, AND elevator address/city
    from app.models.service_call import ServiceCall
    from app.models.elevator import Elevator as _Elevator
    call_rows = (
        db.query(ServiceCall, _Elevator)
        .outerjoin(_Elevator, ServiceCall.elevator_id == _Elevator.id)
        .filter(
            or_(
                ServiceCall.description.ilike(pattern),
                ServiceCall.reported_by.ilike(pattern),
                ServiceCall.resolution_notes.ilike(pattern),
                _Elevator.address.ilike(pattern),
                _Elevator.city.ilike(pattern),
                _Elevator.building_name.ilike(pattern),
            )
        )
        .order_by(ServiceCall.created_at.desc())
        .limit(10)
        .all()
    )
    for call, elev in call_rows:
        addr = f"{elev.address}, {elev.city}" if elev else ""
        num = f"S{str(call.call_number).zfill(5)}" if call.call_number else ""
        results.append(SearchResult(
            id=str(call.id),
            type="call",
            title=f"{num} {call.description[:50] if call.description else 'קריאת שירות'}".strip(),
            subtitle=addr,
            url=f"/calls?callId={call.id}",
        ))

    # Invoices
    try:
        from app.models.invoice import Invoice
        invoices = (
            db.query(Invoice)
            .filter(
                or_(
                    Invoice.number.ilike(pattern),
                    Invoice.notes.ilike(pattern),
                )
            )
            .order_by(Invoice.created_at.desc())
            .limit(5)
            .all()
        )
        for inv in invoices:
            results.append(SearchResult(
                id=str(inv.id),
                type="invoice",
                title=f"חשבונית {inv.number or ''}",
                subtitle=f"₪{inv.total:.0f}" if inv.total else "",
                url=f"/invoices/{inv.id}",
            ))
    except Exception:
        pass

    # Management companies
    try:
        from app.models.management_company import ManagementCompany
        companies = (
            db.query(ManagementCompany)
            .filter(ManagementCompany.name.ilike(pattern))
            .limit(5)
            .all()
        )
        for mc in companies:
            results.append(SearchResult(
                id=str(mc.id),
                type="management_company",
                title=mc.name,
                subtitle="חברת ניהול",
                url=f"/management-companies/{mc.id}",
            ))
    except Exception:
        pass

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
