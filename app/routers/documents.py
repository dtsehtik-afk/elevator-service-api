"""Documents router — upload and AI-analyze contracts/agreements/inspection reports."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.document_analysis import DocumentAnalysis
from app.models.technician import Technician

router = APIRouter(prefix="/documents", tags=["Documents"])

_MAX_SIZE = 20 * 1024 * 1024  # 20 MB
_ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg", "image/png", "image/webp",
}


class DocumentAnalysisResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: Optional[str]
    filename: str
    document_type: Optional[str]
    summary_text: Optional[str]
    extracted_data: Optional[dict]
    auto_filled: Optional[dict]
    status: str
    error_message: Optional[str]
    created_at: str
    created_by: Optional[str]

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_safe(cls, obj: DocumentAnalysis) -> "DocumentAnalysisResponse":
        return cls(
            id=str(obj.id),
            entity_type=obj.entity_type,
            entity_id=str(obj.entity_id) if obj.entity_id else None,
            filename=obj.filename,
            document_type=obj.document_type,
            summary_text=obj.summary_text,
            extracted_data=obj.extracted_data,
            auto_filled=obj.auto_filled,
            status=obj.status,
            error_message=obj.error_message,
            created_at=obj.created_at.isoformat() if obj.created_at else "",
            created_by=obj.created_by,
        )


@router.post("/analyze", response_model=DocumentAnalysisResponse, status_code=201)
def analyze_document(
    file: UploadFile = File(...),
    entity_type: str = Form(..., description="ELEVATOR|PROJECT|CONTRACT|LEAD|CUSTOMER"),
    entity_id: Optional[str] = Form(None, description="UUID of the linked entity"),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Upload a PDF/image document, analyze with Gemini Vision, and auto-fill linked entity fields."""
    content_type = file.content_type or ""
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="קובץ חייב להיות PDF או תמונה")

    raw = file.file.read()
    if len(raw) > _MAX_SIZE:
        raise HTTPException(status_code=400, detail="קובץ גדול מדי — מקסימום 20MB")

    from app.services.document_ai_service import analyze_document as _analyze
    record = _analyze(
        db=db,
        file_bytes=raw,
        filename=file.filename or "document",
        entity_type=entity_type,
        entity_id=entity_id,
        created_by=current_user.name,
    )
    return DocumentAnalysisResponse.from_orm_safe(record)


@router.get("/{entity_type}/{entity_id}", response_model=List[DocumentAnalysisResponse])
def list_analyses(
    entity_type: str,
    entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """List all document analyses for a given entity."""
    records = (
        db.query(DocumentAnalysis)
        .filter(
            DocumentAnalysis.entity_type == entity_type.upper(),
            DocumentAnalysis.entity_id == entity_id,
        )
        .order_by(DocumentAnalysis.created_at.desc())
        .all()
    )
    return [DocumentAnalysisResponse.from_orm_safe(r) for r in records]


@router.get("/recent", response_model=List[DocumentAnalysisResponse])
def list_recent(
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(DocumentAnalysis)
    if status:
        q = q.filter(DocumentAnalysis.status == status.upper())
    records = q.order_by(DocumentAnalysis.created_at.desc()).limit(limit).all()
    return [DocumentAnalysisResponse.from_orm_safe(r) for r in records]


@router.delete("/{doc_id}", status_code=204)
def delete_analysis(
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "DISPATCHER"):
        raise HTTPException(status_code=403, detail="אין הרשאה")
    record = db.query(DocumentAnalysis).filter(DocumentAnalysis.id == doc_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(record)
    db.commit()
