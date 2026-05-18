"""Bot QA router — manage Q&A pairs used as context for the WhatsApp chat agent."""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.bot_qa import BotQA
from app.models.technician import Technician

router = APIRouter(prefix="/bot-qa", tags=["BotQA"])


class BotQACreate(BaseModel):
    question: str
    answer: str
    tags: Optional[str] = None
    created_by: Optional[str] = None


class BotQAUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    tags: Optional[str] = None
    active: Optional[bool] = None


class BotQAResponse(BaseModel):
    id: uuid.UUID
    question: str
    answer: str
    tags: Optional[str]
    use_count: int
    active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=List[BotQAResponse])
def list_qa(
    active_only: bool = Query(True),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(BotQA)
    if active_only:
        q = q.filter(BotQA.active == True)
    if search:
        q = q.filter(
            BotQA.question.ilike(f"%{search}%") | BotQA.answer.ilike(f"%{search}%")
        )
    return q.order_by(BotQA.use_count.desc(), BotQA.created_at.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=BotQAResponse, status_code=201)
def create_qa(
    body: BotQACreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    qa = BotQA(**body.model_dump())
    db.add(qa)
    db.commit()
    db.refresh(qa)
    return qa


@router.put("/{qa_id}", response_model=BotQAResponse)
def update_qa(
    qa_id: uuid.UUID,
    body: BotQAUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    qa = db.query(BotQA).filter(BotQA.id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail="QA entry not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(qa, field, value)
    qa.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(qa)
    return qa


@router.delete("/{qa_id}", status_code=204)
def delete_qa(
    qa_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    qa = db.query(BotQA).filter(BotQA.id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail="QA entry not found")
    db.delete(qa)
    db.commit()
