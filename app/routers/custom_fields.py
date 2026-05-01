"""Custom Fields router — manage user-defined fields per entity type."""

import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.technician import Technician

router = APIRouter(prefix="/custom-fields", tags=["Custom Fields"])

_VALID_FIELD_TYPES = {
    "TEXT", "NUMBER", "DATE", "BOOLEAN",
    "SELECT", "MULTISELECT", "URL", "PHONE", "EMAIL",
}


def _to_snake(label: str) -> str:
    label = label.strip().lower()
    label = re.sub(r"[\s\-]+", "_", label)
    label = re.sub(r"[^\w]", "", label)
    return label or "field"


# ── Request / Response schemas ────────────────────────────────────────────────

class CustomFieldCreate(BaseModel):
    entity_type: str
    field_label: str
    field_name: Optional[str] = None
    field_type: str = "TEXT"
    options: Optional[List[str]] = None
    required: bool = False
    display_order: int = 0


class CustomFieldUpdate(BaseModel):
    field_label: Optional[str] = None
    field_type: Optional[str] = None
    options: Optional[List[str]] = None
    required: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class ReorderItem(BaseModel):
    id: uuid.UUID
    display_order: int


# ── Field definition endpoints ────────────────────────────────────────────────

@router.get("/{entity_type}", summary="List active custom fields for entity type")
def list_fields(
    entity_type: str,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.models.custom_field import CustomField
    q = db.query(CustomField).filter(CustomField.entity_type == entity_type)
    if not include_inactive:
        q = q.filter(CustomField.is_active == True)
    fields = q.order_by(CustomField.display_order, CustomField.created_at).all()
    return [
        {
            "id": str(f.id),
            "entity_type": f.entity_type,
            "field_name": f.field_name,
            "field_label": f.field_label,
            "field_type": f.field_type,
            "options": f.options,
            "required": f.required,
            "is_active": f.is_active,
            "display_order": f.display_order,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in fields
    ]


@router.post("", summary="Create a custom field (admin)", status_code=201)
def create_field(
    body: CustomFieldCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    from app.models.custom_field import CustomField
    from sqlalchemy.exc import IntegrityError

    if body.field_type not in _VALID_FIELD_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid field_type: {body.field_type}")

    field_name = body.field_name or _to_snake(body.field_label)

    field = CustomField(
        entity_type=body.entity_type,
        field_name=field_name,
        field_label=body.field_label,
        field_type=body.field_type,
        options=body.options,
        required=body.required,
        display_order=body.display_order,
    )
    db.add(field)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Field '{field_name}' already exists for entity '{body.entity_type}'",
        )
    db.refresh(field)
    return {
        "id": str(field.id),
        "field_name": field.field_name,
        "field_label": field.field_label,
        "entity_type": field.entity_type,
    }


@router.put("/{field_id}", summary="Update a custom field label/options/order")
def update_field(
    field_id: uuid.UUID,
    body: CustomFieldUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    from app.models.custom_field import CustomField

    field = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    if body.field_type and body.field_type not in _VALID_FIELD_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid field_type: {body.field_type}")

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(field, k, v)
    db.commit()
    db.refresh(field)
    return {"id": str(field.id), "field_name": field.field_name, "is_active": field.is_active}


@router.delete("/{field_id}", summary="Soft-delete a custom field")
def delete_field(
    field_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    from app.models.custom_field import CustomField

    field = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    field.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/reorder", summary="Bulk update display_order")
def reorder_fields(
    items: List[ReorderItem],
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    from app.models.custom_field import CustomField

    for item in items:
        field = db.query(CustomField).filter(CustomField.id == item.id).first()
        if field:
            field.display_order = item.display_order
    db.commit()
    return {"ok": True}


# ── Field value endpoints ─────────────────────────────────────────────────────

@router.get("/values/{entity_type}/{entity_id}", summary="Get custom field values for an entity")
def get_values(
    entity_type: str,
    entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.models.custom_field import CustomField, CustomFieldValue

    fields = (
        db.query(CustomField)
        .filter(CustomField.entity_type == entity_type, CustomField.is_active == True)
        .order_by(CustomField.display_order)
        .all()
    )
    values = (
        db.query(CustomFieldValue)
        .filter(
            CustomFieldValue.entity_id == entity_id,
            CustomFieldValue.entity_type == entity_type,
        )
        .all()
    )
    val_map = {str(v.field_id): v.value for v in values}

    return [
        {
            "field_id": str(f.id),
            "field_name": f.field_name,
            "field_label": f.field_label,
            "field_type": f.field_type,
            "options": f.options,
            "required": f.required,
            "value": val_map.get(str(f.id)),
        }
        for f in fields
    ]


@router.put("/values/{entity_type}/{entity_id}", summary="Upsert custom field values for an entity")
def set_values(
    entity_type: str,
    entity_id: uuid.UUID,
    values: Dict[str, Any],  # field_id (str UUID) → value
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.models.custom_field import CustomField, CustomFieldValue

    for field_id_str, value in values.items():
        try:
            field_id = uuid.UUID(field_id_str)
        except ValueError:
            continue

        field = db.query(CustomField).filter(CustomField.id == field_id).first()
        if not field or field.entity_type != entity_type:
            continue

        existing = db.query(CustomFieldValue).filter(
            CustomFieldValue.entity_id == entity_id,
            CustomFieldValue.entity_type == entity_type,
            CustomFieldValue.field_id == field_id,
        ).first()

        str_value = str(value) if value is not None else None

        if existing:
            existing.value = str_value
        else:
            db.add(CustomFieldValue(
                entity_id=entity_id,
                entity_type=entity_type,
                field_id=field_id,
                value=str_value,
            ))

    db.commit()
    return {"ok": True}
