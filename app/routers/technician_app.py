"""
Mobile-friendly technician web app.
Simple HTML pages served at /app/* — no login required, auth via tech ID in URL.
Technicians bookmark these links from the morning WhatsApp message.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter()


def _get_tech_and_call(db: Session, tech_id: str):
    """Return (technician, active_assignment, call) or raise 404."""
    import uuid
    from app.models.technician import Technician
    from app.models.assignment import Assignment
    from app.models.service_call import ServiceCall

    try:
        tid = uuid.UUID(tech_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="לא נמצא")

    tech = db.query(Technician).filter(Technician.id == tid).first()
    if not tech:
        raise HTTPException(status_code=404, detail="טכנאי לא נמצא")

    assignment = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tid,
                Assignment.status == "CONFIRMED")
        .order_by(Assignment.assigned_at.desc())
        .first()
    )
    call = None
    if assignment:
        call = db.query(ServiceCall).filter(
            ServiceCall.id == assignment.service_call_id,
            ServiceCall.status.in_(["ASSIGNED", "IN_PROGRESS"])
        ).first()

    return tech, assignment, call


@router.get("/tech/{tech_id}", response_class=HTMLResponse, include_in_schema=False)
def technician_portal(tech_id: str, db: Session = Depends(get_db)):
    """Main technician portal — shows active call and report form."""
    tech, assignment, call = _get_tech_and_call(db, tech_id)

    if not call:
        return HTMLResponse(_no_call_page(tech.name))

    from app.models.elevator import Elevator
    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    address = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"

    from app.utils.constants_server import FAULT_TYPE_HE, PRIORITY_HE
    fault = FAULT_TYPE_HE.get(call.fault_type, call.fault_type)
    priority = PRIORITY_HE.get(call.priority, call.priority)
    travel = f"~{assignment.travel_minutes} דק׳" if assignment.travel_minutes else "—"

    return HTMLResponse(_active_call_page(
        tech_id=tech_id,
        tech_name=tech.name,
        call_id=str(call.id),
        address=address,
        fault=fault,
        priority=priority,
        reporter=call.reported_by,
        travel=travel,
    ))


class ReportSubmit(BaseModel):
    notes: str
    resolved: bool = True
    quote_needed: bool = False


@router.post("/tech/{tech_id}/report", response_class=HTMLResponse, include_in_schema=False)
def submit_report(tech_id: str, data: ReportSubmit, db: Session = Depends(get_db)):
    """Technician submits a repair report — resolves the call."""
    from datetime import datetime, timezone
    from app.models.assignment import Assignment, AuditLog
    from app.models.service_call import ServiceCall

    tech, assignment, call = _get_tech_and_call(db, tech_id)
    if not call:
        return HTMLResponse(_no_call_page(tech.name))

    call.status = "RESOLVED" if data.resolved else "IN_PROGRESS"
    if data.resolved:
        call.resolved_at = datetime.now(timezone.utc)
    call.resolution_notes = data.notes
    call.quote_needed = data.quote_needed

    if data.resolved and assignment:
        assignment.status = "AUTO_ASSIGNED"

    audit = AuditLog(
        service_call_id=call.id,
        changed_by=tech.email,
        old_status="IN_PROGRESS",
        new_status="RESOLVED" if data.resolved else "IN_PROGRESS",
        notes=f"דו\"ח טכנאי: {data.notes}",
    )
    db.add(audit)
    db.commit()

    if data.resolved:
        # Notify via WhatsApp
        try:
            from app.services.whatsapp_service import _send_message
            _send_message(tech.whatsapp_number or tech.phone,
                          f"✅ הקריאה נסגרה בהצלחה. תודה {tech.name}!")
        except Exception:
            pass

    return HTMLResponse(_success_page(tech.name, data.resolved, data.quote_needed))


# ── HTML templates ─────────────────────────────────────────────────────────────

_BASE_STYLE = """
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Arial, sans-serif; direction: rtl;
         background: #f0f2f5; min-height: 100vh; padding: 16px; }
  .card { background: white; border-radius: 12px; padding: 20px;
          box-shadow: 0 2px 8px rgba(0,0,0,.1); margin-bottom: 16px; }
  h1 { font-size: 1.3rem; color: #1a1a2e; margin-bottom: 4px; }
  h2 { font-size: 1rem; color: #555; margin-bottom: 12px; }
  .row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
  .label { color: #888; font-size: .85rem; min-width: 80px; }
  .value { font-weight: 600; }
  textarea { width: 100%; border: 1px solid #ddd; border-radius: 8px;
             padding: 12px; font-size: 1rem; direction: rtl;
             min-height: 100px; resize: vertical; margin-bottom: 12px; }
  .btn { display: block; width: 100%; padding: 14px;
         border: none; border-radius: 10px; font-size: 1rem;
         font-weight: 700; cursor: pointer; margin-bottom: 10px; }
  .btn-green  { background: #22c55e; color: white; }
  .btn-orange { background: #f97316; color: white; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 20px;
           font-size: .8rem; font-weight: 600; }
  .badge-red    { background: #fee2e2; color: #dc2626; }
  .badge-orange { background: #ffedd5; color: #ea580c; }
  .badge-blue   { background: #dbeafe; color: #2563eb; }
  .success { text-align: center; padding: 40px 20px; }
  .emoji { font-size: 3rem; margin-bottom: 16px; }
  .checkbox-row { display: flex; align-items: center; gap: 10px;
                  background: #fffbeb; border: 1px solid #fde68a;
                  border-radius: 8px; padding: 12px; margin-bottom: 12px; cursor: pointer; }
  .checkbox-row input[type=checkbox] { width: 20px; height: 20px; cursor: pointer; }
  .checkbox-row label { font-size: 1rem; font-weight: 600; color: #92400e; cursor: pointer; }
</style>
"""


def _active_call_page(tech_id, tech_name, call_id, address, fault, priority, reporter, travel):
    priority_class = "badge-red" if "קריטי" in priority else (
        "badge-orange" if "גבוה" in priority else "badge-blue")
    return f"""<!DOCTYPE html><html><head>{_BASE_STYLE}<title>קריאת שירות</title></head><body>
<div class="card">
  <h1>שלום {tech_name} 👋</h1>
  <h2>קריאת שירות פעילה</h2>
  <div class="row"><span class="label">📍 כתובת</span><span class="value">{address}</span></div>
  <div class="row"><span class="label">⚡ תקלה</span><span class="value">{fault}</span></div>
  <div class="row"><span class="label">⚠️ עדיפות</span>
    <span class="badge {priority_class}">{priority}</span></div>
  <div class="row"><span class="label">👤 מתקשר</span><span class="value">{reporter}</span></div>
  <div class="row"><span class="label">🚗 נסיעה</span><span class="value">{travel}</span></div>
</div>
<div class="card">
  <h2>דו"ח סיום טיפול</h2>
  <textarea id="notes" placeholder="תאר את הטיפול שבוצע, חלקים שהוחלפו וכו׳..."></textarea>
  <div class="checkbox-row" onclick="document.getElementById('quote').click()">
    <input type="checkbox" id="quote">
    <label for="quote">💰 נדרשת הצעת מחיר ללקוח</label>
  </div>
  <button class="btn btn-green" onclick="submitReport(true)">✅ סיימתי — סגור קריאה</button>
  <button class="btn btn-orange" onclick="submitReport(false)">🔧 עדיין בטיפול — שמור הערה</button>
</div>
<script>
function submitReport(resolved) {{
  const notes = document.getElementById('notes').value.trim();
  const quote_needed = document.getElementById('quote').checked;
  if (resolved && !notes) {{ alert('נא למלא תיאור הטיפול לפני סגירת הקריאה'); return; }}
  fetch('/app/tech/{tech_id}/report', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ notes: notes || '—', resolved, quote_needed }})
  }}).then(r => r.text()).then(html => {{
    document.open(); document.write(html); document.close();
  }}).catch(() => alert('שגיאה בשליחת הדו"ח, נסה שוב'));
}}
</script>
</body></html>"""


def _no_call_page(name):
    return f"""<!DOCTYPE html><html><head>{_BASE_STYLE}<title>אין קריאה</title></head><body>
<div class="card success">
  <div class="emoji">✅</div>
  <h1>שלום {name}</h1>
  <p style="color:#555;margin-top:8px">אין קריאות פעילות כרגע</p>
</div></body></html>"""


def _success_page(name, resolved, quote_needed=False):
    if resolved:
        quote_note = (
            '<p style="margin-top:12px;background:#fffbeb;border:1px solid #fde68a;'
            'border-radius:8px;padding:10px;color:#92400e;font-weight:600">'
            '💰 סומן: נדרשת הצעת מחיר ללקוח</p>'
        ) if quote_needed else ""
        return f"""<!DOCTYPE html><html><head>{_BASE_STYLE}<title>נסגר</title></head><body>
<div class="card success">
  <div class="emoji">🎉</div>
  <h1>הקריאה נסגרה!</h1>
  <p style="color:#555;margin-top:8px">תודה {name}, הדו"ח נשמר במערכת.</p>
  {quote_note}
</div></body></html>"""
    else:
        return f"""<!DOCTYPE html><html><head>{_BASE_STYLE}<title>נשמר</title></head><body>
<div class="card success">
  <div class="emoji">💾</div>
  <h1>הערה נשמרה</h1>
  <p style="color:#555;margin-top:8px">הקריאה נשארת פתוחה {name}.</p>
</div></body></html>"""
