"""Import all models so Alembic autogenerate can detect them."""

from app.models.building import Building
from app.models.management_company import ManagementCompany
from app.models.contact import Contact
from app.models.customer import Customer
from app.models.elevator import Elevator
from app.models.technician import Technician
from app.models.service_call import ServiceCall
from app.models.assignment import Assignment, AuditLog
from app.models.maintenance import MaintenanceSchedule
from app.models.incoming_call import IncomingCallLog
from app.models.inspection_report import InspectionReport
from app.models.inspection_email_scan import InspectionEmailScan
from app.models.service_call_email_scan import ServiceCallEmailScan
from app.models.system_settings import SystemSettings
from app.models.quote import Quote
from app.models.contract import Contract, ElevatorContract
from app.models.invoice import Invoice, Receipt
from app.models.part import Part, PartUsage
from app.models.lead import Lead
from app.models.saved_view import SavedView
from app.models.custom_field import CustomField, CustomFieldValue

__all__ = [
    "Building",
    "ManagementCompany",
    "Contact",
    "Customer",
    "Elevator",
    "Technician",
    "ServiceCall",
    "Assignment",
    "AuditLog",
    "MaintenanceSchedule",
    "IncomingCallLog",
    "InspectionReport",
    "InspectionEmailScan",
    "ServiceCallEmailScan",
    "SystemSettings",
    "Quote",
    "Contract",
    "ElevatorContract",
    "Invoice",
    "Receipt",
    "Part",
    "PartUsage",
    "Lead",
    "SavedView",
    "CustomField",
    "CustomFieldValue",
]
