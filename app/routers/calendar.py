from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.services.calendar_aggregator import fetch_calendar_events, generate_ics_feed

router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/events", summary="Get aggregated calendar events")
def get_events(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Returns events for the frontend calendar.
    Aggregates from invoices, contracts, maintenance, inspections, service calls, and leads.
    """
    events = fetch_calendar_events(db, start, end)
    return {"events": events}

@router.get("/feed.ics", summary="Export calendar as iCal feed")
def get_ics_feed(
    token: Optional[str] = Query(None, description="Auth token for external readers"),
    db: Session = Depends(get_db)
):
    """
    Returns an .ics file containing all upcoming and recent events for sync with Google Calendar/Apple Calendar.
    For simplicity in this V1, we fetch a rolling window of past 30 days and future 365 days.
    """
    # In a real app, you would validate 'token' against a system_settings token or similar.
    # For now, we allow the feed to be accessed if token matches a hardcoded or configured secret.
    import os
    expected_token = os.environ.get("CALENDAR_SYNC_TOKEN", "lift1234")
    if token != expected_token:
        return Response(content="Unauthorized", status_code=401)

    start_date = date.today() - timedelta(days=30)
    end_date = date.today() + timedelta(days=365)
    
    events = fetch_calendar_events(db, start_date, end_date)
    ics_content = generate_ics_feed(events)
    
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="lift-agent-calendar.ics"'}
    )
