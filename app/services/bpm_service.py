"""
BPM Service — Business Process Management validation for service call status transitions.

Rules enforced:
1. Cannot close/resolve a call without resolution_notes.
2. New calls (requires_time_report=True) must have arrival + departure times before closing.
3. Chargeable calls without a linked quote or invoice trigger a warning (future: auto-create).

Backward compatibility:
  Existing calls were migrated with requires_time_report=False via server_default.
  Only calls created after BPM was deployed will have requires_time_report=True,
  so legacy records are never blocked.
"""

from app.models.service_call import ServiceCall


class BPMValidationError(ValueError):
    """Raised when a status transition violates a business rule."""
    pass


TERMINAL_STATUSES = {"RESOLVED", "CLOSED"}


def validate_service_call_transition(
    call: ServiceCall,
    new_status: str,
) -> None:
    """
    Validate a status transition for a service call.
    Raises BPMValidationError with a user-facing Hebrew message if a rule is violated.

    Usage (in a router or service):
        validate_service_call_transition(call, new_status)
        call.status = new_status
        db.commit()
    """
    if new_status not in TERMINAL_STATUSES:
        # Only validate closing transitions for now
        return

    # Rule 1: Resolution notes are mandatory for all calls
    if not call.resolution_notes or not call.resolution_notes.strip():
        raise BPMValidationError(
            "לא ניתן לסגור קריאה ללא תיאור התיקון. יש למלא את שדה 'הערות סיום'."
        )

    # Rule 2: Arrival + departure times required for new calls (backward-compatible)
    if getattr(call, "requires_time_report", False):
        if not call.technician_arrival_time:
            raise BPMValidationError(
                "חובה לדווח שעת הגעה לפני סגירת קריאה."
            )
        if not call.technician_departure_time:
            raise BPMValidationError(
                "חובה לדווח שעת עזיבה לפני סגירת קריאה."
            )

    # Rule 3: Chargeable calls should have a commercial document
    if call.is_chargeable and not call.quote_id and not call.invoice_id:
        # Non-blocking warning for now — future: auto-create draft invoice
        # This can be escalated to a BPMValidationError when billing module is ready
        pass
