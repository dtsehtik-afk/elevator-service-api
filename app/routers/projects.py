"""Router for the Construction/Projects module."""

import logging
import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.contract import Contract, ElevatorContract
from app.models.elevator import Elevator
from app.models.project import Project, ProjectTask
from app.models.technician import Technician
from app.schemas.project import (
    ProjectCreate, ProjectDetail, ProjectResponse, ProjectUpdate,
    ProjectTaskCreate, ProjectTaskResponse, ProjectTaskUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])

# Milestones that must all be True before a project can be marked COMPLETED.
_COMPLETION_BLOCKERS = [
    ("milestone_phase_a",            "פאזה א טרם הושלמה"),
    ("milestone_phase_b",            "פאזה ב טרם הושלמה"),
    ("milestone_phase_c",            "פאזה ג טרם הושלמה"),
    ("milestone_initial_inspection", "תסקיר ראשוני טרם בוצע"),
    ("milestone_consultant_approved","היועץ טרם אישר את הפרויקט"),
]


def _has_active_service_contract(db: Session, project_id) -> bool:
    return bool(
        db.query(Contract).filter(
            Contract.project_id == project_id,
            Contract.status == "ACTIVE",
        ).first()
    )


def _check_completion_allowed(db: Session, p: Project) -> list[str]:
    """Return human-readable blockers preventing COMPLETED status."""
    blockers = [label for field, label in _COMPLETION_BLOCKERS if not getattr(p, field, False)]
    if not _has_active_service_contract(db, p.id):
        blockers.append("חוזה שירות פעיל לא קיים")
    return blockers


def _activate_project_elevators(db: Session, project: Project) -> None:
    """When a project is marked COMPLETED, activate all elevators linked via its contracts."""
    today = date.today()
    contracts = db.query(Contract).filter(Contract.project_id == project.id).all()
    activated = 0
    for contract in contracts:
        for ec in db.query(ElevatorContract).filter(ElevatorContract.contract_id == contract.id).all():
            elev = db.get(Elevator, ec.elevator_id)
            if elev and elev.status != "ACTIVE":
                elev.status = "ACTIVE"
                if not elev.handover_date:
                    elev.handover_date = today
                if not elev.installation_date:
                    elev.installation_date = today
                activated += 1
    if activated:
        db.commit()
        logger.info("Project %s completed → %d elevators activated", project.id, activated)


def _enrich(p: Project, db: Session = None) -> ProjectResponse:
    r = ProjectResponse.model_validate(p)
    r.task_count = len(p.tasks)
    r.customer_name = p.customer.name if p.customer else None
    r.responsible_technician_name = p.responsible_technician.name if p.responsible_technician else None
    if p.consultant:
        r.consultant_name = p.consultant.name
        r.consultant_phone = p.consultant.phone
        r.consultant_email = p.consultant.email
        r.consultant_contacts = p.consultant.consultant_contacts or []
    if db:
        r.has_service_contract = _has_active_service_contract(db, p.id)
    return r


@router.get("", response_model=List[ProjectResponse])
def list_projects(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Project)
    if status:
        q = q.filter(Project.status == status)
    projects = q.order_by(Project.created_at.desc()).all()
    return [_enrich(p, db) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = Project(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _enrich(p, db)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    r = ProjectDetail.model_validate(p)
    r.task_count = len(p.tasks)
    r.tasks = p.tasks
    r.customer_name = p.customer.name if p.customer else None
    r.responsible_technician_name = p.responsible_technician.name if p.responsible_technician else None
    if p.consultant:
        r.consultant_name = p.consultant.name
        r.consultant_phone = p.consultant.phone
        r.consultant_email = p.consultant.email
        r.consultant_contacts = p.consultant.consultant_contacts or []
    r.has_service_contract = _has_active_service_contract(db, p.id)
    return r


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    prev_status = p.status

    # Block COMPLETED if completion requirements not met
    if data.status == "COMPLETED" and prev_status != "COMPLETED":
        # Apply milestone updates first so we check the new values
        payload = data.model_dump(exclude_none=True)
        for k, v in payload.items():
            setattr(p, k, v)
        blockers = _check_completion_allowed(db, p)
        if blockers:
            raise HTTPException(
                status_code=422,
                detail={"message": "לא ניתן לסמן פרויקט כהושלם", "blockers": blockers},
            )
    else:
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(p, k, v)

    db.commit()
    db.refresh(p)
    if prev_status != "COMPLETED" and p.status == "COMPLETED":
        _activate_project_elevators(db, p)
    return _enrich(p, db)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(p)
    db.commit()


@router.post("/{project_id}/tasks", response_model=ProjectTaskResponse, status_code=201)
def create_task(
    project_id: uuid.UUID,
    data: ProjectTaskCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    if not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    t = ProjectTask(project_id=project_id, **data.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.patch("/{project_id}/tasks/{task_id}", response_model=ProjectTaskResponse)
def update_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    data: ProjectTaskUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    t = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{project_id}/tasks/{task_id}", status_code=204)
def delete_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    t = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(t)
    db.commit()
