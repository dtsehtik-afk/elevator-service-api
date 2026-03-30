"""Webhook endpoints for external integrations (Make.com, telephony providers, Green API)."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.incoming_call import IncomingCallLog
from app.schemas.service_call import ServiceCallCreate
from app.services import service_call_service
from app.services import ai_assignment_agent
from app.services.call_parser import enrich_elevator, find_elevator, parse_email
from app.services import whatsapp_service

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _extract_email_body(raw_bytes: bytes, content_type: str) -> str:
    """
    Robustly extract the email body from a webhook request.

    Make.com may send the payload in several ways:
    1. Proper JSON:        {"email_body": "line1\\nline2"}
    2. Malformed JSON:     {"email_body": "line1\nline2"}  ← actual newlines inside JSON string
    3. Plain text:         the raw email body with no wrapper
    4. Form-encoded:       email_body=...

    We try each in order and fall back to raw UTF-8 text.
    """
    text = raw_bytes.decode("utf-8", errors="replace")

    # 1. Try strict JSON parse
    if "application/json" in content_type or text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "email_body" in data:
                return data["email_body"]
        except json.JSONDecodeError:
            pass

        # 2. Malformed JSON — newlines inside string aren't escaped.
        #    Replace bare newlines inside the value with \\n, then retry.
        try:
            # Replace literal newlines inside JSON string values
            fixed = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
            data = json.loads(fixed)
            if isinstance(data, dict) and "email_body" in data:
                # Restore actual newlines in the extracted value
                return data["email_body"].replace("\\n", "\n")
        except (json.JSONDecodeError, Exception):
            pass

    # 3. Form-encoded: email_body=...
    if "application/x-www-form-urlencoded" in content_type:
        from urllib.parse import parse_qs, unquote_plus
        try:
            parsed = parse_qs(text)
            if "email_body" in parsed:
                return parsed["email_body"][0]
        except Exception:
            pass

    # 4. Fallback — treat entire body as the email text
    return text


# ── Schemas ───────────────────────────────────────────────────────────────────

class IncomingCallRequest(BaseModel):
    """Payload sent by Make.com — raw email body."""
    email_body: str


class IncomingCallResponse(BaseModel):
    log_id: str
    match_status: str
    match_score: Optional[float]
    match_notes: str
    service_call_id: Optional[str]
    assigned_technician: Optional[str]
    travel_minutes: Optional[int]
    elevator_id: Optional[str]
    elevator_address: Optional[str]
    parsed_name: str
    parsed_phone: str
    parsed_city: str
    parsed_street: str
    priority: str
    fault_type: str
    enriched: bool


class WhatsAppWebhookPayload(BaseModel):
    """Incoming message from Green API webhook."""
    typeWebhook: str = ""
    senderData: dict = {}
    messageData: dict = {}


# ── Security ──────────────────────────────────────────────────────────────────

def _verify_secret(x_webhook_secret: Optional[str] = Header(default=None)):
    configured = settings.webhook_secret
    if configured and x_webhook_secret and x_webhook_secret != configured:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid webhook secret")


# ── Incoming call from telephony provider ─────────────────────────────────────

@router.post(
    "/call",
    response_model=IncomingCallResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive incoming service call from telephony provider",
)
async def receive_call(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_secret),
):
    """
    Full pipeline:
    1. Parse email → extract caller, address, fault type, priority
    2. Fuzzy-match elevator in DB
    3. Enrich elevator with any new info
    4. Create service call (if MATCHED)
    5. AI agent: rank technicians → send WhatsApp → create PENDING_CONFIRMATION assignment
    6. Log everything

    Accepts:
    - application/json   { "email_body": "..." }
    - text/plain         raw email body
    - malformed JSON     with unescaped newlines (Make.com quirk)
    """
    raw = await request.body()
    content_type = request.headers.get("content-type", "")
    email_body = _extract_email_body(raw, content_type)

    logger.debug("Webhook /call received body (%d chars)", len(email_body))

    # 1. Parse
    parsed = parse_email(email_body)

    # 2. Match elevator
    match = find_elevator(db, parsed)

    # 3. Enrich elevator
    enriched = False
    if match.elevator:
        enriched = enrich_elevator(db, match.elevator, parsed)

    # 4. Create service call
    service_call = None
    if match.match_status == "MATCHED" and match.elevator:
        call_data = ServiceCallCreate(
            elevator_id=match.elevator.id,
            reported_by=parsed.name or parsed.phone or "מוקד טלפוני",
            description=parsed.description,
            priority=parsed.priority,
            fault_type=parsed.fault_type,
        )
        service_call = service_call_service.create_service_call(
            db, call_data, "webhook@system"
        )

    # 5. AI assignment — recommend technician + send WhatsApp
    assignment = None
    if service_call:
        try:
            assignment = ai_assignment_agent.assign_with_confirmation(db, service_call)
        except Exception as exc:
            logger.error("AI assignment failed: %s", exc)

    # If no technician found — notify dispatcher
    if service_call and not assignment:
        dispatcher = settings.dispatcher_whatsapp
        if dispatcher and match.elevator:
            whatsapp_service.notify_dispatcher_unassigned(
                dispatcher,
                match.elevator.address,
                match.elevator.city,
                parsed.fault_type,
            )

    # 6. Log
    log = IncomingCallLog(
        raw_text=email_body,
        caller_name=parsed.name or None,
        caller_phone=parsed.phone or None,
        call_city=parsed.city or None,
        call_street=parsed.street or None,
        call_type=parsed.call_type or None,
        call_time_raw=parsed.call_time or None,
        fault_type=parsed.fault_type,
        priority=parsed.priority,
        match_status=match.match_status,
        match_score=match.score,
        match_notes=match.match_notes,
        elevator_id=match.elevator.id if match.elevator else None,
        service_call_id=service_call.id if service_call else None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Resolve assigned technician name for the response
    assigned_name = None
    travel_mins   = None
    if assignment:
        from app.models.technician import Technician
        tech = db.query(Technician).filter(Technician.id == assignment.technician_id).first()
        assigned_name = tech.name if tech else None
        travel_mins   = assignment.travel_minutes

    return IncomingCallResponse(
        log_id=str(log.id),
        match_status=match.match_status,
        match_score=match.score,
        match_notes=match.match_notes,
        service_call_id=str(service_call.id) if service_call else None,
        assigned_technician=assigned_name,
        travel_minutes=travel_mins,
        elevator_id=str(match.elevator.id) if match.elevator else None,
        elevator_address=(
            f"{match.elevator.address}, {match.elevator.city}" if match.elevator else None
        ),
        parsed_name=parsed.name,
        parsed_phone=parsed.phone,
        parsed_city=parsed.city,
        parsed_street=parsed.street,
        priority=parsed.priority,
        fault_type=parsed.fault_type,
        enriched=enriched,
    )


# ── WhatsApp reply from technician (Green API webhook) ────────────────────────

@router.post(
    "/whatsapp",
    status_code=status.HTTP_200_OK,
    summary="Receive WhatsApp reply from technician (Green API webhook)",
)
def receive_whatsapp(
    payload: WhatsAppWebhookPayload,
    db: Session = Depends(get_db),
):
    """
    Green API calls this endpoint when a technician sends a WhatsApp reply.
    "1" → confirm assignment
    "2" → reject (try next technician)
    """
    if payload.typeWebhook != "incomingMessageReceived":
        return {"status": "ignored"}

    sender   = payload.senderData.get("sender", "")   # "972521234567@c.us"
    msg_data = payload.messageData
    msg_type = msg_data.get("typeMessage", "")
    phone    = sender.replace("@c.us", "")

    if not sender:
        return {"status": "empty"}

    # ── Location message (live or static) ────────────────────────────────────
    if msg_type in ("locationMessage", "liveLocationMessage"):
        loc = msg_data.get("locationMessageData") or msg_data.get("liveLocationMessageData", {})
        lat = loc.get("latitude")
        lng = loc.get("longitude")

        if lat is not None and lng is not None:
            from app.models.technician import Technician as TechModel
            tech = _find_tech_by_phone_local(db, phone)
            if tech:
                tech.current_latitude  = float(lat)
                tech.current_longitude = float(lng)
                db.commit()
                logger.info("📍 Location updated for %s: %.5f, %.5f", tech.name, lat, lng)
                return {"status": "location_updated", "name": tech.name, "lat": lat, "lng": lng}
            else:
                logger.warning("Location received from unknown phone: %s", phone)
                return {"status": "unknown_technician"}

        return {"status": "location_empty"}

    # ── Text message — assignment confirmation ────────────────────────────────
    text = msg_data.get("textMessageData", {}).get("textMessage", "").strip()

    if text == "1":
        assignment = ai_assignment_agent.confirm_assignment(db, phone)
        if assignment:
            logger.info("✅ Technician %s confirmed assignment %s", phone, assignment.id)
            return {"status": "confirmed", "assignment_id": str(assignment.id)}
        return {"status": "no_pending_assignment"}

    elif text == "2":
        assignment = ai_assignment_agent.reject_assignment(db, phone)
        if assignment:
            logger.info("❌ Technician %s rejected assignment %s", phone, assignment.id)
            return {"status": "rejected", "assignment_id": str(assignment.id)}
        return {"status": "no_pending_assignment"}

    return {"status": "ignored", "received": text}


# ── Private helper ───────────────────────────────────────────────────────────

def _find_tech_by_phone_local(db, phone: str):
    """Find technician by last 9 digits of phone number."""
    from app.models.technician import Technician as TechModel
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    last9 = digits[-9:]
    return (
        db.query(TechModel)
        .filter(
            (TechModel.phone.contains(last9)) |
            (TechModel.whatsapp_number.contains(last9))
        )
        .first()
    )


# ── Technician GPS location update ───────────────────────────────────────────

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float


@router.post(
    "/location/{technician_id}",
    status_code=status.HTTP_200_OK,
    summary="Update technician GPS location (called from mobile)",
)
def update_location(
    technician_id: str,
    payload: LocationUpdate,
    db: Session = Depends(get_db),
):
    """Called from the technician's phone to update their live GPS position."""
    from app.models.technician import Technician
    import uuid as _uuid
    tech = db.query(Technician).filter(
        Technician.id == _uuid.UUID(technician_id)
    ).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    tech.current_latitude  = payload.latitude
    tech.current_longitude = payload.longitude
    db.commit()
    return {"status": "ok", "name": tech.name}


# ── Manual trigger: morning location request ─────────────────────────────────

@router.post(
    "/trigger/morning",
    status_code=status.HTTP_200_OK,
    summary="Manually trigger morning location request to all technicians",
)
def trigger_morning_message(
    _: None = Depends(_verify_secret),
):
    """
    Sends the morning 'please share your location' WhatsApp to all active technicians.
    Normally runs automatically at 07:15 — this endpoint lets you trigger it manually.
    """
    from app.services.scheduler import _send_morning_location_requests
    _send_morning_location_requests()
    return {"status": "sent"}


# ── Incoming call log ─────────────────────────────────────────────────────────

@router.get("/calls/log", summary="List all incoming call logs")
def list_call_logs(
    match_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(IncomingCallLog).order_by(IncomingCallLog.created_at.desc())
    if match_status:
        query = query.filter(IncomingCallLog.match_status == match_status)
    return query.offset(skip).limit(limit).all()
