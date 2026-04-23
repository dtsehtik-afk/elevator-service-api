import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.types import Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)  # "in" or "out"
    msg_type: Mapped[str] = mapped_column(String(30), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcription: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
