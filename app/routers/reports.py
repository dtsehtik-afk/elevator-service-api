"""Report Builder router — dynamic query, saved views, Excel export."""

import io
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.technician import Technician

router = APIRouter(prefix="/reports", tags=["Reports"])


# ── Request / Response schemas ────────────────────────────────────────────────

class FilterItem(BaseModel):
    field: str
    op: str  # eq|neq|contains|starts_with|gt|gte|lt|lte|in|is_null|is_not_null
    value: Optional[Any] = None


class ReportQuery(BaseModel):
    entity_type: str
    columns: Optional[List[str]] = None
    filters: Optional[List[FilterItem]] = []
    sort_by: Optional[str] = None
    sort_dir: Optional[str] = "desc"
    skip: int = 0
    limit: int = 100
    include_custom_fields: bool = True


class SavedViewCreate(BaseModel):
    entity_type: str
    name: str
    columns: List[str] = []
    filters: List[dict] = []
    sort_by: Optional[str] = None
    sort_dir: str = "desc"
    is_default: bool = False


class SavedViewUpdate(BaseModel):
    name: Optional[str] = None
    columns: Optional[List[str]] = None
    filters: Optional[List[dict]] = None
    sort_by: Optional[str] = None
    sort_dir: Optional[str] = None
    is_default: Optional[bool] = None


# ── Schema endpoints ──────────────────────────────────────────────────────────

def _apply_label_overrides(db: Session, entity_type: str, columns: list) -> list:
    """Merge user-defined label overrides into column definitions."""
    import json
    from sqlalchemy import text as _text
    try:
        row = db.execute(
            _text("SELECT value FROM system_settings WHERE key = :k"),
            {"k": f"field_labels_{entity_type}"},
        ).fetchone()
        overrides = json.loads(row[0]) if row else {}
    except Exception:
        overrides = {}
    if not overrides:
        return columns
    return [
        {**col, "label_he": overrides.get(col["key"], col["label_he"])}
        for col in columns
    ]


@router.get("/schema", summary="All entity types and their available columns")
def get_all_schemas(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.services.report_builder import get_schemas
    schemas = get_schemas()
    result = []
    for etype, schema in schemas.items():
        cols = [
            {
                "key": k,
                "label_he": v["label_he"],
                "type": v["type"],
                "filterable": v.get("filter_attr") is not None,
            }
            for k, v in schema["columns"].items()
        ]
        result.append({
            "entity_type": etype,
            "label_he": schema["label_he"],
            "default_columns": schema["default_columns"],
            "columns": _apply_label_overrides(db, etype, cols),
        })
    return result


@router.get("/schema/{entity_type}", summary="Columns and filter options for an entity")
def get_entity_schema(
    entity_type: str,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.services.report_builder import get_schemas
    schemas = get_schemas()
    if entity_type not in schemas:
        raise HTTPException(status_code=404, detail=f"Entity type '{entity_type}' not found")
    schema = schemas[entity_type]
    cols = [
        {
            "key": k,
            "label_he": v["label_he"],
            "type": v["type"],
            "filterable": v.get("filter_attr") is not None,
        }
        for k, v in schema["columns"].items()
    ]
    return {
        "entity_type": entity_type,
        "label_he": schema["label_he"],
        "default_columns": schema["default_columns"],
        "columns": _apply_label_overrides(db, entity_type, cols),
    }


# ── Query endpoint ────────────────────────────────────────────────────────────

@router.post("/query", summary="Run a dynamic report query")
def run_report(
    body: ReportQuery,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.services.report_builder import run_report as _run, get_schemas
    schemas = get_schemas()
    if body.entity_type not in schemas:
        raise HTTPException(status_code=400, detail=f"Unknown entity_type: {body.entity_type}")

    filters = [f.model_dump() for f in (body.filters or [])]
    result = _run(
        db=db,
        entity_type=body.entity_type,
        columns=body.columns,
        filters=filters,
        sort_by=body.sort_by,
        sort_dir=body.sort_dir or "desc",
        skip=body.skip,
        limit=min(body.limit, 1000),
        include_custom_fields=body.include_custom_fields,
    )
    return result


# ── Export endpoint ───────────────────────────────────────────────────────────

@router.get("/export", summary="Export report as Excel (.xlsx)")
def export_report(
    entity_type: str = Query(...),
    columns: Optional[str] = Query(None, description="Comma-separated column keys"),
    filters: Optional[str] = Query(None, description="JSON array of filter objects"),
    sort_by: Optional[str] = Query(None),
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    import json
    from app.services.report_builder import run_report as _run, export_to_excel, get_schemas

    schemas = get_schemas()
    if entity_type not in schemas:
        raise HTTPException(status_code=400, detail=f"Unknown entity_type: {entity_type}")

    col_list = [c.strip() for c in columns.split(",")] if columns else None
    filter_list = json.loads(filters) if filters else []

    result = _run(
        db=db,
        entity_type=entity_type,
        columns=col_list,
        filters=filter_list,
        sort_by=sort_by,
        sort_dir=sort_dir,
        skip=0,
        limit=10000,
        include_custom_fields=True,
    )

    label_he = schemas[entity_type]["label_he"]
    xlsx_bytes = export_to_excel(result, label_he)

    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={entity_type}_report.xlsx"},
    )


# ── Saved Views CRUD ──────────────────────────────────────────────────────────

@router.get("/views", summary="List current user's saved views")
def list_views(
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.models.saved_view import SavedView
    q = db.query(SavedView).filter(SavedView.user_id == current_user.id)
    if entity_type:
        q = q.filter(SavedView.entity_type == entity_type)
    views = q.order_by(SavedView.created_at.desc()).all()
    return [
        {
            "id": str(v.id),
            "entity_type": v.entity_type,
            "name": v.name,
            "columns": v.columns,
            "filters": v.filters,
            "sort_by": v.sort_by,
            "sort_dir": v.sort_dir,
            "is_default": v.is_default,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        }
        for v in views
    ]


@router.post("/views", summary="Save a new view", status_code=201)
def create_view(
    body: SavedViewCreate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.models.saved_view import SavedView

    if body.is_default:
        db.query(SavedView).filter(
            SavedView.user_id == current_user.id,
            SavedView.entity_type == body.entity_type,
        ).update({"is_default": False})

    view = SavedView(
        user_id=current_user.id,
        entity_type=body.entity_type,
        name=body.name,
        columns=body.columns,
        filters=body.filters,
        sort_by=body.sort_by,
        sort_dir=body.sort_dir,
        is_default=body.is_default,
    )
    db.add(view)
    db.commit()
    db.refresh(view)
    return {"id": str(view.id), "name": view.name, "entity_type": view.entity_type}


@router.put("/views/{view_id}", summary="Update a saved view")
def update_view(
    view_id: uuid.UUID,
    body: SavedViewUpdate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.models.saved_view import SavedView

    view = db.query(SavedView).filter(
        SavedView.id == view_id,
        SavedView.user_id == current_user.id,
    ).first()
    if not view:
        raise HTTPException(status_code=404, detail="View not found")

    updates = body.model_dump(exclude_unset=True)
    if updates.get("is_default"):
        db.query(SavedView).filter(
            SavedView.user_id == current_user.id,
            SavedView.entity_type == view.entity_type,
            SavedView.id != view_id,
        ).update({"is_default": False})

    for k, v in updates.items():
        setattr(view, k, v)
    db.commit()
    db.refresh(view)
    return {"id": str(view.id), "name": view.name}


@router.delete("/views/{view_id}", summary="Delete a saved view", status_code=204)
def delete_view(
    view_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.models.saved_view import SavedView

    view = db.query(SavedView).filter(
        SavedView.id == view_id,
        SavedView.user_id == current_user.id,
    ).first()
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    db.delete(view)
    db.commit()


@router.post("/views/{view_id}/set-default", summary="Set view as default for entity_type")
def set_default_view(
    view_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.models.saved_view import SavedView

    view = db.query(SavedView).filter(
        SavedView.id == view_id,
        SavedView.user_id == current_user.id,
    ).first()
    if not view:
        raise HTTPException(status_code=404, detail="View not found")

    db.query(SavedView).filter(
        SavedView.user_id == current_user.id,
        SavedView.entity_type == view.entity_type,
    ).update({"is_default": False})

    view.is_default = True
    db.commit()
    return {"ok": True}
