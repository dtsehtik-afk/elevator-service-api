import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, JSON
from sqlalchemy.types import Uuid

from app.database import Base


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Which entity this document belongs to
    entity_type = Column(String(50), nullable=False)   # ELEVATOR|PROJECT|CONTRACT|LEAD|CUSTOMER
    entity_id = Column(Uuid(as_uuid=True), nullable=True)  # NULL = unmatched

    # File metadata
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)     # local path under uploads/documents/
    document_type = Column(String(50), nullable=True)  # SERVICE_AGREEMENT|INSPECTION_REPORT|QUOTE|OTHER (AI-detected)

    # AI extraction results
    extracted_data = Column(JSON, nullable=True)       # full structured extraction
    summary_text = Column(Text, nullable=True)         # short Hebrew summary for bot
    auto_filled = Column(JSON, nullable=True)          # {field: value} fields actually written to DB

    # Processing state
    status = Column(String(20), default="PROCESSED")  # PENDING|PROCESSED|ERROR
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)
