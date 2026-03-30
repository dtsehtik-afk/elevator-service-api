"""Import all models so Alembic autogenerate can detect them."""

from app.models.elevator import Elevator
from app.models.technician import Technician
from app.models.service_call import ServiceCall
from app.models.assignment import Assignment, AuditLog
from app.models.maintenance import MaintenanceSchedule
from app.models.incoming_call import IncomingCallLog

__all__ = [
    "Elevator",
    "Technician",
    "ServiceCall",
    "Assignment",
    "AuditLog",
    "MaintenanceSchedule",
    "IncomingCallLog",
]
