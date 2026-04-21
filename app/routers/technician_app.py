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

    tech = db.query(Technician).filter(Technician.id == tid, Technician.is_active == True).first()  # noqa: E712
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
    """Main technician portal — 3-column layout: active call / maintenance / inspector reports."""
    import uuid
    from datetime import date, timedelta
    from app.models.elevator import Elevator
    from app.models.inspection_report import InspectionReport

    tech, assignment, call = _get_tech_and_call(db, tech_id)

    # ── Section 1: Active service call ────────────────────────────────────────
    call_html = ""
    if call:
        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        address = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"
        from app.utils.constants_server import FAULT_TYPE_HE, PRIORITY_HE
        fault = FAULT_TYPE_HE.get(call.fault_type, call.fault_type)
        priority = PRIORITY_HE.get(call.priority, call.priority)
        travel = f"~{assignment.travel_minutes} דק׳" if assignment.travel_minutes else "—"
        priority_class = "badge-red" if "קריטי" in priority else ("badge-orange" if "גבוה" in priority else "badge-blue")
        has_coords = bool(elevator and elevator.latitude and elevator.longitude)
        coords_label = f"({elevator.latitude:.5f}, {elevator.longitude:.5f})" if has_coords else "אין קואורדינטות"
        call_html = f"""
<div class="section-header">🔧 קריאת שירות פעילה</div>
<div class="card">
  <div class="row"><span class="label">📍 כתובת</span><span class="value">{address}</span></div>
  <div class="row"><span class="label">⚡ תקלה</span><span class="value">{fault}</span></div>
  <div class="row"><span class="label">⚠️ עדיפות</span><span class="badge {priority_class}">{priority}</span></div>
  <div class="row"><span class="label">👤 מתקשר</span><span class="value">{call.reported_by or '—'}</span></div>
  <div class="row"><span class="label">🚗 נסיעה</span><span class="value">{travel}</span></div>
  <div class="row"><span class="label">📌 GPS</span><span class="value" id="coords-label" style="font-size:.8rem;color:#888">{coords_label}</span></div>
  <button class="btn-location" id="loc-btn" onclick="saveLocation()">
    📍 שמור מיקום נוכחי על מפת המעלית
  </button>
</div>
<div class="card">
  <h2>דו"ח סיום טיפול</h2>
  <div class="textarea-wrap">
    <textarea id="notes" placeholder="תאר את הטיפול שבוצע, חלקים שהוחלפו וכו׳..."></textarea>
    <button type="button" class="mic-btn" id="mic-notes" onclick="startVoice('notes','mic-notes')">🎤 תמלול קולי</button>
  </div>
  <div class="checkbox-row" onclick="document.getElementById('quote').click()">
    <input type="checkbox" id="quote">
    <label for="quote">💰 נדרשת הצעת מחיר ללקוח</label>
  </div>
  <button class="btn btn-green" onclick="submitReport(true)">✅ סיימתי — סגור קריאה</button>
  <button class="btn btn-orange" onclick="submitReport(false)">🔧 עדיין בטיפול — שמור הערה</button>
</div>
<div class="card">
  <button class="btn btn-gray" onclick="toggleReassign()">🏢 כתובת שגויה? שייך מחדש</button>
  <div id="reassign-panel" style="display:none">
    <p style="color:#555;font-size:.9rem;margin-bottom:10px">חפש את הכתובת הנכונה לפי רחוב, עיר או שם בניין:</p>
    <input id="elev-q" class="search-input" type="text" placeholder="לדוגמה: הרצל תל אביב"
           oninput="if(this.value.length>=2) searchElevators()">
    <div id="elev-results"></div>
  </div>
</div>"""
    else:
        call_html = '<div class="card" style="text-align:center;color:#888;padding:30px">אין קריאות שירות פעילות</div>'

    # ── Section 2: Preventive maintenance ─────────────────────────────────────
    today = date.today()
    upcoming = (
        db.query(Elevator)
        .filter(
            Elevator.next_service_date.isnot(None),
            Elevator.next_service_date <= today + timedelta(days=15),
            Elevator.status == "ACTIVE",
        )
        .order_by(Elevator.next_service_date)
        .limit(20)
        .all()
    )

    if upcoming:
        maint_rows = ""
        for e in upcoming:
            days_left = (e.next_service_date - today).days
            if days_left <= 5:
                color = "#dc2626"; bg = "#fee2e2"; dot = "🔴"
            elif days_left <= 10:
                color = "#ea580c"; bg = "#ffedd5"; dot = "🟠"
            else:
                color = "#16a34a"; bg = "#f0fdf4"; dot = "🟢"
            maint_rows += (
                f'<div style="background:{bg};border-radius:8px;padding:10px 12px;margin-bottom:8px">'
                f'<div style="font-weight:600;color:{color}">{dot} {e.address}, {e.city}</div>'
                f'<div style="font-size:.85rem;color:#555;margin-top:3px">'
                f'טיפול בעוד {days_left} ימים · {e.next_service_date.strftime("%d/%m/%Y")}</div>'
                f'</div>'
            )
        maint_html = f'<div class="section-header">🛠️ טיפול מונע קרוב</div><div class="card">{maint_rows}</div>'
    else:
        maint_html = '<div class="section-header">🛠️ טיפול מונע קרוב</div><div class="card" style="text-align:center;color:#888;padding:20px">אין טיפולים קרובים ב-15 הימים הבאים</div>'

    # ── Section 3: Open inspection reports ────────────────────────────────────
    open_reports = (
        db.query(InspectionReport)
        .filter(InspectionReport.report_status.in_(["OPEN", "PARTIAL"]))
        .order_by(InspectionReport.processed_at.desc())
        .limit(10)
        .all()
    )

    if open_reports:
        report_rows = ""
        for r in open_reports:
            elev = db.query(Elevator).filter(Elevator.id == r.elevator_id).first() if r.elevator_id else None
            addr = f"{elev.address}, {elev.city}" if elev else (r.raw_address or "כתובת לא ידועה")
            count = r.deficiency_count or 0
            is_mine = str(getattr(r, 'assigned_technician_id', None)) == tech_id
            status_label = "בטיפולי 🔧" if is_mine else ("בטיפול אחר" if r.assigned_technician_id else "פנוי")
            bg = "#fffbeb" if is_mine else ("#f0fdf4" if not r.assigned_technician_id else "#f9fafb")
            claim_btn = (
                f'<button class="btn btn-green" style="margin-top:8px;padding:8px" '
                f'onclick="claimReport(\'{r.id}\')">'
                f'🙋 קח על עצמי</button>'
            ) if not r.assigned_technician_id else ""
            inspect_date = r.inspection_date.strftime("%d/%m/%Y") if r.inspection_date else "—"
            report_rows += (
                f'<div style="background:{bg};border-radius:8px;padding:12px;margin-bottom:10px;border:1px solid #e5e7eb">'
                f'<div style="font-weight:600">{addr}</div>'
                f'<div style="font-size:.85rem;color:#555;margin-top:3px">📅 {inspect_date} · ⚠️ {count} ליקויים · {status_label}</div>'
                f'{claim_btn}'
                f'</div>'
            )
        report_html = f'<div class="section-header">📋 דוחות בודק פתוחים</div><div class="card">{report_rows}</div>'
    else:
        report_html = '<div class="section-header">📋 דוחות בודק פתוחים</div><div class="card" style="text-align:center;color:#888;padding:20px">אין דוחות פתוחים לטיפול</div>'

    return HTMLResponse(_portal_page(
        tech_id=tech_id, tech_name=tech.name,
        call_html=call_html, maint_html=maint_html, report_html=report_html,
    ))


class ReportSubmit(BaseModel):
    notes: str
    resolved: bool = True
    quote_needed: bool = False


class ReassignElevator(BaseModel):
    elevator_id: str


class SaveLocation(BaseModel):
    lat: float
    lng: float


@router.get("/tech/{tech_id}/map-data", include_in_schema=False)
def tech_map_data(tech_id: str, db: Session = Depends(get_db)):
    """
    Return all geo-located work items for the technician's war-room map:
    - Open/active service calls (red)
    - Open inspection reports with deficiencies (orange)
    - Upcoming maintenance within 15 days (yellow/green by urgency)
    """
    import uuid
    from datetime import date, timedelta
    from app.models.technician import Technician
    from app.models.service_call import ServiceCall
    from app.models.assignment import Assignment
    from app.models.inspection_report import InspectionReport
    from app.models.elevator import Elevator

    try:
        tid = uuid.UUID(tech_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="לא נמצא")
    if not db.query(Technician).filter(Technician.id == tid).first():
        raise HTTPException(status_code=404, detail="טכנאי לא נמצא")

    pins = []
    today = date.today()
    _FAULT_HE = {"STUCK": "מעלית תקועה 🚨", "DOOR": "תקלת דלת", "ELECTRICAL": "חשמלית",
                 "MECHANICAL": "מכנית", "SOFTWARE": "תוכנה", "OTHER": "כללית"}
    _PRI_HE   = {"CRITICAL": "קריטי 🔴", "HIGH": "גבוה 🟠", "MEDIUM": "בינוני 🟡", "LOW": "נמוך 🟢"}

    # ── 1. Open service calls ─────────────────────────────────────────────────
    open_calls = (
        db.query(ServiceCall)
        .filter(ServiceCall.status.in_(["OPEN", "ASSIGNED", "IN_PROGRESS"]))
        .all()
    )
    for call in open_calls:
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if not elev or not elev.latitude or not elev.longitude:
            continue
        pri_color = {"CRITICAL": "#dc2626", "HIGH": "#ea580c"}.get(call.priority, "#eab308")
        pins.append({
            "type": "call",
            "lat": elev.latitude,
            "lng": elev.longitude,
            "address": f"{elev.address}, {elev.city}",
            "title": _FAULT_HE.get(call.fault_type, call.fault_type),
            "detail": _PRI_HE.get(call.priority, call.priority),
            "status": call.status,
            "color": pri_color,
            "call_id": str(call.id),
        })

    # ── 2. Open inspection reports ────────────────────────────────────────────
    open_reports = (
        db.query(InspectionReport)
        .filter(
            InspectionReport.report_status.in_(["OPEN", "PARTIAL"]),
            InspectionReport.elevator_id.isnot(None),
        )
        .all()
    )
    for rep in open_reports:
        elev = db.query(Elevator).filter(Elevator.id == rep.elevator_id).first()
        if not elev or not elev.latitude or not elev.longitude:
            continue
        days_pending = (today - rep.inspection_date).days if rep.inspection_date else 0
        color = "#dc2626" if days_pending >= 30 else ("#ea580c" if days_pending >= 14 else "#f97316")
        pins.append({
            "type": "inspection",
            "lat": elev.latitude,
            "lng": elev.longitude,
            "address": f"{elev.address}, {elev.city}",
            "title": f"⚠️ {rep.deficiency_count} ליקויים",
            "detail": f"תסקיר: {rep.inspection_date.strftime('%d/%m/%Y') if rep.inspection_date else '—'} · {days_pending} ימים",
            "color": color,
            "report_id": str(rep.id),
        })

    # ── 3. Upcoming maintenance ───────────────────────────────────────────────
    upcoming = (
        db.query(Elevator)
        .filter(
            Elevator.next_service_date.isnot(None),
            Elevator.next_service_date <= today + timedelta(days=15),
            Elevator.status == "ACTIVE",
            Elevator.latitude.isnot(None),
            Elevator.longitude.isnot(None),
        )
        .all()
    )
    for elev in upcoming:
        days_left = (elev.next_service_date - today).days
        color = "#dc2626" if days_left <= 0 else ("#ea580c" if days_left <= 5 else "#16a34a")
        label = f"בוצע לפני {abs(days_left)} ימים" if days_left < 0 else (f"עוד {days_left} ימים" if days_left > 0 else "היום!")
        pins.append({
            "type": "maintenance",
            "lat": elev.latitude,
            "lng": elev.longitude,
            "address": f"{elev.address}, {elev.city}",
            "title": f"🛠️ טיפול מונע",
            "detail": label,
            "color": color,
            "service_date": elev.next_service_date.strftime("%d/%m/%Y"),
        })

    return {"pins": pins}


@router.get("/tech/{tech_id}/elevators", include_in_schema=False)
def search_elevators(tech_id: str, q: str = "", db: Session = Depends(get_db)):
    """
    Return a JSON list of elevators matching the search query (address / city / building name).
    Used by the portal's reassign-address widget.
    """
    import uuid
    from app.models.elevator import Elevator
    from app.models.technician import Technician

    # Validate tech
    try:
        tid = uuid.UUID(tech_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="לא נמצא")
    if not db.query(Technician).filter(Technician.id == tid).first():
        raise HTTPException(status_code=404, detail="טכנאי לא נמצא")

    q = q.strip()
    if not q or len(q) < 2:
        return []

    elevators = (
        db.query(Elevator)
        .filter(
            Elevator.address.ilike(f"%{q}%")
            | Elevator.city.ilike(f"%{q}%")
            | Elevator.building_name.ilike(f"%{q}%")
        )
        .order_by(Elevator.city, Elevator.address)
        .limit(20)
        .all()
    )

    return [
        {
            "id": str(e.id),
            "address": e.address,
            "city": e.city,
            "building_name": e.building_name or "",
        }
        for e in elevators
    ]


@router.post("/tech/{tech_id}/reassign-elevator", response_class=HTMLResponse, include_in_schema=False)
def reassign_elevator(tech_id: str, data: ReassignElevator, db: Session = Depends(get_db)):
    """
    Reassign the technician's active call to a different elevator (correct address).
    Updates call.elevator_id, writes an audit log entry, and notifies the dispatcher.
    """
    import uuid
    from datetime import datetime, timezone
    from app.models.assignment import AuditLog
    from app.models.elevator import Elevator

    tech, assignment, call = _get_tech_and_call(db, tech_id)
    if not call:
        return HTMLResponse(_no_call_page(tech.name))

    try:
        new_elevator_id = uuid.UUID(data.elevator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="מזהה מעלית לא תקין")

    new_elevator = db.query(Elevator).filter(Elevator.id == new_elevator_id).first()
    if not new_elevator:
        raise HTTPException(status_code=404, detail="מעלית לא נמצאה")

    old_elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    old_addr = f"{old_elevator.address}, {old_elevator.city}" if old_elevator else "לא ידוע"
    new_addr = f"{new_elevator.address}, {new_elevator.city}"

    call.elevator_id = new_elevator.id

    audit = AuditLog(
        service_call_id=call.id,
        changed_by=tech.email or tech.name,
        old_status=call.status,
        new_status=call.status,
        notes=f"כתובת תוקנה מ-'{old_addr}' ל-'{new_addr}' ע\"י {tech.name}",
    )
    db.add(audit)
    db.commit()

    # Notify dispatcher
    try:
        from app.services.whatsapp_service import notify_dispatcher
        notify_dispatcher(
            f"📍 *תיקון כתובת*\n"
            f"טכנאי *{tech.name}* עדכן כתובת קריאה:\n"
            f"מ: {old_addr}\n"
            f"ל: *{new_addr}*"
        )
    except Exception:
        pass

    return HTMLResponse(_reassign_success_page(tech.name, old_addr, new_addr))


@router.post("/tech/{tech_id}/save-elevator-location", include_in_schema=False)
def save_elevator_location(tech_id: str, data: SaveLocation, db: Session = Depends(get_db)):
    """Save technician's current GPS to the elevator on their active call."""
    from app.models.elevator import Elevator
    from app.models.assignment import AuditLog

    tech, assignment, call = _get_tech_and_call(db, tech_id)
    if not call:
        return {"ok": False, "error": "אין קריאה פעילה"}

    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    if not elevator:
        return {"ok": False, "error": "מעלית לא נמצאה"}

    elevator.latitude = data.lat
    elevator.longitude = data.lng
    db.add(AuditLog(
        service_call_id=call.id,
        changed_by=tech.email or tech.name,
        old_status=call.status, new_status=call.status,
        notes=f"קואורדינטות GPS עודכנו ע\"י {tech.name}: {data.lat:.6f},{data.lng:.6f}",
    ))
    db.commit()

    try:
        from app.services.whatsapp_service import notify_dispatcher
        notify_dispatcher(
            f"📍 *מיקום מעלית עודכן* ע\"י {tech.name}\n"
            f"🏢 {elevator.address}, {elevator.city}\n"
            f"📌 {data.lat:.6f}, {data.lng:.6f}"
        )
    except Exception:
        pass

    return {"ok": True, "address": f"{elevator.address}, {elevator.city}"}


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


@router.post("/tech/{tech_id}/claim-report/{report_id}", include_in_schema=False)
def claim_report(tech_id: str, report_id: str, db: Session = Depends(get_db)):
    """Technician claims an open inspection report from the portal."""
    import uuid
    from app.models.inspection_report import InspectionReport
    from app.models.technician import Technician

    try:
        tid = uuid.UUID(tech_id)
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID לא תקין")

    tech = db.query(Technician).filter(Technician.id == tid).first()
    if not tech:
        raise HTTPException(status_code=404, detail="טכנאי לא נמצא")

    report = db.query(InspectionReport).filter(InspectionReport.id == rid).first()
    if not report:
        raise HTTPException(status_code=404, detail="דוח לא נמצא")

    report.assigned_technician_id = tid
    db.commit()
    return {"ok": True}


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
  .btn-gray { background: #e5e7eb; color: #374151; }
  .search-input { width: 100%; border: 1px solid #ddd; border-radius: 8px;
                  padding: 10px 12px; font-size: 1rem; direction: rtl; margin-bottom: 8px; }
  .elevator-item { display: block; width: 100%; text-align: right; padding: 10px 12px;
                   background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
                   margin-bottom: 6px; cursor: pointer; font-size: .95rem; }
  .elevator-item:active { background: #dbeafe; }
  #reassign-panel { margin-top: 12px; }
  .section-header { font-size: 1rem; font-weight: 700; color: #1a1a2e;
                    margin: 16px 0 6px; padding-right: 4px; }
  .tabs { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; }
  .tab-btn { padding: 8px 14px; border: none; border-radius: 20px; font-size: .9rem;
             font-weight: 600; cursor: pointer; white-space: nowrap; }
  .tab-active { background: #1a1a2e; color: white; }
  .tab-inactive { background: #e5e7eb; color: #374151; }
  .section { display: none; }
  .section.active { display: block; }
  .textarea-wrap { position: relative; margin-bottom: 12px; }
  .textarea-wrap textarea { margin-bottom: 0; }
  .mic-btn {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    width: 100%; padding: 10px; margin-top: 6px;
    border: 1px solid #d1d5db; border-radius: 8px;
    background: #f9fafb; color: #374151; font-size: .9rem; cursor: pointer;
  }
  .mic-btn.recording { background: #fee2e2; border-color: #fca5a5; color: #dc2626; animation: pulse 1s infinite; }
  .btn-location {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    background: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd;
    border-radius: 10px; padding: 12px; width: 100%; font-size: .95rem;
    font-weight: 700; cursor: pointer; margin-bottom: 10px;
  }
  .btn-location:active { opacity: .8; }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.5 } }
</style>
"""


def _portal_page(tech_id: str, tech_name: str, call_html: str, maint_html: str, report_html: str) -> str:
    return f"""<!DOCTYPE html><html>
<head>
{_BASE_STYLE}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<title>ממשק טכנאי</title>
</head><body>
<div class="card" style="margin-bottom:12px">
  <h1>שלום {tech_name} 👋</h1>
</div>
<div class="tabs">
  <button class="tab-btn tab-active"  onclick="showTab('calls',this)">🔧 קריאות</button>
  <button class="tab-btn tab-inactive" onclick="showTab('maint',this)">🛠️ תחזוקה</button>
  <button class="tab-btn tab-inactive" onclick="showTab('reports',this)">📋 בודק</button>
  <button class="tab-btn tab-inactive" onclick="showTab('warmap',this);setTimeout(initWarMap,100)">🗺️ חמ"ל</button>
</div>
<div id="calls"  class="section active">{call_html}</div>
<div id="maint"  class="section">{maint_html}</div>
<div id="reports" class="section">{report_html}</div>
<div id="warmap" class="section">
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
    <span style="background:#fee2e2;color:#dc2626;border-radius:20px;padding:4px 10px;font-size:.8rem;font-weight:700">🔴 קריאות פתוחות</span>
    <span style="background:#ffedd5;color:#ea580c;border-radius:20px;padding:4px 10px;font-size:.8rem;font-weight:700">🟠 ליקויי בודק</span>
    <span style="background:#f0fdf4;color:#16a34a;border-radius:20px;padding:4px 10px;font-size:.8rem;font-weight:700">🟢 טיפול מונע</span>
  </div>
  <div id="warmap-container" style="height:420px;border-radius:12px;overflow:hidden;margin-bottom:12px"></div>
  <div id="warmap-list"></div>
</div>
<script>
function showTab(id, btn) {{
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => {{ b.classList.remove('tab-active'); b.classList.add('tab-inactive'); }});
  document.getElementById(id).classList.add('active');
  btn.classList.remove('tab-inactive'); btn.classList.add('tab-active');
}}

function submitReport(resolved) {{
  const notes = document.getElementById('notes').value.trim();
  const quote_needed = document.getElementById('quote').checked;
  if (resolved && !notes) {{ alert('נא למלא תיאור הטיפול לפני סגירת הקריאה'); return; }}
  fetch('/app/tech/{tech_id}/report', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ notes: notes || '—', resolved, quote_needed }})
  }}).then(r => r.text()).then(html => {{ document.open(); document.write(html); document.close(); }})
    .catch(() => alert('שגיאה בשליחת הדו"ח, נסה שוב'));
}}

function toggleReassign() {{
  const p = document.getElementById('reassign-panel');
  p.style.display = p.style.display === 'none' ? 'block' : 'none';
  if (p.style.display === 'block') document.getElementById('elev-q').focus();
}}

let _searchTimer = null;
function searchElevators() {{
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => {{
    const q = document.getElementById('elev-q').value.trim();
    if (q.length < 2) return;
    fetch('/app/tech/{tech_id}/elevators?q=' + encodeURIComponent(q))
      .then(r => r.json())
      .then(items => {{
        const box = document.getElementById('elev-results');
        if (!items.length) {{ box.innerHTML = '<p style="color:#888;font-size:.9rem;padding:6px 0">לא נמצאו תוצאות</p>'; return; }}
        box.innerHTML = items.map(e => {{
          const label = e.building_name ? `${{e.address}}, ${{e.city}} (${{e.building_name}})` : `${{e.address}}, ${{e.city}}`;
          return `<button class="elevator-item" onclick="confirmReassign('${{e.id}}','${{label.replace(/'/g,"\\'")}}')"
                  >📍 ${{label}}</button>`;
        }}).join('');
      }}).catch(() => {{}});
  }}, 300);
}}

function confirmReassign(elevatorId, label) {{
  if (!confirm('לשייך את הקריאה לכתובת:\\n' + label + '?')) return;
  fetch('/app/tech/{tech_id}/reassign-elevator', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ elevator_id: elevatorId }})
  }}).then(r => r.text()).then(html => {{ document.open(); document.write(html); document.close(); }})
    .catch(() => alert('שגיאה בעדכון הכתובת, נסה שוב'));
}}

function claimReport(reportId) {{
  if (!confirm('לקחת על עצמך את הדוח לטיפול?')) return;
  fetch(`/app/tech/{tech_id}/claim-report/${{reportId}}`, {{ method: 'POST' }})
    .then(r => {{ if (r.ok) location.reload(); else alert('שגיאה בקבלת הדוח'); }})
    .catch(() => alert('שגיאה'));
}}

// ── War-room map ──────────────────────────────────────────────────────────────
let _warMap = null;
function initWarMap() {{
  if (_warMap) {{
    setTimeout(() => _warMap.invalidateSize(), 100);
    return;
  }}
  const container = document.getElementById('warmap-container');
  if ((container)._leaflet_id) delete container._leaflet_id;
  _warMap = L.map(container, {{ zoomControl: true }});
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap'
  }}).addTo(_warMap);
  _warMap.setView([32.08, 34.78], 9);
  setTimeout(() => _warMap.invalidateSize(), 250);

  fetch('/app/tech/{tech_id}/map-data')
    .then(r => r.json())
    .then(d => renderWarPins(d.pins))
    .catch(() => document.getElementById('warmap-list').innerHTML =
      '<p style="color:#888;text-align:center;padding:20px">שגיאה בטעינת נתונים</p>');

  // Show technician's own location if available
  if (navigator.geolocation) {{
    navigator.geolocation.getCurrentPosition(pos => {{
      const {{ latitude: lat, longitude: lng }} = pos.coords;
      const myIcon = L.divIcon({{
        className: '',
        html: '<div style="width:16px;height:16px;border-radius:50%;background:#2563eb;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,.5)"></div>',
        iconSize: [16,16], iconAnchor: [8,8],
      }});
      L.marker([lat, lng], {{ icon: myIcon }})
        .addTo(_warMap)
        .bindPopup('<b>📍 המיקום שלי</b>');
    }}, () => {{}});
  }}
}}

function renderWarPins(pins) {{
  const listEl = document.getElementById('warmap-list');
  const _TYPE_HE = {{ call: 'קריאה', inspection: 'דוח בודק', maintenance: 'טיפול מונע' }};
  const bounds = [];
  const byType = {{ call: [], inspection: [], maintenance: [] }};

  pins.forEach(p => {{
    if (!p.lat || !p.lng) return;
    const icon = L.divIcon({{
      className: '',
      html: `<div style="width:24px;height:24px;border-radius:50%;background:${{p.color}};border:3px solid white;
                         box-shadow:0 2px 6px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;
                         font-size:10px;color:white;font-weight:700"></div>`,
      iconSize: [24,24], iconAnchor: [12,12],
    }});
    const safeAddr = p.address.replace(/'/g, "\\'");
    const waze = p.lat && p.lng ? `https://waze.com/ul?ll=${{p.lat}},${{p.lng}}&navigate=yes` : '';
    L.marker([p.lat, p.lng], {{ icon }})
      .addTo(_warMap)
      .bindPopup(`
        <div style="direction:rtl;min-width:160px;font-family:sans-serif">
          <b>${{p.title}}</b><br>
          <small>📍 ${{p.address}}</small><br>
          <small>${{p.detail}}</small><br>
          ${{waze ? `<a href="${{waze}}" target="_blank" style="font-size:12px">🚘 Waze</a>` : ''}}
        </div>
      `);
    bounds.push([p.lat, p.lng]);
    (byType[p.type] || []).push(p);
  }});

  if (bounds.length > 0) _warMap.fitBounds(bounds, {{ padding: [40,40], maxZoom: 14 }});
  setTimeout(() => _warMap.invalidateSize(), 100);

  // Build summary list below map
  const _ICONS = {{ call: '🔴', inspection: '🟠', maintenance: '🟢' }};
  let html = '';
  ['call','inspection','maintenance'].forEach(type => {{
    const items = byType[type];
    if (!items.length) return;
    html += `<div style="font-weight:700;margin:12px 0 6px">${{_ICONS[type]}} ${{_TYPE_HE[type]}} (${{items.length}})</div>`;
    items.forEach(p => {{
      const waze = p.lat && p.lng ? `https://waze.com/ul?ll=${{p.lat}},${{p.lng}}&navigate=yes` : '';
      html += `
        <div style="background:white;border-radius:8px;padding:10px 12px;margin-bottom:8px;
                    box-shadow:0 1px 4px rgba(0,0,0,.08);border-right:4px solid ${{p.color}}">
          <div style="font-weight:600;font-size:.9rem">${{p.address}}</div>
          <div style="font-size:.8rem;color:#555;margin-top:2px">${{p.title}} · ${{p.detail}}</div>
          ${{waze ? `<a href="${{waze}}" target="_blank"
              style="font-size:.8rem;color:#1d4ed8;text-decoration:none;margin-top:4px;display:inline-block">
              🚘 נווט ב-Waze</a>` : ''}}
        </div>`;
    }});
  }});
  if (!html) html = '<p style="color:#888;text-align:center;padding:20px">אין פריטים עם קואורדינטות GPS</p>';
  listEl.innerHTML = html;
}}

function saveLocation() {{
  const btn = document.getElementById('loc-btn');
  if (!navigator.geolocation) {{ alert('GPS לא נתמך בדפדפן זה'); return; }}
  btn.textContent = '⏳ מאתר מיקום...';
  btn.disabled = true;
  navigator.geolocation.getCurrentPosition(
    pos => {{
      const {{ latitude, longitude, accuracy }} = pos.coords;
      fetch('/app/tech/{tech_id}/save-elevator-location', {{
        method: 'POST', headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{ lat: latitude, lng: longitude }})
      }})
      .then(r => r.json())
      .then(d => {{
        if (d.ok) {{
          btn.textContent = '✅ מיקום נשמר!';
          const cl = document.getElementById('coords-label');
          if (cl) cl.textContent = latitude.toFixed(5) + ', ' + longitude.toFixed(5) + ' (±' + Math.round(accuracy) + 'm)';
        }} else {{
          btn.textContent = '❌ ' + (d.error || 'שגיאה');
          btn.disabled = false;
        }}
      }})
      .catch(() => {{ btn.textContent = '❌ שגיאת רשת'; btn.disabled = false; }});
    }},
    err => {{
      btn.textContent = '📍 שמור מיקום נוכחי על מפת המעלית';
      btn.disabled = false;
      const msgs = {{ 1: 'הרשאת מיקום נדחתה', 2: 'מיקום לא זמין', 3: 'תם הזמן המוקצב' }};
      alert('לא ניתן לקבל מיקום: ' + (msgs[err.code] || err.message));
    }},
    {{ enableHighAccuracy: true, timeout: 15000 }}
  );
}}

const _activeRecognition = {{}};
function startVoice(targetId, btnId) {{
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {{ alert('תמלול קולי אינו נתמך בדפדפן זה.\nנסה Chrome או Safari עדכני.'); return; }}
  const btn = document.getElementById(btnId);
  if (_activeRecognition[targetId]) {{
    _activeRecognition[targetId].stop();
    return;
  }}
  const r = new SR();
  r.lang = 'he-IL';
  r.continuous = false;
  r.interimResults = false;
  r.maxAlternatives = 1;
  _activeRecognition[targetId] = r;
  btn.textContent = '🔴 מקליט... (לחץ לעצור)';
  btn.classList.add('recording');
  r.onresult = e => {{
    const transcript = e.results[0][0].transcript;
    const el = document.getElementById(targetId);
    el.value = el.value ? el.value + ' ' + transcript : transcript;
    el.focus();
  }};
  r.onerror = e => {{ if (e.error !== 'aborted') alert('שגיאת תמלול: ' + e.error); }};
  r.onend = () => {{
    delete _activeRecognition[targetId];
    btn.textContent = '🎤 תמלול קולי';
    btn.classList.remove('recording');
  }};
  r.start();
}}
</script>
</body></html>"""


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
  <div class="textarea-wrap">
    <textarea id="notes" placeholder="תאר את הטיפול שבוצע, חלקים שהוחלפו וכו׳..."></textarea>
    <button type="button" class="mic-btn" id="mic-notes" onclick="startVoice('notes','mic-notes')">🎤 תמלול קולי</button>
  </div>
  <div class="checkbox-row" onclick="document.getElementById('quote').click()">
    <input type="checkbox" id="quote">
    <label for="quote">💰 נדרשת הצעת מחיר ללקוח</label>
  </div>
  <button class="btn btn-green" onclick="submitReport(true)">✅ סיימתי — סגור קריאה</button>
  <button class="btn btn-orange" onclick="submitReport(false)">🔧 עדיין בטיפול — שמור הערה</button>
</div>
<div class="card">
  <button class="btn btn-gray" onclick="toggleReassign()">🏢 כתובת שגויה? שייך מחדש</button>
  <div id="reassign-panel" style="display:none">
    <p style="color:#555;font-size:.9rem;margin-bottom:10px">
      חפש את הכתובת הנכונה לפי רחוב, עיר או שם בניין:
    </p>
    <input id="elev-q" class="search-input" type="text"
           placeholder="לדוגמה: הרצל תל אביב"
           oninput="if(this.value.length>=2) searchElevators()">
    <div id="elev-results"></div>
  </div>
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

const _activeRecognition = {{}};
function startVoice(targetId, btnId) {{
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {{ alert('תמלול קולי אינו נתמך בדפדפן זה.\nנסה Chrome או Safari עדכני.'); return; }}
  const btn = document.getElementById(btnId);
  if (_activeRecognition[targetId]) {{ _activeRecognition[targetId].stop(); return; }}
  const r = new SR();
  r.lang = 'he-IL'; r.continuous = false; r.interimResults = false; r.maxAlternatives = 1;
  _activeRecognition[targetId] = r;
  btn.textContent = '🔴 מקליט... (לחץ לעצור)'; btn.classList.add('recording');
  r.onresult = e => {{
    const t = e.results[0][0].transcript;
    const el = document.getElementById(targetId);
    el.value = el.value ? el.value + ' ' + t : t;
    el.focus();
  }};
  r.onerror = e => {{ if (e.error !== 'aborted') alert('שגיאת תמלול: ' + e.error); }};
  r.onend = () => {{
    delete _activeRecognition[targetId];
    btn.textContent = '🎤 תמלול קולי'; btn.classList.remove('recording');
  }};
  r.start();
}}

function toggleReassign() {{
  const p = document.getElementById('reassign-panel');
  p.style.display = p.style.display === 'none' ? 'block' : 'none';
  if (p.style.display === 'block') document.getElementById('elev-q').focus();
}}

let _searchTimer = null;
function searchElevators() {{
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => {{
    const q = document.getElementById('elev-q').value.trim();
    if (q.length < 2) return;
    fetch('/app/tech/{tech_id}/elevators?q=' + encodeURIComponent(q))
      .then(r => r.json())
      .then(items => {{
        const box = document.getElementById('elev-results');
        if (!items.length) {{
          box.innerHTML = '<p style="color:#888;font-size:.9rem;padding:6px 0">לא נמצאו תוצאות</p>';
          return;
        }}
        box.innerHTML = items.map(e => {{
          const label = e.building_name
            ? `${{e.address}}, ${{e.city}} (${{e.building_name}})`
            : `${{e.address}}, ${{e.city}}`;
          return `<button class="elevator-item"
                    onclick="confirmReassign('${{e.id}}','${{label.replace(/'/g,"\\'")}}')"
                  >📍 ${{label}}</button>`;
        }}).join('');
      }})
      .catch(() => {{}});
  }}, 300);
}}

function confirmReassign(elevatorId, label) {{
  if (!confirm('לשייך את הקריאה לכתובת:\\n' + label + '?')) return;
  fetch('/app/tech/{tech_id}/reassign-elevator', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ elevator_id: elevatorId }})
  }}).then(r => r.text()).then(html => {{
    document.open(); document.write(html); document.close();
  }}).catch(() => alert('שגיאה בעדכון הכתובת, נסה שוב'));
}}
</script>
</body></html>"""


def _reassign_success_page(name: str, old_addr: str, new_addr: str):
    return f"""<!DOCTYPE html><html><head>{_BASE_STYLE}<title>כתובת עודכנה</title></head><body>
<div class="card success">
  <div class="emoji">📍</div>
  <h1>הכתובת עודכנה!</h1>
  <p style="color:#555;margin-top:8px">הקריאה שויכה מחדש:</p>
  <p style="color:#888;font-size:.9rem;margin-top:6px;text-decoration:line-through">{old_addr}</p>
  <p style="color:#16a34a;font-weight:700;margin-top:4px">{new_addr}</p>
  <p style="color:#555;font-size:.9rem;margin-top:12px">המוקד קיבל עדכון על השינוי.</p>
</div></body></html>"""


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
