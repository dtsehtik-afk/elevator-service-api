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


def _col_meta(k: str, v: dict) -> dict:
    meta: dict = {
        "key": k,
        "label_he": v["label_he"],
        "type": v["type"],
        "filterable": v.get("filter") is not None,
    }
    if "options" in v:
        meta["options"] = v["options"]
    return meta


@router.get("/schema", summary="All entity types and their available columns")
def get_all_schemas(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from app.services.report_builder import get_schemas
    schemas = get_schemas()
    result = []
    for etype, schema in schemas.items():
        cols = [_col_meta(k, v) for k, v in schema["columns"].items()]
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
    cols = [_col_meta(k, v) for k, v in schema["columns"].items()]
    return {
        "entity_type": entity_type,
        "label_he": schema["label_he"],
        "default_columns": schema["default_columns"],
        "columns": _apply_label_overrides(db, entity_type, cols),
    }


# ── Filter options endpoint ───────────────────────────────────────────────────

@router.get("/filter-options", summary="Lists for quick-filter dropdowns")
def get_filter_options(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    from sqlalchemy import distinct
    from app.models.technician import Technician as TechModel
    from app.models.customer import Customer
    from app.models.elevator import Elevator

    technicians = (
        db.query(TechModel.name)
        .filter(TechModel.name.isnot(None))
        .order_by(TechModel.name)
        .all()
    )
    cities = (
        db.query(distinct(Elevator.city))
        .filter(Elevator.city.isnot(None), Elevator.city != "")
        .order_by(Elevator.city)
        .all()
    )
    customers = (
        db.query(Customer.id, Customer.name)
        .filter(Customer.name.isnot(None))
        .order_by(Customer.name)
        .all()
    )
    return {
        "technicians": [t.name for t in technicians if t.name],
        "cities": [c[0] for c in cities if c[0]],
        "customers": [{"id": str(c.id), "name": c.name} for c in customers],
    }


# ── AI chat endpoint ──────────────────────────────────────────────────────────

class AIChatRequest(BaseModel):
    question: str


@router.post("/ai-chat", summary="Answer a natural-language question using Gemini + DB")
async def ai_chat(
    body: AIChatRequest,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    import os
    from app.services.report_ai_agent import answer_question

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured")

    answer = await answer_question(body.question, db, api_key)
    return {"answer": answer}


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
    xlsx_buf = export_to_excel(result, label_he)

    return StreamingResponse(
        xlsx_buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={entity_type}_report.xlsx"},
    )


# ── AI Natural-Language Query ─────────────────────────────────────────────────

class AIQueryRequest(BaseModel):
    question: str


@router.post("/ai-query", summary="Convert natural language question to a report query and execute it")
def ai_report_query(
    body: AIQueryRequest,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Accepts a Hebrew natural language question, uses Gemini to produce filter params, executes the query, and returns a narrative answer."""
    import json, os, httpx
    from datetime import datetime

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="No question provided")

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI לא מוגדר")

    from app.services.report_builder import get_schemas
    schemas = get_schemas()
    schema_lines = []
    for etype, schema in schemas.items():
        filterable_cols = [k for k, v in schema["columns"].items() if v.get("filter") is not None]
        schema_lines.append(f"- {etype} ({schema['label_he']}): {', '.join(filterable_cols)}")

    today = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f"אתה מנוע שאילתות לדוח שירות מעליות. המשתמש שאל שאלה בעברית."
        f" החזר JSON בלבד (ללא markdown) עם פרמטרים לשאילתה.\n\n"
        f"סוגי נתונים:\n" + "\n".join(schema_lines) + "\n\n"
        f"פעולות סינון: eq, neq, contains, gt, gte, lt, lte, is_null, is_not_null\n"
        f"היום: {today}\n\n"
        f"שאלה: {question}\n\n"
        f"החזר בפורמט:\n"
        f'{{"entity_type":"service_calls","columns":["call_number","created_at","address","city","status","technician_name"],'
        f'"filters":[{{"field":"status","op":"eq","value":"CLOSED"}}],"sort_by":"created_at","sort_dir":"desc"}}'
    )

    try:
        resp = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
            f"?key={api_key}",
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 600, "responseMimeType": "application/json"},
            },
            timeout=20,
        )
        resp.raise_for_status()
        ai_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        params = json.loads(ai_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"שגיאת AI: {exc}")

    entity_type = params.get("entity_type", "service_calls")
    if entity_type not in schemas:
        entity_type = "service_calls"

    from app.services.report_builder import run_report as _run
    result = _run(
        db=db,
        entity_type=entity_type,
        columns=params.get("columns"),
        filters=params.get("filters", []),
        sort_by=params.get("sort_by"),
        sort_dir=params.get("sort_dir", "desc"),
        skip=0,
        limit=200,
        include_custom_fields=False,
    )

    # Pass data back to Gemini for a narrative Hebrew answer
    answer = ""
    try:
        rows_preview = result.get("rows", [])[:40]
        summary_prompt = (
            f"אתה מנתח נתונים של מערכת ניהול מעליות. המשתמש שאל: '{question}'\n\n"
            f"נמצאו {result.get('total', 0)} תוצאות. הנה הנתונים:\n"
            f"{json.dumps(rows_preview, ensure_ascii=False)}\n\n"
            f"כתוב תשובה מקצועית, תמציתית ומלאה בעברית בלבד. כלול מספרים, שמות וסטטיסטיקות רלוונטיות. "
            f"אם אין תוצאות — ציין זאת בלבד. אל תתאר את מבנה הנתונים — ענה על השאלה ישירות."
        )
        ans_resp = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
            f"?key={api_key}",
            json={"contents": [{"role": "user", "parts": [{"text": summary_prompt}]}],
                  "generationConfig": {"maxOutputTokens": 400}},
            timeout=15,
        )
        ans_resp.raise_for_status()
        answer = ans_resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass

    return {**result, "answer": answer, "ai_params": params}


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
