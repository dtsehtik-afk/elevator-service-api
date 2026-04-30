"""ERP Dashboard router — נתוני מגה-דשבורד."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.elevator import Elevator
from app.models.invoice import Invoice
from app.models.lead import Lead
from app.models.maintenance import MaintenanceSchedule
from app.models.part import Part
from app.models.service_call import ServiceCall
from app.models.technician import Technician

router = APIRouter(prefix="/erp", tags=["ERP Dashboard"])


@router.get("/dashboard")
def erp_dashboard(
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    today = date.today()
    month_start = today.replace(day=1)
    next_30 = today + timedelta(days=30)

    # ── Service metrics ────────────────────────────────────────────────────────
    open_calls = db.query(func.count(ServiceCall.id)).filter(
        ServiceCall.status.in_(["OPEN", "ASSIGNED", "IN_PROGRESS"])
    ).scalar() or 0

    critical_calls = db.query(func.count(ServiceCall.id)).filter(
        ServiceCall.status.in_(["OPEN", "ASSIGNED"]),
        ServiceCall.priority == "CRITICAL"
    ).scalar() or 0

    overdue_maintenance = db.query(func.count(MaintenanceSchedule.id)).filter(
        MaintenanceSchedule.status == "OVERDUE"
    ).scalar() or 0

    upcoming_maintenance = db.query(func.count(MaintenanceSchedule.id)).filter(
        MaintenanceSchedule.status == "SCHEDULED",
        MaintenanceSchedule.scheduled_date <= next_30,
    ).scalar() or 0

    # ── CRM metrics ───────────────────────────────────────────────────────────
    total_customers = db.query(func.count(Customer.id)).filter(Customer.is_active == True).scalar() or 0
    active_contracts = db.query(func.count(Contract.id)).filter(Contract.status == "ACTIVE").scalar() or 0
    expiring_contracts = db.query(func.count(Contract.id)).filter(
        Contract.status == "ACTIVE",
        Contract.end_date <= next_30,
    ).scalar() or 0

    new_leads = db.query(func.count(Lead.id)).filter(Lead.status == "NEW").scalar() or 0

    # ── Financial metrics ─────────────────────────────────────────────────────
    month_revenue = db.query(func.sum(Invoice.total)).filter(
        Invoice.status == "PAID",
        Invoice.paid_at >= month_start,
    ).scalar() or 0

    open_receivables = db.query(func.sum(Invoice.total - Invoice.amount_paid)).filter(
        Invoice.status.in_(["SENT", "PARTIAL", "OVERDUE"])
    ).scalar() or 0

    overdue_invoices = db.query(func.count(Invoice.id)).filter(
        Invoice.status == "OVERDUE"
    ).scalar() or 0

    # ── Inventory metrics ─────────────────────────────────────────────────────
    low_stock_parts = db.query(func.count(Part.id)).filter(
        Part.is_active == True,
        Part.quantity < Part.min_quantity,
    ).scalar() or 0

    # ── Elevators ────────────────────────────────────────────────────────────
    total_elevators = db.query(func.count(Elevator.id)).filter(Elevator.status == "ACTIVE").scalar() or 0
    high_risk = db.query(func.count(Elevator.id)).filter(Elevator.risk_score >= 7).scalar() or 0
    with_debt = db.query(func.count(Elevator.id)).filter(Elevator.has_debt == True).scalar() or 0

    # ── Alerts ────────────────────────────────────────────────────────────────
    alerts = []
    if critical_calls:
        alerts.append({"level": "error", "message": f"{critical_calls} קריאות קריטיות פתוחות"})
    if overdue_maintenance:
        alerts.append({"level": "warning", "message": f"{overdue_maintenance} תחזוקות באיחור"})
    if overdue_invoices:
        alerts.append({"level": "warning", "message": f"{overdue_invoices} חשבוניות באיחור"})
    if low_stock_parts:
        alerts.append({"level": "info", "message": f"{low_stock_parts} חלקי חילוף במלאי נמוך"})
    if expiring_contracts:
        alerts.append({"level": "info", "message": f"{expiring_contracts} חוזים פגים ב-30 הימים הקרובים"})
    if high_risk:
        alerts.append({"level": "warning", "message": f"{high_risk} מעליות בסיכון גבוה"})

    return {
        "service": {
            "open_calls": open_calls,
            "critical_calls": critical_calls,
            "overdue_maintenance": overdue_maintenance,
            "upcoming_maintenance": upcoming_maintenance,
        },
        "crm": {
            "total_customers": total_customers,
            "active_contracts": active_contracts,
            "expiring_contracts": expiring_contracts,
            "new_leads": new_leads,
        },
        "financial": {
            "month_revenue": float(month_revenue),
            "open_receivables": float(open_receivables),
            "overdue_invoices": overdue_invoices,
        },
        "inventory": {
            "low_stock_parts": low_stock_parts,
        },
        "elevators": {
            "total_active": total_elevators,
            "high_risk": high_risk,
            "with_debt": with_debt,
        },
        "alerts": alerts,
    }


@router.get("/related/{entity_type}/{entity_id}", tags=["Cross-Reference"])
def get_related(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Universal cross-reference: returns all linked entities for any entity type."""
    import uuid as _uuid
    try:
        eid = _uuid.UUID(entity_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid UUID")

    from fastapi import HTTPException

    if entity_type == "elevator":
        e = db.query(Elevator).filter(Elevator.id == eid).first()
        if not e:
            raise HTTPException(status_code=404, detail="Elevator not found")

        open_calls = db.query(func.count(ServiceCall.id)).filter(
            ServiceCall.elevator_id == eid,
            ServiceCall.status.in_(["OPEN", "ASSIGNED", "IN_PROGRESS"])
        ).scalar() or 0

        from app.models.contract import ElevatorContract
        contracts = db.query(ElevatorContract).filter(ElevatorContract.elevator_id == eid).all()

        invoices = db.query(Invoice).filter(
            Invoice.contract_id.in_([ec.contract_id for ec in contracts])
        ).all() if contracts else []

        return {
            "entity": {"type": "elevator", "id": entity_id, "label": f"{e.address}, {e.city}"},
            "links": {
                "customer": {"id": str(e.customer_id), "name": e.customer.name} if e.customer else None,
                "management_company": {"id": str(e.management_company_id), "name": e.management_company.name} if e.management_company else None,
                "building": {"id": str(e.building_id)} if e.building_id else None,
                "open_service_calls": open_calls,
                "contracts": [{"id": str(ec.contract_id), "number": ec.contract.number, "status": ec.contract.status} for ec in contracts],
                "invoices": [{"id": str(inv.id), "number": inv.number, "total": float(inv.total), "status": inv.status} for inv in invoices],
            }
        }

    elif entity_type == "customer":
        from app.routers.customers import get_customer_related
        return get_customer_related(eid, db, _)

    elif entity_type == "contract":
        c = db.query(Contract).filter(Contract.id == eid).first()
        if not c:
            raise HTTPException(status_code=404, detail="Contract not found")
        from app.models.contract import ElevatorContract
        links = db.query(ElevatorContract).filter(ElevatorContract.contract_id == eid).all()
        invoices = db.query(Invoice).filter(Invoice.contract_id == eid).all()
        quotes = db.query(__import__("app.models.quote", fromlist=["Quote"]).Quote).filter(
            __import__("app.models.quote", fromlist=["Quote"]).Quote.contract_id == eid
        ).all()
        return {
            "entity": {"type": "contract", "id": entity_id, "label": c.number},
            "links": {
                "customer": {"id": str(c.customer_id), "name": c.customer.name},
                "elevators": [{"id": str(l.elevator_id), "address": l.elevator.address} for l in links],
                "invoices": [{"id": str(inv.id), "number": inv.number, "status": inv.status} for inv in invoices],
                "quotes": [{"id": str(q.id), "number": q.number, "status": q.status} for q in quotes],
            }
        }

    raise HTTPException(status_code=400, detail=f"Unknown entity type: {entity_type}")
