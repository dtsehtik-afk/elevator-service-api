"""Business logic for elevator management."""

import uuid
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.elevator import Elevator
from app.models.service_call import ServiceCall
from app.schemas.elevator import ElevatorCreate, ElevatorUpdate, ElevatorAnalytics


def _ensure_elevator_customer(db: Session, elevator: Elevator) -> None:
    """Guarantee every elevator has a customer_id.

    Priority:
    1. Already has customer_id → nothing to do.
    2. Has management_company_id but no customer_id → find or create a Customer
       that mirrors the ManagementCompany.
    3. Neither → create a COMMITTEE (ועד בית) customer for the building address.
    """
    if elevator.customer_id:
        return

    from app.models.customer import Customer
    from app.models.management_company import ManagementCompany

    if elevator.management_company_id:
        mc: Optional[ManagementCompany] = db.query(ManagementCompany).filter(
            ManagementCompany.id == elevator.management_company_id
        ).first()
        if mc:
            # Find existing Customer mirroring this ManagementCompany (by name+type)
            customer = db.query(Customer).filter(
                Customer.name == mc.name,
                Customer.customer_type == "MANAGEMENT_COMPANY",
            ).first()
            if not customer:
                customer = Customer(
                    id=uuid.uuid4(),
                    name=mc.name,
                    customer_type="MANAGEMENT_COMPANY",
                    phone=mc.phone,
                    email=mc.email,
                    contact_person=mc.contact_name,
                )
                db.add(customer)
                db.flush()
            elevator.customer_id = customer.id
            return

    # No management company — create/find a ועד בית customer for this address
    vaad_name = f"ועד בית — {elevator.address or ''}, {elevator.city or ''}".strip(", ")
    customer = db.query(Customer).filter(
        Customer.name == vaad_name,
        Customer.customer_type == "COMMITTEE",
    ).first()
    if not customer:
        customer = Customer(
            id=uuid.uuid4(),
            name=vaad_name,
            customer_type="COMMITTEE",
            address=elevator.address,
            city=elevator.city,
            phone=elevator.contact_phone,
        )
        db.add(customer)
        db.flush()
    elevator.customer_id = customer.id


def _sync_elevator_to_customer(db: Session, elevator: Elevator, updated_fields: set) -> None:
    """Propagate elevator contact/address changes to its auto-managed customer.

    Only syncs COMMITTEE and MANAGEMENT_COMPANY customers that were auto-created —
    manually managed customers are not overwritten.
    """
    if not elevator.customer_id:
        return

    from app.models.customer import Customer
    customer = db.query(Customer).filter(Customer.id == elevator.customer_id).first()
    if not customer or customer.customer_type not in ("COMMITTEE", "MANAGEMENT_COMPANY"):
        return

    if "address" in updated_fields and elevator.address:
        customer.address = elevator.address
    if "city" in updated_fields and elevator.city:
        customer.city = elevator.city
    if "contact_phone" in updated_fields and elevator.contact_phone:
        customer.phone = elevator.contact_phone


def calculate_risk_score(db: Session, elevator_id: uuid.UUID) -> float:
    """Calculate a risk score (0-100) based on service call history.

    The formula:
    - Total calls in last 90 days → base score
    - Recurring calls add 5 points each
    - CRITICAL calls add 10 points each
    - Capped at 100.
    """
    from datetime import datetime, timedelta, timezone
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

    calls = (
        db.query(ServiceCall)
        .filter(
            ServiceCall.elevator_id == elevator_id,
            ServiceCall.created_at >= ninety_days_ago,
        )
        .all()
    )

    if not calls:
        return 0.0

    score = len(calls) * 3.0
    for call in calls:
        if call.is_recurring:
            score += 5.0
        if call.priority == "CRITICAL":
            score += 10.0

    return min(score, 100.0)


def sync_all_elevator_customers(db: Session) -> int:
    """Ensure every elevator has a customer. Runs at startup to backfill existing data."""
    elevators = db.query(Elevator).filter(Elevator.customer_id == None).all()
    count = 0
    for elevator in elevators:
        try:
            _ensure_elevator_customer(db, elevator)
            count += 1
        except Exception:
            db.rollback()
            continue
    if count:
        db.commit()
    return count


def create_elevator(db: Session, data: ElevatorCreate) -> Elevator:
    """Create and persist a new elevator record.

    Args:
        db: Database session.
        data: Validated elevator creation data.

    Returns:
        The newly created Elevator ORM object.
    """
    elevator = Elevator(**data.model_dump())
    db.add(elevator)
    db.flush()  # get elevator.id before _ensure_elevator_customer
    _ensure_elevator_customer(db, elevator)
    db.commit()
    db.refresh(elevator)
    return elevator


def get_elevator(db: Session, elevator_id: uuid.UUID) -> Optional[Elevator]:
    """Fetch a single elevator by its UUID.

    Returns:
        Elevator or None if not found.
    """
    return db.query(Elevator).filter(Elevator.id == elevator_id).first()


def list_elevators(
    db: Session,
    city: Optional[str] = None,
    status: Optional[str] = None,
    min_risk: Optional[float] = None,
    max_risk: Optional[float] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Elevator]:
    """Return a filtered, paginated list of elevators.

    Args:
        db: Database session.
        city: Filter by city (case-insensitive partial match).
        status: Filter by status (ACTIVE/INACTIVE/UNDER_REPAIR).
        min_risk: Minimum risk_score filter.
        max_risk: Maximum risk_score filter.
        skip: Pagination offset.
        limit: Page size (max 200).

    Returns:
        List of Elevator objects.
    """
    query = db.query(Elevator)
    if city:
        query = query.filter(Elevator.city.ilike(f"%{city}%"))
    if status:
        query = query.filter(Elevator.status == status)
    if min_risk is not None:
        query = query.filter(Elevator.risk_score >= min_risk)
    if max_risk is not None:
        query = query.filter(Elevator.risk_score <= max_risk)
    return query.offset(skip).limit(min(limit, 2000)).all()


def _recalculate_next_service(elevator: Elevator) -> None:
    """Auto-fill next_service_date from last_service_date + maintenance interval.

    Priority:
    1. maintenance_interval_days (explicit, set from import or edit)
    2. service_contract: ANNUAL_6 → 60 days, ANNUAL_12 → 30 days
    3. service_type: COMPREHENSIVE → 30 days, REGULAR → 60 days
    4. Default: 60 days
    """
    from datetime import timedelta
    if not elevator.last_service_date:
        return
    if elevator.maintenance_interval_days:
        days = elevator.maintenance_interval_days
    elif elevator.service_contract == "ANNUAL_12":
        days = 30
    elif elevator.service_contract == "ANNUAL_6":
        days = 60
    elif elevator.service_type == "COMPREHENSIVE":
        days = 30
    else:
        days = 60
    elevator.next_service_date = elevator.last_service_date + timedelta(days=days)


def _recalculate_contract_renewal(elevator: Elevator) -> None:
    """Auto-set contract_renewal = contract_start + 1 year when not explicitly given."""
    from datetime import date
    from dateutil.relativedelta import relativedelta
    if elevator.contract_start and not elevator.contract_renewal:
        elevator.contract_renewal = elevator.contract_start + relativedelta(years=1)


def update_elevator(
    db: Session, elevator_id: uuid.UUID, data: ElevatorUpdate
) -> Optional[Elevator]:
    """Apply partial updates to an elevator.

    Returns:
        Updated Elevator or None if not found.
    """
    from sqlalchemy.exc import IntegrityError
    from fastapi import HTTPException

    elevator = get_elevator(db, elevator_id)
    if not elevator:
        return None
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(elevator, field, value)
    # Always recalculate next_service_date unless it was explicitly overridden in this call
    if "next_service_date" not in updates:
        _recalculate_next_service(elevator)
    elif "last_service_date" in updates and "next_service_date" not in updates:
        _recalculate_next_service(elevator)
    # Auto-calculate contract_renewal when contract_start is set but renewal is not
    if "contract_start" in updates and "contract_renewal" not in updates:
        elevator.contract_renewal = None  # force recalc
        _recalculate_contract_renewal(elevator)
    # Ensure every elevator has a customer; sync contact/address changes
    _ensure_elevator_customer(db, elevator)
    _sync_elevator_to_customer(db, elevator, set(updates.keys()))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="שגיאת שמירה — ערך כפול בשדה ייחודי (מספר סידורי, מס״ד, וכד׳)",
        ) from exc
    db.refresh(elevator)
    return elevator


def get_elevator_analytics(db: Session, elevator_id: uuid.UUID) -> Optional[ElevatorAnalytics]:
    """Return analytics for a specific elevator: fault breakdown, recurring calls, avg resolution.

    Returns:
        ElevatorAnalytics or None if the elevator doesn't exist.
    """
    elevator = get_elevator(db, elevator_id)
    if not elevator:
        return None

    calls = (
        db.query(ServiceCall)
        .filter(ServiceCall.elevator_id == elevator_id)
        .all()
    )

    calls_by_fault: dict = {}
    calls_by_priority: dict = {}
    total_resolution_hours = 0.0
    resolved_count = 0

    for call in calls:
        calls_by_fault[call.fault_type] = calls_by_fault.get(call.fault_type, 0) + 1
        calls_by_priority[call.priority] = calls_by_priority.get(call.priority, 0) + 1
        if call.resolved_at and call.created_at:
            diff = (call.resolved_at - call.created_at).total_seconds() / 3600
            total_resolution_hours += diff
            resolved_count += 1

    avg_resolution = (
        round(total_resolution_hours / resolved_count, 2) if resolved_count else None
    )
    recurring = sum(1 for c in calls if c.is_recurring)

    return ElevatorAnalytics(
        elevator_id=elevator_id,
        total_calls=len(calls),
        recurring_calls=recurring,
        calls_by_fault_type=calls_by_fault,
        calls_by_priority=calls_by_priority,
        avg_resolution_hours=avg_resolution,
        risk_score=elevator.risk_score,
    )
