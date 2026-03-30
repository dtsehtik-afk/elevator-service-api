"""Business logic for maintenance schedule management."""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.maintenance import MaintenanceSchedule
from app.schemas.maintenance import MaintenanceCreate, MaintenanceUpdate


def create_maintenance(db: Session, data: MaintenanceCreate) -> MaintenanceSchedule:
    """Schedule a new maintenance event.

    Args:
        db: Database session.
        data: Validated maintenance creation data.

    Returns:
        Created MaintenanceSchedule ORM object.
    """
    maintenance = MaintenanceSchedule(
        elevator_id=data.elevator_id,
        technician_id=data.technician_id,
        scheduled_date=data.scheduled_date,
        maintenance_type=data.maintenance_type,
        checklist=data.checklist or {},
    )
    db.add(maintenance)
    db.commit()
    db.refresh(maintenance)
    return maintenance


def get_maintenance(
    db: Session, maintenance_id: uuid.UUID
) -> Optional[MaintenanceSchedule]:
    """Fetch a single maintenance event by UUID."""
    return (
        db.query(MaintenanceSchedule)
        .filter(MaintenanceSchedule.id == maintenance_id)
        .first()
    )


def list_maintenances(
    db: Session,
    elevator_id: Optional[uuid.UUID] = None,
    technician_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[MaintenanceSchedule]:
    """Return a filtered list of maintenance schedules."""
    query = db.query(MaintenanceSchedule)
    if elevator_id:
        query = query.filter(MaintenanceSchedule.elevator_id == elevator_id)
    if technician_id:
        query = query.filter(MaintenanceSchedule.technician_id == technician_id)
    if status:
        query = query.filter(MaintenanceSchedule.status == status)
    if from_date:
        query = query.filter(MaintenanceSchedule.scheduled_date >= from_date)
    if to_date:
        query = query.filter(MaintenanceSchedule.scheduled_date <= to_date)
    return (
        query.order_by(MaintenanceSchedule.scheduled_date)
        .offset(skip)
        .limit(min(limit, 200))
        .all()
    )


def update_maintenance(
    db: Session, maintenance_id: uuid.UUID, data: MaintenanceUpdate
) -> Optional[MaintenanceSchedule]:
    """Apply partial updates to a maintenance event.

    Automatically sets ``completed_at`` when status changes to COMPLETED.

    Returns:
        Updated MaintenanceSchedule or None if not found.
    """
    maintenance = get_maintenance(db, maintenance_id)
    if not maintenance:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(maintenance, field, value)
    if data.status == "COMPLETED" and not maintenance.completed_at:
        maintenance.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(maintenance)
    return maintenance


def mark_overdue_maintenances(db: Session) -> int:
    """Background job: mark all past-due SCHEDULED maintenances as OVERDUE.

    Should be called once daily (e.g., at midnight via APScheduler).

    Returns:
        Number of records updated.
    """
    today = date.today()
    overdue = (
        db.query(MaintenanceSchedule)
        .filter(
            MaintenanceSchedule.status == "SCHEDULED",
            MaintenanceSchedule.scheduled_date < today,
        )
        .all()
    )
    for m in overdue:
        m.status = "OVERDUE"
    db.commit()
    return len(overdue)


def send_upcoming_reminders(db: Session) -> int:
    """Background job: flag maintenances due within 30 days that haven't been reminded yet.

    In a production system this would send an email/SMS. Here it marks ``reminder_sent=True``.

    Returns:
        Number of reminders sent.
    """
    today = date.today()
    reminder_date = today + timedelta(days=30)

    upcoming = (
        db.query(MaintenanceSchedule)
        .filter(
            MaintenanceSchedule.status == "SCHEDULED",
            MaintenanceSchedule.scheduled_date <= reminder_date,
            MaintenanceSchedule.scheduled_date >= today,
            MaintenanceSchedule.reminder_sent == False,  # noqa: E712
        )
        .all()
    )
    for m in upcoming:
        # In production: send_email(m.technician.email, ...)
        m.reminder_sent = True
    db.commit()
    return len(upcoming)
