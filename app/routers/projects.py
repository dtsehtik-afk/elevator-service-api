"""Router for the Construction/Projects module."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.project import Project, ProjectTask
from app.models.technician import Technician
from app.schemas.project import (
    ProjectCreate, ProjectDetail, ProjectResponse, ProjectUpdate,
    ProjectTaskCreate, ProjectTaskResponse, ProjectTaskUpdate,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


def _enrich(p: Project) -> ProjectResponse:
    r = ProjectResponse.model_validate(p)
    r.task_count = len(p.tasks)
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
    return [_enrich(p) for p in projects]


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
    return _enrich(p)


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
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _enrich(p)


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
