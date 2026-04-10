"""Webhook endpoints for external integrations (Make.com, telephony providers, Green API)."""

import base64
import html as html_lib
import json
import logging
import re
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


def _clean_html(text: str) -> str:
    """Strip HTML tags and decode entities from email body."""
    # Replace block-level tags with newlines so fields stay on separate lines
    text = re.sub(r"</?(p|br|div|li|tr|td|th)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities (&amp; &#39; &nbsp; etc.)
    text = html_lib.unescape(text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
    email_body = _clean_html(_extract_email_body(raw, content_type))

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
    Green API pushes every WhatsApp message here.
    Handles: assignment confirmation (natural language or 1/2), location updates, free-text queries.
    """
    webhook_type = payload.typeWebhook

    # Accept both incoming (regular) and outgoing (self-send: instance phone == technician phone)
    if webhook_type not in ("incomingMessageReceived", "outgoingMessageReceived"):
        return {"status": "ignored"}

    sender_data = payload.senderData
    msg_data    = payload.messageData
    msg_type    = msg_data.get("typeMessage", "")

    # For outgoing (self-send), use chatId as the phone; for incoming use sender
    if webhook_type == "outgoingMessageReceived":
        phone = sender_data.get("chatId", "").replace("@c.us", "")
    else:
        phone = sender_data.get("sender", "").replace("@c.us", "").replace("@s.whatsapp.net", "")

    if not phone:
        return {"status": "empty"}

    # ── Location message ──────────────────────────────────────────────────────
    if msg_type in ("locationMessage", "liveLocationMessage"):
        loc = msg_data.get("locationMessageData") or msg_data.get("liveLocationMessageData", {})
        lat, lng = loc.get("latitude"), loc.get("longitude")
        if lat is not None and lng is not None:
            tech = _find_tech_by_phone_local(db, phone)
            if tech:
                tech.current_latitude  = float(lat)
                tech.current_longitude = float(lng)
                db.commit()
                logger.info("📍 Location updated for %s", tech.name)
                return {"status": "location_updated"}
        return {"status": "location_empty"}

    # ── Voice message — transcribe with Gemini ───────────────────────────────
    if msg_type == "audioMessage":
        text = _transcribe_audio_gemini(msg_data)
        if not text:
            return {"status": "audio_transcription_failed"}
        logger.info("🎤 Voice from %s transcribed: %s", phone, text)
    # ── Text message ──────────────────────────────────────────────────────────
    elif msg_type == "extendedTextMessage":
        text = msg_data.get("extendedTextMessageData", {}).get("text", "").strip()
    else:
        text = msg_data.get("textMessageData", {}).get("textMessage", "").strip()

    if not text:
        return {"status": "empty_text"}

    # For outgoing self-send: skip echo of system messages (long messages we sent)
    if webhook_type == "outgoingMessageReceived" and len(text) > 30:
        return {"status": "ignored_outgoing_echo"}

    logger.info("📩 WhatsApp from %s: %r", phone, text)

    # ── Route: pending assignment reply or free-text ──────────────────────────
    pending = ai_assignment_agent.get_pending_assignments_for_phone(db, phone)
    if pending:
        from app.services.scheduler import _handle_tech_reply
        _handle_tech_reply(db, phone, text, pending, settings)
        return {"status": "processed"}

    # Free-text: report / question / self-assign
    from app.services.scheduler import _handle_free_text
    _handle_free_text(db, phone, text, settings)
    return {"status": "processed"}


# ── Private helpers ──────────────────────────────────────────────────────────

def _transcribe_audio_gemini(msg_data: dict) -> str:
    """
    Download voice message from Green API and transcribe it via Gemini.

    Green API puts the download URL inside fileMessageData.downloadUrl.
    We fetch the audio bytes, base64-encode them, and send them to
    Gemini as inline audio data with a Hebrew transcription prompt.
    """
    import httpx

    file_data = msg_data.get("fileMessageData") or {}
    download_url = file_data.get("downloadUrl", "")
    mime_type = file_data.get("mimeType", "audio/ogg; codecs=opus")
    # Gemini wants a clean mime type (no codec suffix)
    clean_mime = mime_type.split(";")[0].strip() or "audio/ogg"

    if not download_url:
        logger.warning("_transcribe_audio_gemini: no downloadUrl in msg_data")
        return ""

    api_key = settings.gemini_api_key
    if not api_key:
        logger.warning("_transcribe_audio_gemini: no gemini_api_key configured")
        return ""

    # 1. Download the audio file
    try:
        with httpx.Client(timeout=30) as client:
            audio_resp = client.get(download_url)
            audio_resp.raise_for_status()
            audio_bytes = audio_resp.content
    except Exception as exc:
        logger.error("_transcribe_audio_gemini: download failed: %s", exc)
        return ""

    # 2. Base64-encode
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    # 3. Send to Gemini with inline audio data
    gemini_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": clean_mime,
                            "data": audio_b64,
                        }
                    },
                    {
                        "text": (
                            "תמלל את הודעת הקול הזו לעברית בדיוק כפי שנאמרה. "
                            "החזר רק את הטקסט המתומלל, ללא הסברים נוספים."
                        )
                    },
                ]
            }
        ],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.0},
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(gemini_url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            text = (
                result.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
            return text
    except Exception as exc:
        logger.error("_transcribe_audio_gemini: Gemini call failed: %s", exc)
        return ""


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
