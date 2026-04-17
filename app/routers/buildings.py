"""Buildings router — CRUD for physical building grouping."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.building import Building
from app.models.elevator import Elevator
from app.models.technician import Technician
from app.schemas.building import BuildingCreate, BuildingDetail, BuildingResponse, BuildingUpdate

router = APIRouter(prefix="/buildings", tags=["Buildings"])


@router.get("", response_model=List[BuildingResponse])
def list_buildings(
    city: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Building)
    if city:
        q = q.filter(Building.city.ilike(f"%{city}%"))
    buildings = q.order_by(Building.city, Building.address).offset(skip).limit(limit).all()
    result = []
    for b in buildings:
        count = db.query(Elevator).filter(Elevator.building_id == b.id).count()
        r = BuildingResponse.model_validate(b)
        r.elevator_count = count
        result.append(r)
    return result


@router.post("", response_model=BuildingResponse, status_code=201)
def create_building(
    data: BuildingCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    b = Building(**data.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    r = BuildingResponse.model_validate(b)
    r.elevator_count = 0
    return r


@router.get("/{building_id}", response_model=BuildingDetail)
def get_building(
    building_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    b = db.query(Building).filter(Building.id == building_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Building not found")
    count = db.query(Elevator).filter(Elevator.building_id == b.id).count()
    r = BuildingDetail.model_validate(b)
    r.elevator_count = count
    r.elevators = b.elevators
    r.contacts = b.contacts
    return r


@router.patch("/{building_id}", response_model=BuildingResponse)
def update_building(
    building_id: uuid.UUID,
    data: BuildingUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    b = db.query(Building).filter(Building.id == building_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Building not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    count = db.query(Elevator).filter(Elevator.building_id == b.id).count()
    r = BuildingResponse.model_validate(b)
    r.elevator_count = count
    return r


@router.delete("/{building_id}", status_code=204)
def delete_building(
    building_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    b = db.query(Building).filter(Building.id == building_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Building not found")
    # Detach elevators (SET NULL via FK) before deleting
    db.query(Elevator).filter(Elevator.building_id == building_id).update({Elevator.building_id: None})
    db.delete(b)
    db.commit()
