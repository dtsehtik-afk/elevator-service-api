"""Router for manual and automatic assignment of service calls."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_dispatcher_or_admin
from app.database import get_db
from app.models.technician import Technician
from app.schemas.assignment import AssignmentResponse, ManualAssignRequest
from app.services.assignment_service import auto_assign_call, manual_assign_call

router = APIRouter()


@router.post(
    "/{call_id}/assign",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manual assignment",
    description="Manually assign a specific technician to a service call. Requires ADMIN or DISPATCHER.",
)
def assign_call(
    call_id: uuid.UUID,
    data: ManualAssignRequest,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(require_dispatcher_or_admin),
):
    """Manually assign a technician to a service call."""
    try:
        assignment = manual_assign_call(
            db, call_id, data.technician_id, current_user.email, data.notes
        )
        return assignment
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{call_id}/auto-assign",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Auto assignment",
    description="Automatically assign the best available technician with WhatsApp confirmation. Requires ADMIN or DISPATCHER.",
)
def auto_assign(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(require_dispatcher_or_admin),
):
    """Auto-assign the best available technician — sends WhatsApp and awaits confirmation."""
    from app.models.service_call import ServiceCall
    from app.services.ai_assignment_agent import assign_with_confirmation

    call = db.query(ServiceCall).filter(ServiceCall.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Service call not found")

    assignment = assign_with_confirmation(db, call, needs_confirmation=True)
    if not assignment:
        raise HTTPException(
            status_code=503,
            detail="No available technician found.",
        )
    return assignment
