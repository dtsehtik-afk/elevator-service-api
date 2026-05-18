import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean
from sqlalchemy.types import Uuid

from app.database import Base


class BotQA(Base):
    __tablename__ = "bot_qa"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    tags = Column(String(500), nullable=True)       # comma-separated: e.g. "intent,assign,reject"
    use_count = Column(Integer, default=0)          # how many times matched in bot context
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(100), nullable=True)  # phone or "system"
