"""Activity log service — log_activity() helper used across routers."""

import logging
from typing import Optional, Any

from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog

logger = logging.getLogger(__name__)


def log_activity(
    db: Session,
    action: str,
    message: str,
    category: str = "service",
    actor_name: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[Any] = None,
    entity_ref: Optional[str] = None,
) -> None:
    """
    Append an activity entry. Caller must commit the session.
    Uses flush so the record is visible in the same transaction.
    """
    try:
        entry = ActivityLog(
            actor_name=actor_name,
            action=action,
            message=message,
            category=category,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            entity_ref=entity_ref,
        )
        db.add(entry)
        db.flush()
    except Exception as e:
        logger.warning("Failed to log activity '%s': %s", action, e)
