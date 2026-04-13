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

    # 3b. Save caller phone to elevator for future matching (if not already saved)
    if match.match_status == "MATCHED" and match.elevator and parsed.phone:
        _save_caller_phone(match.elevator, parsed.phone, db)

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
        logger.warning("🔔 Webhook ignored: type=%s", webhook_type)
        return {"status": "ignored"}

    sender_data = payload.senderData
    msg_data    = payload.messageData
    msg_type    = msg_data.get("typeMessage", "")

    # For outgoing messages: only process self-messages (Denis texting himself).
    # When chatId == sender it's a self-message (saved messages / own chat).
    # When chatId != sender it's a system echo sent TO a technician — ignore.
    if webhook_type == "outgoingMessageReceived":
        chat_id = sender_data.get("chatId", "")
        sender  = sender_data.get("sender", "")
        if chat_id != sender:
            logger.warning("🔕 Outgoing echo to %s — ignored", chat_id)
            return {"status": "ignored_outgoing_echo"}
        # Self-message: Denis writing to himself → use his own number
        phone = chat_id.replace("@c.us", "").replace("@s.whatsapp.net", "")
    else:
        phone = sender_data.get("sender", "").replace("@c.us", "").replace("@s.whatsapp.net", "")

    logger.warning("🔔 phone=%s  msg_type=%s  direction=%s", phone, msg_type, webhook_type)

    if not phone:
        return {"status": "empty"}

    # ── Location message ──────────────────────────────────────────────────────
    if msg_type in ("locationMessage", "liveLocationMessage"):
        loc = (
            msg_data.get("locationMessageData")
            or msg_data.get("liveLocationMessageData")
            or {}
        )
        lat, lng = loc.get("latitude"), loc.get("longitude")
        logger.warning("📍 Location msg from %s | type=%s | lat=%s lng=%s | raw_loc=%s",
                       phone, msg_type, lat, lng, loc)
        if lat is not None and lng is not None:
            tech = _find_tech_by_phone_local(db, phone)
            if tech:
                tech.current_latitude  = float(lat)
                tech.current_longitude = float(lng)
                db.commit()
                logger.warning("📍 Location saved for %s: %.4f, %.4f", tech.name, float(lat), float(lng))
                from app.services.whatsapp_service import _send_message
                _send_message(phone, f"📍 המיקום שלך התעדכן בהצלחה, {tech.name}.")
                return {"status": "location_updated"}
            else:
                logger.warning("📍 Location received but no tech found for phone=%s", phone)
        else:
            logger.warning("📍 Location msg with no coordinates from %s | full msg_data=%s", phone, msg_data)
        return {"status": "location_empty"}

    # ── Voice message — transcribe with Gemini ───────────────────────────────
    # Only transcribe for registered system users — skip unknown numbers silently
    is_voice = False
    if msg_type == "audioMessage":
        known_sender = _find_tech_by_phone_local(db, phone)
        if not known_sender:
            logger.warning("🎤 Audio from unregistered %s — skipping transcription", phone)
            return {"status": "ignored_unknown_audio"}
        transcribed_text = _transcribe_audio_gemini(msg_data)
        if not transcribed_text:
            from app.services.whatsapp_service import _send_message
            _send_message(phone, "⚠️ לא הצלחתי לתמלל את ההודעה הקולית. אנא שלח הודעת טקסט.")
            _log_message(db, phone, "in", msg_type, None, None)
            return {"status": "audio_transcription_failed"}
        is_voice = True
        text = transcribed_text
        logger.info("🎤 Voice from %s transcribed: %s", phone, text)
        _log_message(db, phone, "in", msg_type, None, transcription=text)
    # ── Text message ──────────────────────────────────────────────────────────
    elif msg_type in ("extendedTextMessage", "quotedMessage"):
        text = msg_data.get("extendedTextMessageData", {}).get("text", "").strip()
    else:
        text = msg_data.get("textMessageData", {}).get("textMessage", "").strip()

    if not text:
        return {"status": "empty_text"}

    # Log non-voice incoming messages
    if not is_voice:
        _log_message(db, phone, "in", msg_type, text)

    # Self-messages (outgoing where chatId==sender) reach here — process normally

    logger.info("📩 WhatsApp from %s: %r", phone, text)

    # For voice messages — echo the transcription back so the tech knows what was understood
    if is_voice:
        from app.services.whatsapp_service import _send_message
        _send_message(phone, f"🎤 *שמעתי:* \"{text}\"")

    # ── Route: pending assignment reply or free-text ──────────────────────────
    pending = ai_assignment_agent.get_pending_assignments_for_phone(db, phone)
    if pending:
        from app.services.scheduler import _handle_tech_reply
        _handle_tech_reply(db, phone, text, pending, settings)
        return {"status": "processed"}

    # Free-text: report / question / self-assign
    # Pass is_reply=True for quoted messages so the chat agent loads conversation history
    from app.services.scheduler import _handle_free_text
    _handle_free_text(db, phone, text, settings, is_reply=(msg_type == "quotedMessage"))
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


def _log_message(db, phone: str, direction: str, msg_type: str, text: str | None, transcription: str | None = None):
    try:
        from app.models.whatsapp_message import WhatsAppMessage
        entry = WhatsAppMessage(phone=phone, direction=direction, msg_type=msg_type, text=text, transcription=transcription)
        db.add(entry)
        db.commit()
    except Exception as exc:
        logger.error("Failed to log WhatsApp message: %s", exc)


def _save_caller_phone(elevator, phone: str, db) -> None:
    """Add caller phone to elevator.caller_phones if not already present."""
    try:
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("972"):
            digits = "0" + digits[3:]
        normalized = digits[-10:] if len(digits) >= 10 else digits
        if not normalized:
            return
        existing = list(elevator.caller_phones or [])
        # Check if already saved (last-9 match)
        for p in existing:
            p_digits = "".join(c for c in p if c.isdigit())
            if p_digits[-9:] == normalized[-9:]:
                return  # already exists
        existing.append(normalized)
        elevator.caller_phones = existing
        db.commit()
        logger.warning("📞 Saved caller phone %s to elevator %s", normalized, elevator.id)
    except Exception as exc:
        logger.error("Failed to save caller phone: %s", exc)


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


@router.get(
    "/track/{tech_id}",
    summary="Live location tracking page for technician (opens in mobile browser)",
)
def location_tracking_page(tech_id: str):
    """
    Serve a simple mobile HTML page that streams the technician's GPS to the server.
    The technician opens this link on their phone and allows location access.
    """
    from fastapi.responses import HTMLResponse
    base_url = settings.app_base_url
    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>מיקום חי — אקורד מעליות</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; background: #f0f4f8; min-height: 100vh;
          display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px; }}
  h1 {{ font-size: 26px; color: #1a1a2e; margin-bottom: 4px; }}
  h2 {{ font-size: 15px; color: #666; margin-bottom: 24px; font-weight: normal; }}
  .card {{ background: white; border-radius: 16px; padding: 24px 20px;
           width: 100%; max-width: 340px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); text-align: center; }}
  .dot {{ display: inline-block; width: 14px; height: 14px; border-radius: 50%;
          margin-left: 8px; vertical-align: middle; }}
  .dot.green {{ background: #22c55e; animation: pulse 1.5s infinite; }}
  .dot.yellow {{ background: #f59e0b; animation: pulse 1.5s infinite; }}
  .dot.red {{ background: #ef4444; }}
  @keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.3; }} }}
  .status-text {{ font-size: 17px; font-weight: bold; margin: 14px 0 6px; }}
  .sub-text {{ font-size: 13px; color: #666; line-height: 1.7; }}
  .time {{ font-size: 12px; color: #999; margin-top: 10px; }}
  .logo {{ font-size: 44px; margin-bottom: 6px; }}
  .btn {{ display: inline-block; margin-top: 16px; padding: 10px 24px;
          background: #3b82f6; color: white; border: none; border-radius: 10px;
          font-size: 15px; cursor: pointer; width: 100%; }}
  .btn:active {{ background: #2563eb; }}
  .steps {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px;
            padding: 12px 14px; margin-top: 14px; text-align: right; font-size: 12px;
            color: #92400e; line-height: 1.9; display: none; }}
</style>
</head>
<body>
<div class="logo">📍</div>
<h1>מיקום חי</h1>
<h2>אקורד מעליות</h2>
<div class="card">
  <div id="dot" class="dot yellow"></div>
  <div id="status" class="status-text">ממתין לאישור מיקום…</div>
  <div id="sub" class="sub-text">אנא אפשר גישה למיקום כאשר הדפדפן ישאל</div>
  <div id="time" class="time"></div>
  <button id="retryBtn" class="btn" onclick="grab()" style="display:none">🔄 נסה שוב</button>
  <div id="steps" class="steps"></div>
</div>
<p style="margin-top:18px;font-size:11px;color:#bbb;text-align:center;">השאר דף זה פתוח — המיקום מתעדכן כל 5 דקות</p>
<script>
const TECH_ID = "{tech_id}";
const BASE_URL = "{base_url}";
const INTERVAL_MS = 5 * 60 * 1000;
let timer = null;

function setStatus(type, msg, sub) {{
  document.getElementById('dot').className = 'dot ' + type;
  document.getElementById('status').textContent = msg;
  if (sub !== undefined) document.getElementById('sub').textContent = sub;
}}

function showRetry(stepsHtml) {{
  document.getElementById('retryBtn').style.display = 'block';
  const el = document.getElementById('steps');
  if (stepsHtml) {{ el.innerHTML = stepsHtml; el.style.display = 'block'; }}
}}

function hideRetry() {{
  document.getElementById('retryBtn').style.display = 'none';
  document.getElementById('steps').style.display = 'none';
}}

function sendLocation(lat, lng) {{
  fetch(BASE_URL + '/webhooks/location/' + TECH_ID, {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{latitude: lat, longitude: lng}})
  }}).then(r => {{
    if (r.ok) {{
      const t = new Date().toLocaleTimeString('he-IL', {{hour:'2-digit', minute:'2-digit'}});
      setStatus('green', '✅ מיקום פעיל', 'מתעדכן כל 5 דקות');
      document.getElementById('time').textContent = 'עדכון אחרון: ' + t;
      hideRetry();
    }} else {{
      setStatus('red', '⚠️ שגיאת שרת', 'מנסה שוב בקרוב…');
    }}
  }}).catch(() => setStatus('red', '⚠️ אין חיבור לשרת', 'בדוק חיבור לאינטרנט'));
}}

function grab() {{
  setStatus('yellow', 'מאתר מיקום…', '');
  hideRetry();
  navigator.geolocation.getCurrentPosition(
    p => sendLocation(p.coords.latitude, p.coords.longitude),
    e => {{
      if (e.code === 1) {{
        // PERMISSION_DENIED
        const isChrome = /Chrome/.test(navigator.userAgent) && !/Edg/.test(navigator.userAgent);
        const isInsecure = location.protocol !== 'https:';
        if (isInsecure && isChrome) {{
          setStatus('red', '🔒 נדרש HTTPS', '');
          showRetry(`<b>Chrome חוסם מיקום על HTTP.</b><br>פתרונות:<br>
            1️⃣ פתח בדפדפן <b>Firefox</b> במקום Chrome<br>
            2️⃣ או בשורת הכתובת הקלד:<br><code>chrome://flags</code><br>
            חפש: <i>Insecure origins treated as secure</i><br>
            הוסף: <code>http://{settings.app_base_url.replace("http://","")}</code>`);
        }} else {{
          setStatus('red', '❌ גישה למיקום נדחתה', '');
          showRetry(`כדי לאפשר מיקום:<br>
            1️⃣ לחץ על סמל המנעול/מידע בשורת הכתובת<br>
            2️⃣ בחר <b>הרשאות אתר</b><br>
            3️⃣ הגדר <b>מיקום → אפשר</b><br>
            4️⃣ לחץ <b>נסה שוב</b>`);
        }}
      }} else if (e.code === 2) {{
        setStatus('red', '📡 GPS לא זמין', 'ודא שה-GPS מופעל בהגדרות הטלפון');
        showRetry('');
      }} else {{
        setStatus('red', '⏱ timeout', 'המיקום לוקח זמן רב — נסה שוב');
        showRetry('');
      }}
    }},
    {{enableHighAccuracy: true, timeout: 15000}}
  );
}}

if (!navigator.geolocation) {{
  setStatus('red', '❌ GPS לא נתמך', 'נסה לפתוח בדפדפן Chrome או Firefox');
}} else {{
  grab();
  timer = setInterval(grab, INTERVAL_MS);
}}

if ('wakeLock' in navigator) {{
  navigator.wakeLock.request('screen').catch(() => {{}});
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


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
    from datetime import datetime, timezone
    import uuid as _uuid
    tech = db.query(Technician).filter(
        Technician.id == _uuid.UUID(technician_id)
    ).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    tech.current_latitude  = payload.latitude
    tech.current_longitude = payload.longitude
    tech.last_location_at  = datetime.now(timezone.utc)
    db.commit()
    logger.warning("📍 Live location updated for %s: %.4f, %.4f", tech.name, payload.latitude, payload.longitude)
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


# ── Technician call confirmation map page ────────────────────────────────────

@router.get("/my-calls/{tech_id}/data", summary="JSON list of pending calls for technician app")
def my_calls_data(tech_id: str, db: Session = Depends(get_db)):
    from app.models.assignment import Assignment
    from app.models.service_call import ServiceCall
    from app.models.elevator import Elevator
    from app.models.technician import Technician as TechnicianModel

    tech = db.query(TechnicianModel).filter(TechnicianModel.id == tech_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    assignments = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id, Assignment.status == "PENDING_CONFIRMATION")
        .order_by(Assignment.assigned_at.asc())
        .all()
    )
    result = []
    for a in assignments:
        call = db.query(ServiceCall).filter(ServiceCall.id == a.service_call_id).first()
        if not call:
            continue
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if not elev:
            continue
        result.append({
            "assignment_id": str(a.id),
            "address": elev.address,
            "city": elev.city,
            "fault_type": call.fault_type,
            "priority": call.priority,
            "description": call.description or "",
            "travel_minutes": a.travel_minutes or "?",
            "lat": elev.latitude,
            "lng": elev.longitude,
        })
    return result


@router.get("/my-calls/{tech_id}", summary="Mobile map page for technician to accept/reject pending calls")
def my_calls_page(tech_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse
    from app.models.assignment import Assignment
    from app.models.service_call import ServiceCall
    from app.models.elevator import Elevator
    from app.models.technician import Technician as TechnicianModel
    import json

    tech = db.query(TechnicianModel).filter(TechnicianModel.id == tech_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    assignments = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id, Assignment.status == "PENDING_CONFIRMATION")
        .order_by(Assignment.assigned_at.asc())
        .all()
    )

    calls_data = []
    _FAULT_HE = {"STUCK": "מעלית תקועה 🚨", "DOOR": "תקלת דלת", "ELECTRICAL": "חשמלית",
                 "MECHANICAL": "מכנית", "SOFTWARE": "תוכנה", "OTHER": "כללית"}
    _PRI_HE = {"CRITICAL": "🔴 קריטי", "HIGH": "🟠 גבוה", "MEDIUM": "🟡 בינוני", "LOW": "🟢 נמוך"}

    for a in assignments:
        call = db.query(ServiceCall).filter(ServiceCall.id == a.service_call_id).first()
        if not call:
            continue
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if not elev:
            continue
        calls_data.append({
            "assignment_id": str(a.id),
            "address": elev.address,
            "city": elev.city,
            "fault": _FAULT_HE.get(call.fault_type, call.fault_type),
            "priority": _PRI_HE.get(call.priority, call.priority),
            "priority_raw": call.priority,
            "description": call.description or "",
            "travel_minutes": a.travel_minutes or "?",
            "lat": elev.latitude,
            "lng": elev.longitude,
            "maps_url": f"https://maps.google.com/?q={elev.address}+{elev.city}",
            "waze_url": f"https://waze.com/ul?q={elev.address}+{elev.city}",
        })

    base_url = settings.app_base_url
    calls_json = json.dumps(calls_data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>קריאות לאישור — {tech.name}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; direction: rtl; }}
  #header {{ background: #1a73e8; color: white; padding: 14px 16px; text-align: center; }}
  #header h1 {{ font-size: 18px; }}
  #header p {{ font-size: 13px; opacity: .85; margin-top: 4px; }}
  #map {{ height: 280px; width: 100%; }}
  #list {{ padding: 12px; }}
  .card {{
    background: white; border-radius: 12px; padding: 14px; margin-bottom: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,.1);
  }}
  .card.done {{ opacity: .45; pointer-events: none; }}
  .card-title {{ font-size: 16px; font-weight: 700; margin-bottom: 4px; }}
  .card-sub {{ font-size: 13px; color: #555; margin-bottom: 10px; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 12px; font-weight: 600; margin-left: 6px;
  }}
  .CRITICAL {{ background:#fde8e8; color:#c0392b; }}
  .HIGH {{ background:#fef0e6; color:#e67e22; }}
  .MEDIUM {{ background:#fefce8; color:#b7950b; }}
  .LOW {{ background:#e8f8f0; color:#27ae60; }}
  .btn-row {{ display: flex; gap: 10px; }}
  .btn {{
    flex: 1; padding: 12px; border: none; border-radius: 10px;
    font-size: 15px; font-weight: 700; cursor: pointer;
  }}
  .btn-accept {{ background: #27ae60; color: white; }}
  .btn-reject {{ background: #e74c3c; color: white; }}
  .btn:active {{ opacity: .8; }}
  .nav-row {{ display: flex; gap: 8px; margin-bottom: 10px; }}
  .nav-btn {{
    flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 8px;
    background: white; font-size: 13px; text-align: center;
    text-decoration: none; color: #333;
  }}
  #empty {{ text-align: center; padding: 40px 20px; color: #888; font-size: 16px; }}
</style>
</head>
<body>
<div id="header">
  <h1>קריאות ממתינות לאישורך</h1>
  <p id="count-label">טוען...</p>
</div>
<div id="map"></div>
<div id="list"></div>

<script>
const TECH_ID = "{tech_id}";
const BASE_URL = "{base_url}";
const CALLS = {calls_json};

const _PRI_COLOR = {{CRITICAL:"#e74c3c",HIGH:"#e67e22",MEDIUM:"#f1c40f",LOW:"#27ae60"}};

// Init map
const map = L.map('map', {{zoomControl: true}});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© OpenStreetMap'
}}).addTo(map);

const markers = {{}};
const bounds = [];

function buildMarker(c) {{
  if (!c.lat || !c.lng) return;
  const icon = L.divIcon({{
    className: '',
    html: `<div style="background:${{_PRI_COLOR[c.priority_raw] || '#888'}};width:28px;height:28px;border-radius:50%;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,.4);"></div>`,
    iconSize: [28,28], iconAnchor: [14,14]
  }});
  const m = L.marker([c.lat, c.lng], {{icon}}).addTo(map);
  m.bindPopup(`<b>${{c.address}}, ${{c.city}}</b><br>${{c.fault}}`);
  markers[c.assignment_id] = m;
  bounds.push([c.lat, c.lng]);
}}

function renderList() {{
  const list = document.getElementById('list');
  const pending = CALLS.filter(c => !c._done);
  document.getElementById('count-label').textContent =
    pending.length === 0 ? 'אין קריאות ממתינות' : `${{pending.length}} קריאות ממתינות לאישורך`;

  if (pending.length === 0) {{
    list.innerHTML = '<div id="empty">✅ כל הקריאות טופלו!</div>';
    return;
  }}

  list.innerHTML = pending.map(c => `
    <div class="card" id="card-${{c.assignment_id}}">
      <div class="card-title">📍 ${{c.address}}, ${{c.city}}</div>
      <div class="card-sub">
        ${{c.fault}}
        <span class="badge ${{c.priority_raw}}">${{c.priority}}</span>
        🚗 ~${{c.travel_minutes}} דק'
        ${{c.description ? '<br>📝 ' + c.description : ''}}
      </div>
      <div class="nav-row">
        <a class="nav-btn" href="${{c.maps_url}}" target="_blank">🗺 גוגל מפות</a>
        <a class="nav-btn" href="${{c.waze_url}}" target="_blank">🚘 Waze</a>
      </div>
      <div class="btn-row">
        <button class="btn btn-accept" onclick="action('${{c.assignment_id}}','accept')">✅ קבל קריאה</button>
        <button class="btn btn-reject" onclick="action('${{c.assignment_id}}','reject')">❌ דחה</button>
      </div>
    </div>
  `).join('');
}}

async function action(aid, type) {{
  const card = document.getElementById('card-' + aid);
  if (card) card.style.opacity = '0.5';
  try {{
    const r = await fetch(`${{BASE_URL}}/webhooks/my-calls/${{TECH_ID}}/${{type}}/${{aid}}`, {{method:'POST'}});
    if (r.ok) {{
      const c = CALLS.find(x => x.assignment_id === aid);
      if (c) c._done = true;
      if (markers[aid]) map.removeLayer(markers[aid]);
      renderList();
    }} else {{
      if (card) card.style.opacity = '1';
      alert('שגיאה, נסה שוב');
    }}
  }} catch(e) {{
    if (card) card.style.opacity = '1';
    alert('בעיית חיבור');
  }}
}}

// Build map
CALLS.forEach(buildMarker);
if (bounds.length > 0) {{
  map.fitBounds(bounds, {{padding: [30,30]}});
}} else {{
  map.setView([32.6, 35.3], 9);
}}

renderList();
</script>
</body>
</html>"""
    return HTMLResponse(html)


@router.post("/my-calls/{tech_id}/accept/{assignment_id}")
def accept_call(tech_id: str, assignment_id: str, db: Session = Depends(get_db)):
    from app.services.ai_assignment_agent import confirm_assignment_by_id
    from app.models.technician import Technician as TechnicianModel
    tech = db.query(TechnicianModel).filter(TechnicianModel.id == tech_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Not found")
    result = confirm_assignment_by_id(db, tech.whatsapp_number or tech.phone, assignment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"status": "accepted"}


@router.post("/my-calls/{tech_id}/reject/{assignment_id}")
def reject_call(tech_id: str, assignment_id: str, db: Session = Depends(get_db)):
    from app.services.ai_assignment_agent import reject_assignment_by_id
    from app.models.technician import Technician as TechnicianModel
    tech = db.query(TechnicianModel).filter(TechnicianModel.id == tech_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Not found")
    result = reject_assignment_by_id(db, tech.whatsapp_number or tech.phone, assignment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"status": "rejected"}


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
