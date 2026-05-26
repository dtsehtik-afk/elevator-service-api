import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.models.invoice import Invoice
from app.models.elevator import Elevator
from app.models.contract import Contract
from app.models.lead import Lead
from app.models.service_call import ServiceCall

def fetch_calendar_events(db: Session, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    """
    Aggregates events from multiple sources into a unified calendar format.
    Each event has: id, title, date, type, url, and optionally an end time.
    """
    events = []

    # 1. Invoices (מועדי תשלום/קבלה)
    invoices = db.query(Invoice).filter(
        Invoice.due_date >= start_date,
        Invoice.due_date <= end_date,
        Invoice.status != "CANCELLED"
    ).all()
    for inv in invoices:
        events.append({
            "id": f"inv-{inv.id}",
            "title": f"חשבונית {inv.number} - מועד תשלום",
            "date": inv.due_date.isoformat(),
            "type": "finance",
            "allDay": True,
            "url": f"/invoices/{inv.id}",
            "status": inv.status
        })

    # 2. Contract Renewals (חידושי חוזים)
    contracts = db.query(Contract).filter(
        Contract.end_date >= start_date,
        Contract.end_date <= end_date
    ).all()
    for con in contracts:
        customer_name = con.customer.name if con.customer else "ללא לקוח"
        events.append({
            "id": f"con-{con.id}",
            "title": f"חידוש חוזה: {customer_name}",
            "date": con.end_date.isoformat(),
            "type": "contract",
            "allDay": True,
            "url": f"/customers/{con.customer_id}/contracts" if con.customer_id else "/contracts",
            "status": "warning" if con.end_date < date.today() else "info"
        })

    # 3. Elevators: Next Maintenance (תחזוקה)
    elevators_maint = db.query(Elevator).filter(
        Elevator.next_service_date >= start_date,
        Elevator.next_service_date <= end_date,
        Elevator.status == "ACTIVE"
    ).all()
    for el in elevators_maint:
        events.append({
            "id": f"maint-{el.id}",
            "title": f"טיפול מעלית - {el.address}, {el.city}",
            "date": el.next_service_date.isoformat(),
            "type": "maintenance",
            "allDay": True,
            "url": f"/elevators/{el.id}"
        })

    # 4. Elevators: Next Inspection (בדיקות מהנדס)
    elevators_insp = db.query(Elevator).filter(
        Elevator.next_inspection_date >= start_date,
        Elevator.next_inspection_date <= end_date,
        Elevator.status == "ACTIVE"
    ).all()
    for el in elevators_insp:
        events.append({
            "id": f"insp-{el.id}",
            "title": f"בדיקת מהנדס - {el.address}, {el.city}",
            "date": el.next_inspection_date.isoformat(),
            "type": "inspection",
            "allDay": True,
            "url": f"/elevators/{el.id}"
        })

    # 5. Service Calls (קריאות שירות מתוכננות)
    # We will use created_at as an all day event, or if there's a deadline, maybe sla_deadline
    calls = db.query(ServiceCall).filter(
        ServiceCall.created_at >= start_date,
        ServiceCall.created_at <= end_date + timedelta(days=1)
    ).all()
    for call in calls:
        if call.status in ("CLOSED", "RESOLVED"):
            continue
        # Use SLA deadline if exists and within range
        target_date = call.sla_deadline if call.sla_deadline else call.created_at
        
        # If it's a specific time, pass it as ISO string with time
        date_str = target_date.isoformat()
        
        el = call.elevator
        location = f"{el.address}, {el.city}" if el else call.reported_by
        events.append({
            "id": f"call-{call.id}",
            "title": f"קריאת שירות: {location}",
            "date": date_str,
            "type": "service_call",
            "allDay": False,
            "url": f"/calls/{call.id}",
            "status": call.priority
        })

    # 6. Leads / Meetings (פגישות)
    leads = db.query(Lead).filter(
        Lead.meeting_date != None,
        Lead.meeting_date >= start_date,
        Lead.meeting_date <= end_date + timedelta(days=1)
    ).all()
    for lead in leads:
        events.append({
            "id": f"lead-{lead.id}",
            "title": f"פגישה: {lead.name}",
            "date": lead.meeting_date.isoformat(),
            "type": "meeting",
            "allDay": False,
            "url": f"/crm/leads?id={lead.id}",
            "status": lead.status
        })

    return events

def generate_ics_feed(events: List[Dict[str, Any]]) -> str:
    """Generates an iCalendar formatted string from events."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lift Agent//Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:אקורד מעליות - יומן מרכזי"
    ]
    
    for ev in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{ev['id']}@lift-agent.com")
        
        # Format dates
        dt = ev['date']
        if ev.get('allDay'):
            # Format: YYYYMMDD
            fmt_date = dt.replace("-", "")[:8]
            lines.append(f"DTSTART;VALUE=DATE:{fmt_date}")
            # End date is start date + 1 day for all-day events in ICS
            from datetime import datetime
            d = datetime.strptime(fmt_date, "%Y%m%d") + timedelta(days=1)
            lines.append(f"DTEND;VALUE=DATE:{d.strftime('%Y%m%d')}")
        else:
            # Parse ISO datetime manually. Assuming format YYYY-MM-DDTHH:MM:SS
            # Since it can have +03:00, we'll just slice the first 19 chars
            try:
                dt_clean = dt[:19].replace("-", "").replace(":", "") + "Z"
                lines.append(f"DTSTART:{dt_clean}")
                
                # We need to compute an end time. Let's just use 1 hour after.
                # To do this safely, we parse dt clean:
                from datetime import datetime
                parsed = datetime.strptime(dt[:19], "%Y-%m-%dT%H:%M:%S")
                end_parsed = parsed + timedelta(hours=1)
                lines.append(f"DTEND:{end_parsed.strftime('%Y%m%dT%H%M%SZ')}")
            except Exception:
                # Fallback to all-day if parsing fails
                fmt_date = dt.replace("-", "")[:8]
                lines.append(f"DTSTART;VALUE=DATE:{fmt_date}")
        
        lines.append(f"SUMMARY:{ev['title']}")
        url_abs = f"https://lift-agent.com{ev['url']}"
        lines.append(f"URL:{url_abs}")
        lines.append(f"DESCRIPTION:קישור: {url_abs}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)
