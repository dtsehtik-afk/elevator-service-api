"""Import all models so Alembic autogenerate can detect them."""

from app.models.building import Building
from app.models.management_company import ManagementCompany
from app.models.contact import Contact
from app.models.elevator import Elevator
from app.models.technician import Technician
from app.models.service_call import ServiceCall
from app.models.assignment import Assignment, AuditLog
from app.models.maintenance import MaintenanceSchedule
from app.models.incoming_call import IncomingCallLog
from app.models.inspection_report import InspectionReport

__all__ = [
    "Building",
    "ManagementCompany",
    "Contact",
    "Elevator",
    "Technician",
    "ServiceCall",
    "Assignment",
    "AuditLog",
    "MaintenanceSchedule",
    "IncomingCallLog",
    "InspectionReport",
]
