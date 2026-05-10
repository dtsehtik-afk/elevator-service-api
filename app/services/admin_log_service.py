"""Admin log service — write and query AdminLog entries."""

from __future__ import annotations

import logging
import traceback
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.admin_log import AdminLog


def log_event(
    db: Session,
    message: str,
    level: str = "ERROR",
    source: str = "",
    exc: Optional[BaseException] = None,
) -> AdminLog:
    """Write a structured event to the admin log table."""
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc else None
    entry = AdminLog(level=level, source=source, message=message, stack_trace=stack)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_logs(
    db: Session,
    level: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
) -> List[AdminLog]:
    query = db.query(AdminLog)
    if level:
        query = query.filter(AdminLog.level == level.upper())
    if source:
        query = query.filter(AdminLog.source.ilike(f"%{source}%"))
    if search:
        query = query.filter(AdminLog.message.ilike(f"%{search}%"))
    return query.order_by(AdminLog.created_at.desc()).offset(skip).limit(limit).all()


def clear_logs(db: Session, level: Optional[str] = None) -> int:
    query = db.query(AdminLog)
    if level:
        query = query.filter(AdminLog.level == level.upper())
    count = query.count()
    query.delete(synchronize_session=False)
    db.commit()
    return count


class DBLogHandler(logging.Handler):
    """Python logging handler that persists WARNING+ records to admin_logs table.

    Attach this after the DB is ready (inside lifespan).  Uses a fresh session
    per record so a failed DB write never propagates up to the caller.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        try:
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                stack = None
                if record.exc_info:
                    stack = self.format(record)
                entry = AdminLog(
                    level=record.levelname,
                    source=f"{record.name}:{record.funcName}",
                    message=record.getMessage(),
                    stack_trace=stack,
                )
                db.add(entry)
                db.commit()
            finally:
                db.close()
        except Exception:
            pass  # never let logging errors crash the app
