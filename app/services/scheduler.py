"""APScheduler background job runner — nightly maintenance + morning WhatsApp reminders."""

import logging
import re
import tempfile
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
_location_reminder_sent: dict[str, datetime] = {}  # tech_id → last reminder time
# phone → {assignment_id, address, city, expires_at} — NLP-inferred action awaiting explicit confirmation
_PENDING_NLP_CONFIRMATION: dict[str, dict] = {}


def _transcribe_voice(msg_data: dict, settings) -> str:
    """
    Download a WhatsApp voice message and transcribe it with OpenAI Whisper.
    Returns transcribed text, or empty string on failure.
    """
    if not getattr(settings, "openai_api_key", ""):
        logger.debug("OPENAI_API_KEY not set — voice transcription skipped")
        return ""

    try:
        import httpx
        import openai

        audio_data = msg_data.get("fileMessageData") or msg_data.get("audioMessageData", {})
        url = audio_data.get("downloadUrl", "")
        if not url:
            return ""

        # Download the audio file
        resp = httpx.get(url, timeout=30)
        if resp.status_code != 200:
            return ""

        # Save to temp file and send to Whisper
        suffix = ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        try:
            client = openai.OpenAI(api_key=settings.openai_api_key)
            with open(tmp_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="he",  # Hebrew
                )
            return result.text.strip()
        finally:
            os.unlink(tmp_path)

    except Exception as exc:
        logger.error("Voice transcription failed: %s", exc)
        return ""


def _auto_assign_maintenance_tech(db, service_call, elevator):
    """
    Auto-assign a maintenance technician to a newly created MAINTENANCE call.
    Priority: elevator.maintenance_technician_id → any MAINTENANCE_TECHNICIAN → leave OPEN.
    """
    from app.models.assignment import Assignment
    from app.models.technician import Technician

    tech = None

    # 1. Dedicated maintenance technician for this elevator
    if elevator.maintenance_technician_id:
        tech = db.query(Technician).filter(
            Technician.id == elevator.maintenance_technician_id,
            Technician.is_active == True,  # noqa: E712
        ).first()

    # 2. Any available MAINTENANCE_TECHNICIAN
    if not tech:
        tech = db.query(Technician).filter(
            Technician.role == "MAINTENANCE_TECHNICIAN",
            Technician.is_active == True,  # noqa: E712
            Technician.is_available == True,  # noqa: E712
        ).first()

    if not tech:
        return  # leave OPEN for dispatcher

    assignment = Assignment(
        service_call_id=service_call.id,
        technician_id=tech.id,
        status="PENDING_CONFIRMATION",
    )
    db.add(assignment)
    service_call.status = "ASSIGNED"
    db.commit()
    logger.info("Maintenance call %s auto-assigned to %s", service_call.id, tech.name)


def _run_nightly_maintenance():
    """
    Nightly job: mark overdue maintenances + tiered maintenance call creation.

    15 days  → LOW priority, silent (no WhatsApp)
    10 days  → MEDIUM priority, silent
    5 days   → HIGH priority + urgent WhatsApp to dispatcher
    overdue  → CRITICAL priority + urgent WhatsApp (once)
    """
    from datetime import date, timedelta
    from app.database import SessionLocal
    from app.services.maintenance_service import mark_overdue_maintenances
    from app.models.elevator import Elevator
    from app.models.service_call import ServiceCall
    from app.services.whatsapp_service import notify_dispatcher

    db = SessionLocal()
    try:
        overdue_count = mark_overdue_maintenances(db)

        today = date.today()
        threshold_15 = today + timedelta(days=15)

        upcoming = (
            db.query(Elevator)
            .filter(
                Elevator.next_service_date.isnot(None),
                Elevator.next_service_date <= threshold_15,
                Elevator.status == "ACTIVE",
            )
            .all()
        )

        _PRANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        opened = 0
        upgraded = 0
        notified = 0

        for elev in upcoming:
            days_left = (elev.next_service_date - today).days

            if days_left <= 0:
                priority = "CRITICAL"
                should_notify = True
            elif days_left <= 5:
                priority = "HIGH"
                should_notify = True
            elif days_left <= 10:
                priority = "MEDIUM"
                should_notify = False
            else:
                priority = "LOW"
                should_notify = False

            existing = db.query(ServiceCall).filter(
                ServiceCall.elevator_id == elev.id,
                ServiceCall.fault_type == "MAINTENANCE",
                ServiceCall.status.in_(["OPEN", "ASSIGNED", "IN_PROGRESS"]),
            ).first()

            addr = f"{elev.address}, {elev.city}"
            days_str = (
                f"מתוכנן ל-{elev.next_service_date.strftime('%d/%m/%Y')}"
                if days_left >= 0
                else f"באיחור {-days_left} ימים"
            )

            if existing:
                if _PRANK.get(priority, 2) < _PRANK.get(existing.priority, 2):
                    existing.priority = priority
                    db.commit()
                    upgraded += 1
                # Mark for morning WhatsApp — don't send at midnight
                if should_notify and "[maint_pending_notify]" not in (existing.description or "") \
                        and "[maint_notified]" not in (existing.description or ""):
                    existing.description = (existing.description or "") + " [maint_pending_notify]"
                    db.commit()
                continue

            sc = ServiceCall(
                elevator_id=elev.id,
                reported_by="מערכת — טיפול מונע",
                description=f"טיפול מונע {days_str}" + (" [maint_pending_notify]" if should_notify else ""),
                priority=priority,
                fault_type="MAINTENANCE",
                status="OPEN",
            )
            db.add(sc)
            db.commit()
            db.refresh(sc)
            opened += 1

            # Auto-assign maintenance technician if defined
            _auto_assign_maintenance_tech(db, sc, elev)


        logger.info(
            "Nightly maintenance: %d overdue, %d calls opened, %d upgraded, %d notified",
            overdue_count, opened, upgraded, notified,
        )
    except Exception as exc:
        logger.error("Nightly maintenance job failed: %s", exc)
    finally:
        db.close()


_MORNING_QUOTES = [
    "💪 \"האנשים הגדולים לא נולדו גדולים — הם גדלו.\" — מריו פוזו",
    "🌟 \"הצלחה היא סכום של מאמצים קטנים שחוזרים על עצמם יום אחר יום.\" — רוברט קולייר",
    "🔧 \"אין תחליף לעבודה קשה.\" — תומס אדיסון",
    "🚀 \"כל יום הוא הזדמנות להיות טוב יותר ממה שהיית אתמול.\"",
    "☀️ \"הדרך הטובה ביותר להתחיל היא להפסיק לדבר ולהתחיל לעשות.\" — וולט דיסני",
    "⚡ \"האמונה בעצמך היא הצעד הראשון לכל הישג.\"",
    "🏆 \"לא חשוב כמה פעמים נפלת — חשוב כמה פעמים קמת.\"",
    "💡 \"עבודה טובה היא הגאווה הכי שקטה שיש.\"",
    "🎯 \"כל קריאה שאתה פותר — מישהו לנשום לרווחה.\"",
    "🌄 \"בוקר חדש, סיכוי חדש, יום חדש לעשות את ההבדל.\"",
]

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def _gemini_text(prompt: str, api_key: str, max_tokens: int = 200) -> str:
    """Send a simple text prompt to Gemini REST API and return the response text."""
    import httpx
    resp = httpx.post(
        f"{_GEMINI_URL}?key={api_key}",
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _generate_personal_motivation(name: str, api_key: str) -> str:
    """Use Gemini to generate a fresh personal motivational sentence for a technician."""
    try:
        return _gemini_text(
            f"כתוב משפט מוטיבציה אישי קצר (משפט אחד בלבד) בעברית לטכנאי מעליות בשם {name}. "
            f"הודעה חמה, מעודדת ואישית. ללא הסברים, רק המשפט עצמו.",
            api_key,
        )
    except Exception as exc:
        logger.warning("Gemini motivation generation failed for %s: %s", name, exc)
        return ""

def _send_morning_location_requests():
    """07:15 — send each active technician a good-morning WhatsApp with their open call count."""
    import random
    from app.database import SessionLocal
    from app.models.technician import Technician
    from app.models.service_call import ServiceCall
    from app.models.assignment import Assignment
    from app.services.whatsapp_service import _send_message

    db = SessionLocal()
    try:
        technicians = (
            db.query(Technician)
            .filter(Technician.is_active == True, Technician.is_available == True)  # noqa: E712
            .all()
        )
        from app.config import get_settings
        base_url = get_settings().app_base_url
        portal_link = f"{base_url}/tech"
        quote = random.choice(_MORNING_QUOTES)

        sent = 0
        for tech in technicians:
            phone = tech.whatsapp_number or tech.phone
            if not phone:
                continue

            # Count open calls assigned to this technician
            open_count = (
                db.query(Assignment)
                .join(ServiceCall, Assignment.service_call_id == ServiceCall.id)
                .filter(
                    Assignment.technician_id == tech.id,
                    Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION", "AUTO_ASSIGNED"]),
                    ServiceCall.status.notin_(["CLOSED", "RESOLVED", "CANCELLED"]),
                )
                .count()
            )

            call_line = (
                f"📋 יש לך *{open_count} קריאות פתוחות* היום.\n" if open_count > 0
                else "📋 אין קריאות פתוחות כרגע — תהיה זמין! 👍\n"
            )

            msg = (
                f"בוקר טוב {tech.name} 👋\n\n"
                f"{quote}\n\n"
                f"────────────────────\n"
                f"{call_line}"
                f"🔗 {portal_link}\n"
                f"────────────────────\n"
                f"בהצלחה היום! 🙏"
            )
            if _send_message(phone, msg):
                sent += 1

        logger.info("Morning message sent to %d/%d technicians", sent, len(technicians))
    except Exception as exc:
        logger.error("Morning location request job failed: %s", exc)
    finally:
        db.close()


def _handle_technician_report(db, phone: str, text: str):
    """Resolve ALL of the technician's active calls when they send a report."""
    from app.models.assignment import Assignment, AuditLog
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message
    from datetime import datetime, timezone

    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    tech = (db.query(Technician)
            .filter(Technician.phone.contains(digits[-9:]) |
                    Technician.whatsapp_number.contains(digits[-9:]))
            .first())
    if not tech:
        return

    # Extract report notes (strip common prefixes)
    notes = text
    for prefix in ("דוח ", 'דו"ח ', "סיום ", "סגור ", "סגירה "):
        if notes.startswith(prefix):
            notes = notes[len(prefix):]
            break
    notes = notes or "טופל על ידי טכנאי"

    # Find ALL confirmed assignments for this technician
    assignments = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id,
                Assignment.status == "CONFIRMED")
        .all()
    )

    closed = 0
    closed_call_info = []  # list of (tech_name, address, notes) for dispatcher notifications
    for assignment in assignments:
        call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
        if not call or call.status not in ("IN_PROGRESS", "ASSIGNED", "OPEN"):
            continue

        old_status = call.status
        call.status = "RESOLVED"
        call.resolved_at = datetime.now(timezone.utc)
        call.resolution_notes = notes
        assignment.status = "AUTO_ASSIGNED"  # marks as completed

        audit = AuditLog(
            service_call_id=call.id,
            changed_by=tech.email or tech.name,
            old_status=old_status,
            new_status="RESOLVED",
            notes=f"דו\"ח טכנאי: {notes}",
        )
        db.add(audit)
        closed += 1

        from app.models.elevator import Elevator as _Elevator
        _elev = db.query(_Elevator).filter(_Elevator.id == call.elevator_id).first()
        _addr = f"{_elev.address}, {_elev.city}" if _elev else "כתובת לא ידועה"
        closed_call_info.append(_addr)

    db.commit()

    # Notify dispatcher for each closed call
    from app.services.whatsapp_service import notify_dispatcher as _notify_dispatcher
    for _addr in closed_call_info:
        _notify_dispatcher(f"✔️ קריאה נסגרה ע\"י *{tech.name}*\n📍 {_addr}\n📝 {notes}")

    if closed == 0:
        _send_message(
            tech.whatsapp_number or tech.phone,
            f"ℹ️ {tech.name}, לא נמצאו קריאות פעילות פתוחות על שמך."
        )
    elif closed == 1:
        _send_message(
            tech.whatsapp_number or tech.phone,
            f"✅ הקריאה נסגרה בהצלחה. תודה {tech.name}!"
        )
    else:
        _send_message(
            tech.whatsapp_number or tech.phone,
            f"✅ {closed} קריאות נסגרו בהצלחה. תודה {tech.name}!"
        )

    # Rebuild route after closing — remove resolved stops
    if tech.current_latitude and tech.current_longitude:
        try:
            from app.services.route_service import send_route_to_technician
            send_route_to_technician(db, tech)
        except Exception as exc:
            logger.error("Route rebuild after close failed for %s: %s", tech.name, exc)

    logger.info("📋 %d call(s) resolved by %s", closed, tech.name)


def _send_route_throttled(db, tech, cooldown_minutes: int = 30) -> None:
    """Send route with a longer cooldown for morning location triggers."""
    from app.services.route_service import send_route_to_technician
    send_route_to_technician(db, tech, cooldown_minutes=cooldown_minutes)


def _handle_tech_reply(db, phone: str, text: str, pending: list, s, quoted_msg_id: str = "") -> None:
    """
    Route a technician's incoming message to the correct assignment handler.

    Priority order:
    1. Confirm/cancel a pending NLP-inferred action (requires explicit "כן"/"לא")
    2. Reply-quoted "1"/"2"/"כן"/"לא" → match by WhatsApp message ID (unambiguous)
    3. Bare confirm/reject + exactly one pending
    4. Bare confirm/reject + multiple pending → ask tech to quote
    5. Free text → NLP address match → ask for confirmation
    6. Unrecognised → route to chat agent
    """
    from datetime import timedelta
    from app.services import ai_assignment_agent
    from app.services.whatsapp_service import _send_message

    clean = text.strip().lower()
    
    # Common confirm/reject words
    is_confirm = clean in ("1", "כן", "yes", "ok", "אוקי", "אוקיי", "סבבה", "אחלה", "בסדר", "y")
    is_reject = clean in ("2", "לא", "no", "ביטול", "בטל", "n")

    # ── 1. Pending NLP confirmation ───────────────────────────────────────────
    pending_confirm = _PENDING_NLP_CONFIRMATION.get(phone)
    if pending_confirm:
        if datetime.utcnow() < pending_confirm["expires_at"]:
            if is_confirm:
                aid = pending_confirm.pop("assignment_id", None)
                _PENDING_NLP_CONFIRMATION.pop(phone, None)
                if aid:
                    ai_assignment_agent.confirm_assignment_by_id(db, phone, aid)
                return
            elif is_reject:
                _PENDING_NLP_CONFIRMATION.pop(phone, None)
                _send_message(phone, "👍 בוטל. שלח שוב אם תרצה.")
                return
        else:
            _PENDING_NLP_CONFIRMATION.pop(phone, None)

    # ── 2. Reply-quoted message ───────────────────────────────────────────────
    if quoted_msg_id:
        linked = next((p for p in pending if p.get("whatsapp_message_id") == quoted_msg_id), None)
        if linked:
            if is_confirm:
                ai_assignment_agent.confirm_assignment_by_id(db, phone, linked["assignment_id"])
            elif is_reject:
                ai_assignment_agent.reject_assignment_by_id(db, phone, linked["assignment_id"])
            else:
                _send_message(phone, "אנא השב 'כן' (או 1) לאישור, או 'לא' (או 2) לדחייה.")
            return
        else:
            # They replied to some OTHER message (like the chat bot!).
            # Pass directly to chat agent.
            _handle_free_text(db, phone, text, s, is_reply=True)
            return

    # ── 3. Bare confirm/reject — exactly one pending ────────────────────────
    if len(pending) == 1 and (is_confirm or is_reject):
        if is_confirm:
            ai_assignment_agent.confirm_assignment_by_id(db, phone, pending[0]["assignment_id"])
        else:
            ai_assignment_agent.reject_assignment_by_id(db, phone, pending[0]["assignment_id"])
        return

    # ── 4. Bare confirm/reject — multiple pending → ask to quote ────────────
    if len(pending) > 1 and (is_confirm or is_reject):
        lines = "\n".join(
            f"• {p.get('address', 'כתובת לא ידועה')}, {p.get('city', '')}"
            for p in sorted(pending, key=lambda x: x["assigned_at"], reverse=True)[:8]
        )
        _send_message(phone,
            f"יש לך {len(pending)} קריאות ממתינות לאישור:\n{lines}\n\n"
            f"↩️ *השב ישירות על ההודעה* שאת/ה רוצה לקבל/לדחות."
        )
        return

    # ── 5. Free text → NLP address match ────────────────────────────────────
    # Avoid asking Gemini to parse obvious conversational short words as addresses.
    if len(clean) > 3 and not (is_confirm or is_reject) and clean not in ("תודה", "היי", "שלום"):
        gemini_key = getattr(s, "gemini_api_key", "")
        if gemini_key:
            result = _parse_reply_gemini(clean, pending, gemini_key)
            if result.get("accept"):
                aid = result["accept"][0]  # take only the first match
                matched = next((p for p in pending if p["assignment_id"] == aid), None)
                if matched:
                    addr = f"{matched.get('address', '')}, {matched.get('city', '')}".strip(", ")
                    _PENDING_NLP_CONFIRMATION[phone] = {
                        "assignment_id": aid,
                        "address": addr,
                        "expires_at": datetime.utcnow() + timedelta(minutes=10),
                    }
                    _send_message(phone,
                        f"🤔 הבנתי שרצית לקבל את הקריאה ב-*{addr}*.\n"
                        f"שלח *כן* לאישור, או *לא* לביטול."
                    )
                    return

    # ── 6. Unrecognised → chat agent ─────────────────────────────────────────
    _handle_free_text(db, phone, text, s, is_reply=bool(quoted_msg_id))


def _parse_reply_gemini(text: str, pending: list, api_key: str) -> dict:
    """
    Ask Gemini to match a technician's free-text reply to pending assignments.
    Returns {"accept": [assignment_id, ...], "reject": [assignment_id, ...]}.
    """
    import json as _json, re
    try:
        calls_desc = "\n".join(
            f"- ID: {p['assignment_id']} | כתובת: {p['address']}, {p['city']}"
            for p in pending
        )
        prompt = (
            f"טכנאי קיבל את הקריאות הבאות הממתינות לאישורו:\n{calls_desc}\n\n"
            f"הטכנאי שלח: \"{text}\"\n\n"
            f"החזר JSON בלבד (ללא הסברים):\n"
            f'{{ "accept": ["id1",...], "reject": ["id2",...] }}\n'
            f"אם לא ברור — החזר רשימות ריקות."
        )
        raw = _gemini_text(prompt, api_key, max_tokens=200)
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return _json.loads(raw.strip())
    except Exception as exc:
        logger.warning("Gemini reply parsing failed: %s", exc)
        return {"accept": [], "reject": []}


def _poll_whatsapp_replies():
    """
    Poll Green API every 15 seconds for incoming WhatsApp messages.
    Processes technician replies (1/2) and live location updates.
    Used instead of webhook when server is not publicly accessible.
    """
    import httpx
    from app.config import get_settings
    from app.database import SessionLocal
    from app.services import ai_assignment_agent

    s = get_settings()
    if not s.greenapi_instance_id or not s.greenapi_api_token:
        return

    receive_url = (
        f"https://api.green-api.com/waInstance{s.greenapi_instance_id}"
        f"/receiveNotification/{s.greenapi_api_token}"
    )
    delete_url = (
        f"https://api.green-api.com/waInstance{s.greenapi_instance_id}"
        f"/deleteNotification/{s.greenapi_api_token}"
    )

    # Process up to 10 queued messages per cycle
    for _ in range(10):
        try:
            resp = httpx.get(receive_url, timeout=5)
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break   # queue empty

            receipt_id = data.get("receiptId")
            body       = data.get("body", {})
            msg_type   = body.get("typeWebhook", "")

            # ── Determine the sender phone ────────────────────────────────────
            # For regular incoming messages, sender is in senderData.
            # When the Green API instance number == technician number (self-send),
            # the message arrives as outgoingMessageReceived — we treat it the same.
            sender_data = body.get("senderData", {})
            sender      = sender_data.get("sender", "")
            # chatId is the conversation partner; for outgoing it's the destination
            chat_id_raw = sender_data.get("chatId", "")

            is_incoming = msg_type == "incomingMessageReceived"
            is_outgoing = msg_type == "outgoingMessageReceived"

            # For outgoing messages from the instance, we treat chatId as the "phone"
            # (the technician who the message was sent to — and who presumably replied)
            if is_outgoing:
                phone = chat_id_raw.replace("@c.us", "")
            else:
                phone = sender.replace("@c.us", "").replace("@s.whatsapp.net", "")

            if is_incoming or is_outgoing:
                msg_data = body.get("messageData", {})
                msg_kind = msg_data.get("typeMessage", "")

                # For outgoing messages, only process if they look like a technician reply
                # (i.e. they contain quoted context meaning it's a REPLY to our message)
                # Skip purely outgoing notifications that are just echoes of what WE sent
                if is_outgoing:
                    # Only process outgoing if it's a reply (has quotedMessage) or is "1"/"2"
                    # This handles the case where the instance phone == technician phone
                    has_quote = bool(msg_data.get("extendedTextMessageData", {}).get("quotedMessage"))
                    text_check = msg_data.get("textMessageData", {}).get("textMessage", "").strip()
                    if not has_quote and text_check not in ("1", "2"):
                        # It's just an echo of our own outgoing message — skip
                        if receipt_id:
                            httpx.delete(f"{delete_url}/{receipt_id}", timeout=5)
                        continue

                db = SessionLocal()
                try:
                    if msg_kind == "locationMessage":
                        # Static pin → save as elevator coordinates for the active call
                        loc = msg_data.get("locationMessageData", {})
                        lat, lng = loc.get("latitude"), loc.get("longitude")
                        if lat and lng:
                            _save_pin_to_elevator(db, phone, float(lat), float(lng))

                    elif msg_kind == "audioMessage":
                        # Voice message — transcribe with Whisper then route like text
                        transcribed = _transcribe_voice(msg_data, s)
                        if transcribed:
                            logger.info("🎤 Voice from %s: %s", phone, transcribed)
                            _handle_free_text(db, phone, transcribed, s)

                    elif msg_kind in ("textMessage", "extendedTextMessage"):
                        # textMessage = plain text; extendedTextMessage = reply/quote
                        is_reply = msg_kind == "extendedTextMessage"
                        stanza_id = ""
                        if is_reply:
                            ext = msg_data.get("extendedTextMessageData", {})
                            text = ext.get("text", "").strip()
                            stanza_id = ext.get("stanzaId", "")
                            # Include quoted context so agent knows what's being replied to
                            quoted = ext.get("quotedMessage", {})
                            quoted_text = (
                                quoted.get("textMessage", "")
                                or quoted.get("extendedTextMessage", {}).get("text", "")
                            ).strip()
                            if quoted_text and quoted_text not in text:
                                text = f'[מגיב להודעה: "{quoted_text[:120]}"]\n{text}'
                        else:
                            text = msg_data.get("textMessageData", {}).get("textMessage", "").strip()

                        logger.info("📩 Message from %s (reply=%s stanza=%s): %r", phone, is_reply, stanza_id, text)
                        pending = ai_assignment_agent.get_pending_assignments_for_phone(db, phone)
                        if pending:
                            _handle_tech_reply(db, phone, text, pending, s, quoted_msg_id=stanza_id)
                        elif len(text) > 0:
                            _handle_free_text(db, phone, text, s, is_reply=is_reply)
                finally:
                    db.close()

            # Acknowledge (delete) the notification so it won't appear again
            if receipt_id:
                httpx.delete(f"{delete_url}/{receipt_id}", timeout=5)

        except Exception as exc:
            logger.warning("WhatsApp poll error: %s", exc)
            break


def _save_pin_to_elevator(db, phone: str, lat: float, lng: float) -> None:
    """
    A technician dropped a static location pin.
    Save it as the GPS coordinates of the elevator they're currently handling.
    Useful for sites without a proper address (industrial zones, etc.).
    """
    from app.models.assignment import Assignment
    from app.models.elevator import Elevator
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message

    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    tech = (db.query(Technician)
            .filter(Technician.phone.contains(digits[-9:]) |
                    Technician.whatsapp_number.contains(digits[-9:]))
            .first())
    if not tech:
        return

    # Find their active call
    assignment = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id,
                Assignment.status == "CONFIRMED")
        .order_by(Assignment.assigned_at.desc())
        .first()
    )
    if not assignment:
        _send_message(tech.whatsapp_number or tech.phone,
                      "📍 קיבלתי את הנקודה, אבל לא נמצאה קריאה פעילה שלך — הנקודה לא נשמרה.")
        return

    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    if not call:
        return

    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    if not elevator:
        return

    elevator.latitude  = lat
    elevator.longitude = lng
    db.commit()

    maps_url = f"https://maps.google.com/?q={lat},{lng}"
    _send_message(
        tech.whatsapp_number or tech.phone,
        f"✅ *נקודת GPS נשמרה למעלית*\n"
        f"📍 {elevator.address}, {elevator.city}\n"
        f"🌐 {lat:.5f}, {lng:.5f}\n"
        f"🔗 {maps_url}\n\n"
        f"הנקודה תשמש לניתוב קריאות עתידיות לאתר זה."
    )
    logger.info("📌 GPS pin (%.5f, %.5f) saved to elevator %s by %s", lat, lng, elevator.id, tech.name)


def _handle_self_assign(db, phone: str, text: str) -> None:
    """
    A technician sends 'לקחתי [כתובת]' to self-assign an open call.
    Finds the best matching OPEN call and assigns it to them.
    """
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message
    from datetime import datetime, timezone

    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    tech = (db.query(Technician)
            .filter(Technician.phone.contains(digits[-9:]) |
                    Technician.whatsapp_number.contains(digits[-9:]))
            .first())
    if not tech:
        return

    # Extract address hint from message (everything after "לקחתי")
    address_hint = text.replace("לקחתי", "").replace("קיבלתי", "").strip()

    open_calls = (
        db.query(ServiceCall)
        .filter(ServiceCall.status == "OPEN")
        .all()
    )

    if not open_calls:
        _send_message(tech.whatsapp_number or tech.phone,
                      "ℹ️ אין כרגע קריאות פתוחות שאינן משובצות.")
        return

    # If address hint given — find best matching call
    matched_call = None
    if address_hint:
        for call in open_calls:
            elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
            if elevator and address_hint in (elevator.address + " " + elevator.city):
                matched_call = call
                break
        # Fuzzy fallback — check if any word matches
        if not matched_call:
            hint_words = set(address_hint.split())
            for call in open_calls:
                elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
                if elevator:
                    addr_words = set((elevator.address + " " + elevator.city).split())
                    if hint_words & addr_words:
                        matched_call = call
                        break
    else:
        # No hint — take the highest-priority open call
        matched_call = sorted(
            open_calls,
            key=lambda c: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(c.priority, 2)
        )[0]

    if not matched_call:
        _send_message(tech.whatsapp_number or tech.phone,
                      f"❌ לא נמצאה קריאה פתוחה עם הכתובת: *{address_hint}*\nנסה לשלוח 'לקחתי' בלבד לקריאה הדחופה ביותר.")
        return

    elevator = db.query(Elevator).filter(Elevator.id == matched_call.elevator_id).first()

    # Cancel any existing pending assignments for this call
    existing = (db.query(Assignment)
                .filter(Assignment.service_call_id == matched_call.id,
                        Assignment.status == "PENDING_CONFIRMATION")
                .all())
    for a in existing:
        a.status = "CANCELLED"

    # Create confirmed assignment
    from app.services.maps_service import travel_time_minutes
    travel = None
    if tech.current_latitude and elevator and elevator.latitude:
        travel = travel_time_minutes(
            tech.current_latitude, tech.current_longitude,
            elevator.latitude, elevator.longitude
        )

    assignment = Assignment(
        service_call_id=matched_call.id,
        technician_id=tech.id,
        assignment_type="MANUAL",
        status="CONFIRMED",
        travel_minutes=travel,
        notes=f"{tech.name} לקח את הקריאה באופן עצמאי",
    )
    db.add(assignment)

    matched_call.status     = "IN_PROGRESS"
    matched_call.assigned_at = datetime.now(timezone.utc)

    audit = AuditLog(
        service_call_id=matched_call.id,
        changed_by=tech.email or tech.name,
        old_status="OPEN",
        new_status="IN_PROGRESS",
        notes=f"{tech.name} לקח את הקריאה דרך ווצאפ",
    )
    db.add(audit)
    db.commit()

    addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"
    travel_str = f"~{travel} דק' נסיעה" if travel else ""
    _send_message(
        tech.whatsapp_number or tech.phone,
        f"✅ *קריאה נרשמה על שמך*\n"
        f"📍 {addr}\n"
        f"🚗 {travel_str}\n\n"
        f"בסיום הטיפול, שלח *דוח* + תיאור קצר לסגירה."
    )
    logger.info("✋ %s self-assigned call %s at %s", tech.name, matched_call.id, addr)

    # Send updated route to technician
    _send_route_throttled(db, tech)


def _handle_technician_defer(db, phone: str, text: str) -> None:
    """
    A technician defers their active/pending call to tomorrow with an optional summary note.
    Example: "דחה למחר — המעלית עובדת, יש רעש קטן, יטופל בהמשך היום"
    """
    from datetime import date, timedelta
    from app.models.assignment import Assignment, AuditLog
    from app.models.service_call import ServiceCall
    from app.models.elevator import Elevator
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message, notify_dispatcher

    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    tech = (db.query(Technician)
            .filter(Technician.phone.contains(digits[-9:]) |
                    Technician.whatsapp_number.contains(digits[-9:]))
            .first())
    if not tech:
        return

    phone_out = tech.whatsapp_number or tech.phone

    # Find the oldest active assignment (PENDING_CONFIRMATION or CONFIRMED)
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status.in_(["PENDING_CONFIRMATION", "CONFIRMED"]),
        )
        .order_by(Assignment.assigned_at.asc())
        .first()
    )
    if not assignment:
        _send_message(phone_out, "ℹ️ לא נמצאה קריאה פעילה לדחייה.")
        return

    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first() if call else None
    addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"

    # Extract summary from text (everything after "דחה למחר" or "מחר")
    summary = text
    for marker in ["דחה למחר", "אטפל מחר", "מחר"]:
        if marker in summary:
            parts = summary.split(marker, 1)
            summary = parts[1].strip(" -–—:") if len(parts) > 1 else ""
            break

    tomorrow = date.today() + timedelta(days=1)
    defer_note = f"[דחוי למחר {tomorrow.strftime('%d/%m/%Y')} ע״י {tech.name}]"
    if summary:
        defer_note += f" — {summary}"

    assignment.status = "REJECTED"
    if call:
        call.description = (call.description or "") + f"\n{defer_note}"
        call.status = "OPEN"
        db.add(AuditLog(
            service_call_id=call.id,
            changed_by=tech.email or tech.name,
            old_status="ASSIGNED",
            new_status="OPEN",
            notes=defer_note,
        ))
    db.commit()

    _send_message(phone_out,
        f"✅ הקריאה ב{addr} נדחתה למחר.\n"
        f"📝 סיכום נשמר: {summary or '—'}"
    )
    notify_dispatcher(
        f"⏭️ *{tech.name}* דחה קריאה ב{addr} למחר.\n"
        f"📝 {summary or 'ללא סיכום'}"
    )


def _handle_technician_request(db, phone: str, text: str) -> None:
    """
    A technician sends 'מבקש [כתובת]' to request handling an open call that
    was not auto-assigned (passed to manual assignment).

    Unlike _handle_self_assign, this does NOT immediately assign — it creates
    a PENDING_CONFIRMATION assignment of type REQUEST and notifies the dispatcher
    for approval.  The dispatcher can then approve ('אשר בקשת <name>') or
    reject ('דחה בקשת <name>') via WhatsApp.
    """
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message, notify_dispatcher
    from datetime import datetime, timezone

    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    tech = (db.query(Technician)
            .filter(Technician.phone.contains(digits[-9:]) |
                    Technician.whatsapp_number.contains(digits[-9:]))
            .first())
    if not tech:
        return

    # Extract address hint — strip request keywords
    address_hint = text
    for kw in ["מבקש לטפל ב", "מבקש לטפל", "מבקש", "אשמח לטפל ב", "אשמח לטפל",
               "רוצה לטפל ב", "רוצה לטפל", "אני מבקש את הקריאה ב",
               "אני מבקש את הקריאה", "אני מבקש"]:
        address_hint = address_hint.replace(kw, "").strip()

    # Find OPEN calls only (manual assignment queue)
    open_calls = (
        db.query(ServiceCall)
        .filter(ServiceCall.status == "OPEN")
        .all()
    )

    if not open_calls:
        _send_message(tech.whatsapp_number or tech.phone,
                      "ℹ️ אין כרגע קריאות פתוחות הממתינות לשיבוץ.")
        return

    # Match by address hint
    matched_call = None
    if address_hint:
        for call in open_calls:
            elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
            if elevator and address_hint in (elevator.address + " " + elevator.city):
                matched_call = call
                break
        if not matched_call:
            hint_words = set(address_hint.split())
            for call in open_calls:
                elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
                if elevator:
                    addr_words = set((elevator.address + " " + elevator.city).split())
                    if hint_words & addr_words:
                        matched_call = call
                        break
    else:
        # No address — request the highest-priority open call
        matched_call = sorted(
            open_calls,
            key=lambda c: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(c.priority, 2)
        )[0]

    if not matched_call:
        _send_message(tech.whatsapp_number or tech.phone,
                      f"❌ לא נמצאה קריאה פתוחה עם הכתובת: *{address_hint}*\n"
                      f"נסה לשלוח 'מבקש' בלבד לקריאה הדחופה ביותר.")
        return

    elevator = db.query(Elevator).filter(Elevator.id == matched_call.elevator_id).first()
    addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"

    # Check if tech already has a pending request for this call
    existing_request = (db.query(Assignment)
                        .filter(Assignment.service_call_id == matched_call.id,
                                Assignment.technician_id == tech.id,
                                Assignment.assignment_type == "REQUEST",
                                Assignment.status == "PENDING_CONFIRMATION")
                        .first())
    if existing_request:
        _send_message(tech.whatsapp_number or tech.phone,
                      f"⏳ כבר שלחת בקשה לקריאה ב*{addr}*. ממתין לאישור המוקד.")
        return

    # Compute travel time if possible
    from app.services.maps_service import travel_time_minutes
    travel = None
    if tech.current_latitude and elevator and elevator.latitude:
        try:
            travel = travel_time_minutes(
                tech.current_latitude, tech.current_longitude,
                elevator.latitude, elevator.longitude
            )
        except Exception:
            pass

    # Create a REQUEST-type pending assignment
    assignment = Assignment(
        service_call_id=matched_call.id,
        technician_id=tech.id,
        assignment_type="REQUEST",
        status="PENDING_CONFIRMATION",
        travel_minutes=travel,
        notes=f"{tech.name} ביקש לטפל בקריאה דרך ווצאפ",
    )
    db.add(assignment)

    audit = AuditLog(
        service_call_id=matched_call.id,
        changed_by=tech.email or tech.name,
        old_status="OPEN",
        new_status="OPEN",
        notes=f"{tech.name} ביקש לטפל — ממתין לאישור מוקד",
    )
    db.add(audit)
    db.commit()

    travel_str = f"\n🚗 זמן נסיעה משוער: ~{travel} דק'" if travel else ""
    tech_first = tech.name.split()[0] if tech.name else tech.name

    # Notify dispatcher for approval
    notify_dispatcher(
        f"🙋 *{tech.name} מבקש לטפל בקריאה*\n"
        f"📍 {addr}\n"
        f"⚡ {matched_call.fault_type} | ⚠️ {matched_call.priority}"
        f"{travel_str}\n\n"
        f"לאישור: *אשר בקשת {tech_first}*\n"
        f"לדחייה: *דחה בקשת {tech_first}*"
    )

    # Acknowledge the technician
    _send_message(
        tech.whatsapp_number or tech.phone,
        f"✅ בקשתך לטפל בקריאה ב*{addr}* נשלחה למוקד.\n"
        f"תקבל עדכון לאחר אישור."
    )
    logger.info("🙋 %s requested call %s at %s — awaiting dispatcher approval", tech.name, matched_call.id, addr)


def _handle_send_route(db, phone: str) -> None:
    """Send the current route to a technician on demand."""
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message
    from app.services.route_service import send_route_to_technician, build_route, format_route_message

    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    tech = (db.query(Technician)
            .filter(Technician.phone.contains(digits[-9:]) |
                    Technician.whatsapp_number.contains(digits[-9:]))
            .first())
    if not tech:
        return

    if not tech.current_latitude or not tech.current_longitude:
        _send_message(tech.whatsapp_number or tech.phone,
            "📍 לא נמצא מיקום עדכני שלך.\n"
            "שתף מיקום חי דרך WhatsApp ואשלח את המסלול מיד.")
        return

    stops, suggestions = build_route(db, tech)
    msg = format_route_message(tech.name, stops, suggestions)
    _send_message(tech.whatsapp_number or tech.phone, msg)
    logger.info("🗺️ Route sent on demand to %s (%d stops)", tech.name, len(stops))


def _quick_detect_intent(text: str, settings) -> str:
    """Keyword-based intent detection — no API call. Returns intent or OTHER for ambiguous cases."""
    t = text.strip().lower()

    # Question signals — always win; must be checked FIRST before any action keyword
    # A message ending with "?" or starting with a question word is always a QUESTION
    question_starters = (
        "יש משהו", "יכול ל", "יכולה ל", "האם יש", "האם", "כמה יש",
        "יש לך", "יש פה", "מה יש", "מה קרה", "מה המצב", "מה הסטטוס",
        "תוכל", "תוכלי", "אפשר לשלוח", "אפשר לקבל",
    )
    if t.endswith("?") or any(t.startswith(qs) for qs in question_starters):
        return "QUESTION"

    report_kw  = ("דוח", "סיום", "סיימתי", "טיפלתי", "סגור", "סגירה", 'דו"ח', "טיפלנו", "בוצע")
    # "אטפל" requires a preceding space or start-of-string to avoid matching "שאטפל"/"שאני אטפל" inside questions
    take_kw    = ("לקחתי", "קיבלתי", "אני לוקח", "אני אטפל", " אטפל ", "הולך", "אני על זה", "אני מגיע")
    defer_kw   = ("דחה למחר", "אטפל מחר", "לדחות", "מחר בבוקר")
    request_kw = ("מבקש", "מבקשת", "אשמח לטפל", "רוצה לטפל")
    route_kw   = ("מסלול", "שלח מסלול", "מפה", "קריאות שלי", "מה יש לי היום", "מה יש לי",
                   "את המסלול", "הקריאות שלי", "סדר יום")
    ignore_kw  = ("תודה", "אוקיי", "אוק", "סבבה", "בסדר", "👍", "🙏", "✅", "ממש תודה")
    question_kw = ("אפשר", "מה ה", "כמה", "מתי", "היסטוריה", "פרטים", "מי ה", "איפה",
                   "קריאות פתוחות", "סטטוס", "רשימה", "כתובת", "פירוט", "מה המצב")
    if any(k in t for k in report_kw):
        return "REPORT"
    if any(k in t for k in route_kw):
        return "ROUTE"
    if any(k in t for k in take_kw):
        return "TAKE"
    if any(k in t for k in defer_kw):
        return "DEFER"
    if any(k in t for k in request_kw):
        return "REQUEST"
    if any(k in t for k in ignore_kw) and len(t) < 20:
        return "IGNORE"
    if any(k in t for k in question_kw):
        return "QUESTION"
    return "OTHER"


def _handle_free_text(db, phone: str, text: str, settings, is_reply: bool = False) -> None:  # noqa: ARG001
    """
    Route free-text messages to the right handler.
    With Gemini configured: everything goes through the chat agent (questions AND actions).
    Without Gemini: keyword-based fallback.
    """
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message

    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    tech = (db.query(Technician)
            .filter(Technician.phone.contains(digits[-9:]) |
                    Technician.whatsapp_number.contains(digits[-9:]))
            .first())

    dispatcher_numbers = [n.strip() for n in (settings.dispatcher_whatsapp or "").split(",") if n.strip()]
    is_dispatcher = any(
        "".join(c for c in n if c.isdigit())[-9:] == digits[-9:]
        for n in dispatcher_numbers
    )
    is_manager = is_dispatcher or (tech and getattr(tech, "role", "") == "MANAGER")

    if not tech and not is_manager:
        logger.warning("📵 Message from unregistered number %s — ignored", phone)
        return

    # Pure dispatcher (no tech record) → dispatcher command handler
    if is_dispatcher and not tech:
        from app.services.dispatcher_commands import handle_dispatcher_command
        handle_dispatcher_command(db, phone, text, settings)
        return

    # No Gemini configured → keyword-based fallback
    if not settings.gemini_api_key:
        if any(w in text for w in ["דוח", "סיום", "סיימתי", "טיפלתי", "סגור"]):
            _handle_technician_report(db, phone, text)
        elif any(w in text for w in ["מסלול", "שלח מסלול", "קריאות שלי", "מה יש לי היום"]):
            _handle_send_route(db, phone)
        elif any(w in text for w in ["לקחתי", "קיבלתי", "אני לוקח", "הולך", "אני על זה"]):
            _handle_self_assign(db, phone, text)
        elif any(w in text for w in ["דחה למחר", "אטפל מחר", "לדחות"]):
            _handle_technician_defer(db, phone, text)
        elif any(w in text for w in ["מבקש", "אשמח לטפל", "רוצה לטפל"]):
            _handle_technician_request(db, phone, text)
        else:
            _handle_chat_question_simple(db, phone, text, settings)
        return

    # Gemini configured → chat agent handles everything (questions + actions)
    _handle_chat_question(db, phone, text, settings, with_history=True)


def _handle_chat_question_simple(db, phone: str, question: str, settings) -> None:
    """
    Simple DB-based answers for common questions when no Anthropic API key is set.
    Handles the most frequent queries without needing Claude.
    """
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message

    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]

    # Only answer known technicians or dispatcher
    tech = (db.query(Technician)
            .filter(Technician.phone.contains(digits[-9:]) |
                    Technician.whatsapp_number.contains(digits[-9:]))
            .first())
    dispatcher_numbers = [n.strip() for n in (settings.dispatcher_whatsapp or "").split(",") if n.strip()]
    is_dispatcher = any(
        "".join(c for c in n if c.isdigit())[-9:] == digits[-9:]
        for n in dispatcher_numbers
    )
    if not tech and not is_dispatcher:
        return

    q = question.lower()

    # "כמה קריאות פתוחות / open calls"
    if any(w in q for w in ["פתוחות", "פתוח", "כמה קריאות", "open"]):
        open_count    = db.query(ServiceCall).filter(ServiceCall.status == "OPEN").count()
        assigned_count= db.query(ServiceCall).filter(ServiceCall.status == "ASSIGNED").count()
        progress_count= db.query(ServiceCall).filter(ServiceCall.status == "IN_PROGRESS").count()
        _send_message(phone,
            f"📊 *סטטוס קריאות כרגע*\n"
            f"🔴 פתוחות (ממתינות לשיבוץ): *{open_count}*\n"
            f"🟡 משובצות (ממתינות לאישור): *{assigned_count}*\n"
            f"🔵 בטיפול: *{progress_count}*"
        )
        return

    # "הקריאה שלי / הקריאה הפעילה"
    if tech and any(w in q for w in ["הקריאה שלי", "הקריאה הפעילה", "איפה אני", "מה יש לי"]):
        from app.models.assignment import Assignment
        from app.models.elevator import Elevator
        asgn = (db.query(Assignment)
                .filter(Assignment.technician_id == tech.id,
                        Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"]))
                .order_by(Assignment.assigned_at.desc())
                .first())
        if not asgn:
            _send_message(phone, "ℹ️ אין לך קריאה פעילה כרגע.")
            return
        call = db.query(ServiceCall).filter(ServiceCall.id == asgn.service_call_id).first()
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first() if call else None
        addr = f"{elev.address}, {elev.city}" if elev else "כתובת לא ידועה"
        _send_message(phone,
            f"📋 *הקריאה הפעילה שלך*\n"
            f"📍 {addr}\n"
            f"🔧 {call.fault_type if call else ''}\n"
            f"🚗 בנסיעה: ~{asgn.travel_minutes or '?'} דקות"
        )
        return

    # Generic fallback
    _send_message(phone,
        f"🤖 לא הצלחתי להבין את השאלה.\n"
        f"כרגע אני יכול לענות על:\n"
        f"• *כמה קריאות פתוחות יש*\n"
        f"• *מה הקריאה שלי*"
    )


def _handle_chat_question(db, phone: str, question: str, settings, with_history: bool = False) -> None:
    """Route a free-text WhatsApp question to the Claude chat agent and reply."""
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message

    # Identify who is asking
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    tech = (
        db.query(Technician)
        .filter(
            Technician.phone.contains(digits[-9:]) |
            Technician.whatsapp_number.contains(digits[-9:])
        )
        .first()
    )
    asker_name = tech.name if tech else "משתמש"

    # Only known technicians / managers OR dispatcher number
    dispatcher_numbers = [n.strip() for n in (settings.dispatcher_whatsapp or "").split(",") if n.strip()]
    is_dispatcher = any(
        "".join(c for c in n if c.isdigit())[-9:] == digits[-9:]
        for n in dispatcher_numbers
    )
    if not tech and not is_dispatcher:
        logger.warning("Chat question from unknown number %s — ignored", phone)
        return

    logger.info("💬 Chat question from %s: %s", asker_name, question)

    if not settings.gemini_api_key:
        _handle_chat_question_simple(db, phone, question, settings)
        return

    try:
        from app.services.chat_agent import answer_question
        answer = answer_question(db, question, asker_name, phone=phone, with_history=with_history)
        _send_message(phone, f"🤖 *נציג המערכת*\n\n{answer}")

        # Save bot response to conversation history so it appears in the UI
        # and so the bot can see its own previous replies in future turns
        try:
            from app.models.whatsapp_message import WhatsAppMessage
            db.add(WhatsAppMessage(phone=phone, direction="out", msg_type="text", text=answer))
            db.commit()
        except Exception as save_exc:
            logger.warning("Could not save bot reply to history: %s", save_exc)

        # Auto-build QA knowledge base from successful conversations
        # Skip write-action questions (close/assign/transfer) — those are too specific
        _write_keywords = ["סגור", "שבץ", "העבר", "הצעת מחיר", "לבטל", "בטל"]
        if len(answer) > 60 and not any(w in question for w in _write_keywords):
            try:
                from app.models.bot_qa import BotQA
                existing = db.query(BotQA).filter(BotQA.question == question).first()
                if not existing:
                    db.add(BotQA(
                        question=question,
                        answer=answer,
                        active=True,
                        use_count=0,
                        created_by="auto",
                    ))
                    db.commit()
                else:
                    existing.answer = answer
                    existing.updated_at = __import__('datetime').datetime.utcnow()
                    db.commit()
            except Exception as qa_exc:
                logger.warning("Could not auto-save QA pair: %s", qa_exc)

    except Exception as exc:
        logger.error("Chat agent error: %s", exc)
        _handle_chat_question_simple(db, phone, question, settings)


_REMINDER_AFTER_MINUTES  = 60    # send hourly reminder if call still unconfirmed
_ESCALATE_AFTER_MINUTES  = 180   # alert dispatcher if still unconfirmed after 3 hours


def _check_pending_assignment_timeouts():
    """
    Runs every minute.

    Part A — PENDING_CONFIRMATION assignments:
      - After 10 min with no reply → send a reminder WhatsApp
      - After 20 min with no reply → mark REJECTED, reassign to next technician

    Part B — Orphaned OPEN calls (status=OPEN with no active assignment):
      - Immediately try to assign them via AI agent
      - If no technician available → alert dispatcher
    """
    from datetime import datetime, timezone, timedelta

    from app.database import SessionLocal
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator
    from app.models.service_call import ServiceCall
    from app.models.technician import Technician
    from app.services import ai_assignment_agent
    from app.services.whatsapp_service import _send_message

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # ── Part B: Orphaned OPEN calls ───────────────────────────────────────
        # Find all OPEN calls that have no PENDING_CONFIRMATION or CONFIRMED assignment
        open_calls = (
            db.query(ServiceCall)
            .filter(ServiceCall.status == "OPEN")
            .all()
        )
        # Get IDs of calls already being handled
        active_assignment_call_ids = {
            a.service_call_id
            for a in db.query(Assignment)
            .filter(Assignment.status.in_(["PENDING_CONFIRMATION", "CONFIRMED"]))
            .all()
        }
        orphaned = [
            c for c in open_calls
            if c.id not in active_assignment_call_ids
            and c.fault_type != "MAINTENANCE"  # maintenance calls are scheduled, not auto-assigned
        ]

        from app.services.working_hours import is_working_hours as _iwh
        if orphaned and not _iwh():
            logger.info("⏰ Off-hours — skipping %d orphaned call(s)", len(orphaned))
            orphaned = []

        if orphaned:
            logger.info("🔄 Found %d orphaned OPEN call(s) — attempting assignment", len(orphaned))
            from app.config import get_settings
            from app.services.whatsapp_service import notify_dispatcher_unassigned, _send_message
            from app.models.technician import Technician as _Tech
            s = get_settings()

            # When re-dispatching multiple calls at once, suppress per-call WhatsApp noise.
            # We'll send one consolidated message per technician and one for the dispatcher.
            batch_silent = len(orphaned) > 1
            # tech_phone → [(addr, fault_type, call_number)]
            _tech_dispatch_map: dict = {}
            _dispatcher_redispatch: list = []

            for call in orphaned:
                try:
                    # Collect previously rejected technicians for this call
                    rejected_ids = [
                        a.technician_id
                        for a in db.query(Assignment).filter(
                            Assignment.service_call_id == call.id,
                            Assignment.status == "REJECTED",
                        ).all()
                    ]
                    next_a = ai_assignment_agent.assign_with_confirmation(
                        db, call, exclude_tech_ids=rejected_ids, silent=batch_silent
                    )
                    if not next_a:
                        logger.warning("No technician available for orphaned call %s", call.id)
                        # Alert dispatcher once — mark call as DISPATCHER_NOTIFIED via notes
                        already_notified = (call.description or "").endswith("[dispatcher_notified]")
                        if s.dispatcher_whatsapp and not already_notified:
                            elevator = db.query(Elevator).filter(
                                Elevator.id == call.elevator_id
                            ).first()
                            if elevator:
                                notify_dispatcher_unassigned(
                                    s.dispatcher_whatsapp,
                                    elevator.address, elevator.city, call.fault_type,
                                    call_number=call.call_number,
                                    app_base_url=getattr(s, "app_base_url", ""),
                                )
                                call.description = (call.description or "") + " [dispatcher_notified]"
                                db.commit()
                                logger.info("📢 Dispatcher alerted for unassigned call %s", call.id)
                    else:
                        logger.info("✅ Orphaned call %s re-assigned", call.id)
                        if batch_silent:
                            # Collect techs dispatched to this call for consolidated messages
                            elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
                            addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"
                            num_str = f"S{call.call_number:05d}" if call.call_number else ""
                            _dispatcher_redispatch.append((addr, call.fault_type, num_str))
                            # Find all new PENDING_CONFIRMATION assignments for this call
                            new_asgns = db.query(Assignment).filter(
                                Assignment.service_call_id == call.id,
                                Assignment.status == "PENDING_CONFIRMATION",
                            ).all()
                            for a in new_asgns:
                                tech = db.get(_Tech, a.technician_id)
                                if not tech:
                                    continue
                                phone = tech.whatsapp_number or tech.phone
                                if phone:
                                    _tech_dispatch_map.setdefault(phone, []).append(
                                        (addr, call.fault_type, num_str, str(call.id), str(tech.id))
                                    )
                except Exception as exc:
                    logger.error("Failed to assign orphaned call %s: %s", call.id, exc)

            # ── Send ONE consolidated WhatsApp per technician ─────────────────
            if batch_silent and _tech_dispatch_map:
                from app.config import get_settings as _gs
                base_url = getattr(_gs(), "app_base_url", "").rstrip("/")
                portal_url = f"{base_url}/tech" if base_url else ""
                for tech_phone, call_list in _tech_dispatch_map.items():
                    lines = "\n".join(
                        f"• {addr} ({ft})" + (f" [{num}]" if num else "")
                        for addr, ft, num, _, _ in call_list
                    )
                    _send_message(
                        tech_phone,
                        f"🔔 *{len(call_list)} קריאות ממתינות לטיפולך*\n"
                        f"────────────────────\n{lines}\n────────────────────\n"
                        + (f"📱 {portal_url}\n" if portal_url else "")
                        + "↩️ כנס לפורטל לקבלה / דחייה של כל קריאה"
                    )

            # ── Send ONE consolidated dispatcher notification ─────────────────
            if batch_silent and _dispatcher_redispatch and s.dispatcher_whatsapp:
                from app.services.whatsapp_service import notify_dispatcher as _nd
                from app.config import get_settings as _gs
                base_url = getattr(_gs(), "app_base_url", "").rstrip("/")
                lines = "\n".join(
                    f"• {addr} ({ft})" + (f" [{num}]" if num else "")
                    for addr, ft, num in _dispatcher_redispatch
                )
                _nd(
                    f"📋 *{len(_dispatcher_redispatch)} קריאות שודרו מחדש לטכנאים*\n"
                    f"────────────────────\n{lines}\n────────────────────\n"
                    + (f"🔗 {base_url}/calls" if base_url else "")
                )

        # ── Part A: PENDING_CONFIRMATION timeouts ─────────────────────────────
        pending = (
            db.query(Assignment)
            .filter(Assignment.status == "PENDING_CONFIRMATION")
            .all()
        )

        _reminder_calls: list = []  # collected this run — sent as one batch after loop
        _reminded_call_ids: set = set()  # deduplicate calls with multiple pending assignments

        for assignment in pending:
            assigned_at = assignment.assigned_at
            if assigned_at.tzinfo is None:
                assigned_at = assigned_at.replace(tzinfo=timezone.utc)

            age_minutes = (now - assigned_at).total_seconds() / 60

            tech = db.query(Technician).filter(
                Technician.id == assignment.technician_id
            ).first()
            call = db.query(ServiceCall).filter(
                ServiceCall.id == assignment.service_call_id
            ).first()
            elevator = db.query(Elevator).filter(
                Elevator.id == call.elevator_id
            ).first() if call else None

            if not tech or not call:
                continue

            phone = tech.whatsapp_number or tech.phone
            addr  = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"

            # ── Stage 2: escalate (3 hours) — alert dispatcher ───────────────
            if age_minutes >= _ESCALATE_AFTER_MINUTES:
                logger.warning(
                    "⏰ Assignment %s timed out (%.0f min) — alerting dispatcher",
                    assignment.id, age_minutes,
                )
                assignment.status = "CANCELLED"
                db.commit()

                # If all assignments for this call are done/cancelled, alert dispatcher
                remaining = db.query(Assignment).filter(
                    Assignment.service_call_id == call.id,
                    Assignment.status == "PENDING_CONFIRMATION",
                ).count() if call else 0

                confirmed_count = db.query(Assignment).filter(
                    Assignment.service_call_id == call.id,
                    Assignment.status.in_(["CONFIRMED", "AUTO_ASSIGNED"]),
                ).count() if call else 0
                if remaining == 0 and confirmed_count == 0 and call and elevator:
                    call.status = "OPEN"
                    db.commit()
                    from app.config import get_settings
                    from app.services.working_hours import is_working_hours as _iwh
                    s = get_settings()
                    from app.services.whatsapp_service import notify_dispatcher
                    if _iwh():
                        _base_url = getattr(s, "app_base_url", "").rstrip("/")
                        _num_str = f" S{call.call_number:05d}" if call.call_number else ""
                        _link = f"\n🔗 {_base_url}/calls" if _base_url else ""
                        notify_dispatcher(
                            f"⚠️ קריאה{_num_str} ב{addr} לא אושרה אחרי {_ESCALATE_AFTER_MINUTES} דקות — נא לשבץ ידנית.{_link}"
                        )
                    else:
                        logger.info("⏰ Off-hours — 180-min escalation for %s deferred to morning", addr)

            # ── Stage 1: collect calls needing reminder (send consolidated below) ──
            elif age_minutes >= _REMINDER_AFTER_MINUTES and not assignment.reminder_sent_at:
                assignment.reminder_sent_at = now
                db.commit()
                if call and elevator and call.id not in _reminded_call_ids:
                    _reminder_calls.append((call, elevator, addr))
                    _reminded_call_ids.add(call.id)

        # ── Send consolidated reminder to all available technicians ──────────
        if _reminder_calls:
            from app.config import get_settings as _gs
            from app.services.whatsapp_service import _send_message as _wa
            from app.services.working_hours import is_working_hours
            base_url = getattr(_gs(), "app_base_url", "").rstrip("/")
            portal_url = f"{base_url}/tech" if base_url else ""

            all_techs = (
                db.query(Technician).filter(Technician.is_active == True, Technician.is_available == True).all()  # noqa: E712
                if is_working_hours() else
                db.query(Technician).filter(Technician.is_active == True, Technician.is_on_call == True).all()  # noqa: E712
            )
            for reminder_tech in all_techs:
                r_phone = reminder_tech.whatsapp_number or reminder_tech.phone
                if not r_phone:
                    continue
                if len(_reminder_calls) == 1:
                    _c, _e, _addr = _reminder_calls[0]
                    _num = f" S{_c.call_number:05d}" if _c.call_number else ""
                    _wa(r_phone,
                        f"🔔 *תזכורת — קריאה{_num} ממתינה לטיפול*\n"
                        f"📍 {_addr}\n⚡ {_c.fault_type}\n"
                        + (f"📱 {portal_url}\n" if portal_url else "")
                        + f"↩️ השב על הודעת השיבוץ: *1* לקבלה | *2* לדחייה"
                    )
                else:
                    lines = "\n".join(
                        f"• {_addr} ({_c.fault_type})" + (f" [S{_c.call_number:05d}]" if _c.call_number else "")
                        for _c, _e, _addr in _reminder_calls[:12]
                    )
                    _wa(r_phone,
                        f"🔔 *{len(_reminder_calls)} קריאות ממתינות לטיפול*\n"
                        f"────────────────────\n{lines}\n────────────────────\n"
                        + (f"📱 {portal_url}\n" if portal_url else "")
                        + f"↩️ כנס לפורטל לטיפול או השב על הודעת השיבוץ הרלוונטית"
                    )
            logger.info("🔔 Consolidated reminder sent for %d call(s) to %d technicians",
                        len(_reminder_calls), len(all_techs))

    except Exception as exc:
        logger.error("Timeout checker error: %s", exc)
    finally:
        db.close()


def _poll_email_calls():
    """Poll Gmail every 60 seconds for new service-call emails."""
    from app.database import SessionLocal
    from app.services.email_poller import poll_emails

    db = SessionLocal()
    try:
        count = poll_emails(db)
        logger.warning("📧 Email poller ran — %d new call(s) created", count)
    except Exception as exc:
        logger.error("📧 Email poller job failed: %s", exc)
    finally:
        db.close()


def _poll_inspection_emails():
    """Scan Gmail every hour for inspection report attachments (PDFs / images)."""
    from app.database import SessionLocal
    from app.services.inspection_email_poller import poll_inspection_emails

    db = SessionLocal()
    try:
        count = poll_inspection_emails(db)
        if count:
            logger.info("📄 Inspection email scan — %d report(s) processed", count)
    except Exception as exc:
        logger.error("📄 Inspection email scan job failed: %s", exc)
    finally:
        db.close()


def _check_location_reminders():
    """
    Every 5 minutes during working hours: if a technician opened the tracking page
    today (last_location_at is set today) but hasn't updated in 20+ minutes,
    send them a WhatsApp reminder to reopen the tracking link.
    """
    from app.database import SessionLocal
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message
    from app.services.working_hours import is_working_hours
    from app.config import get_settings
    from datetime import datetime, timezone, timedelta

    if not is_working_hours():
        return

    db = SessionLocal()
    try:
        s = get_settings()
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = now - timedelta(minutes=45)

        techs = db.query(Technician).filter(
            Technician.is_active == True,          # noqa: E712
            Technician.role == "TECHNICIAN",
            Technician.last_location_at != None,   # noqa: E711  — has used tracking today or before
            Technician.last_location_at >= today_start,  # opened today
            Technician.last_location_at <= cutoff,       # but not in last 20 min
        ).all()

        for tech in techs:
            phone = tech.whatsapp_number or tech.phone
            if not phone:
                continue
            # Send reminder at most once every 45 minutes per technician
            tech_id_str = str(tech.id)
            last_sent = _location_reminder_sent.get(tech_id_str)
            if last_sent and (now - last_sent).total_seconds() < 45 * 60:
                continue
            tracking_url = f"{s.app_base_url}/webhooks/track/{tech.id}"
            _send_message(phone,
                f"📍 {tech.name}, המיקום שלך הפסיק להתעדכן.\n"
                f"פתח שוב את הקישור כדי להמשיך:\n{tracking_url}"
            )
            _location_reminder_sent[tech_id_str] = now
            logger.warning("📍 Location reminder sent to %s", tech.name)
    except Exception as exc:
        logger.error("Location reminder job failed: %s", exc)
    finally:
        db.close()


def _check_monitoring_calls():
    """
    Daily job (08:00): auto-close MONITORING calls older than 7 days.
    Also checks if a new call arrived for the same elevator — marks it as recurring.
    """
    from datetime import datetime, timezone, timedelta
    from app.database import SessionLocal
    from app.models.service_call import ServiceCall
    from app.models.assignment import AuditLog

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        monitoring_calls = (
            db.query(ServiceCall)
            .filter(ServiceCall.status == "MONITORING")
            .all()
        )
        closed = 0
        for call in monitoring_calls:
            if not call.monitoring_since:
                continue
            # Check if a new call arrived for this elevator since monitoring started
            new_call = (
                db.query(ServiceCall)
                .filter(
                    ServiceCall.elevator_id == call.elevator_id,
                    ServiceCall.id != call.id,
                    ServiceCall.created_at > call.monitoring_since,
                    ServiceCall.status != "MONITORING",
                )
                .first()
            )
            if new_call:
                # Mark as recurring and reopen with HIGH priority
                new_call.is_recurring = True
                new_call.priority = "HIGH"
                call.status = "CLOSED"
                db.add(AuditLog(
                    service_call_id=call.id,
                    changed_by="system",
                    old_status="MONITORING",
                    new_status="CLOSED",
                    notes="נסגרה — תקלה חוזרת זוהתה בקריאה חדשה",
                ))
                db.add(AuditLog(
                    service_call_id=new_call.id,
                    changed_by="system",
                    old_status=new_call.status,
                    new_status=new_call.status,
                    notes="סומנה כתקלה חוזרת — עדיפות עודכנה ל-HIGH",
                ))
                closed += 1
            elif call.monitoring_since <= cutoff:
                # 7 days passed with no recurrence — close it
                call.status = "CLOSED"
                db.add(AuditLog(
                    service_call_id=call.id,
                    changed_by="system",
                    old_status="MONITORING",
                    new_status="CLOSED",
                    notes="נסגרה אוטומטית — 7 ימי מעקב ללא תקלה חוזרת",
                ))
                closed += 1
        if closed:
            db.commit()
            logger.info("🔍 Monitoring: closed %d calls", closed)
    except Exception as exc:
        logger.error("_check_monitoring_calls failed: %s", exc)
    finally:
        db.close()


def _scan_drive_inspections():
    """Scan Google Drive folder for new inspection PDFs and process them."""
    from app.services import drive_service
    if not drive_service.is_configured():
        return
    try:
        from app.database import SessionLocal
        from app.models.inspection_report import InspectionReport
        from app.services.inspection_service import process_inspection_report

        db = SessionLocal()
        try:
            # Collect already-processed Drive file IDs
            processed = {
                r.drive_file_id
                for r in db.query(InspectionReport.drive_file_id)
                .filter(InspectionReport.drive_file_id.isnot(None))
                .all()
            }
            new_files = drive_service.list_folder_files(processed)
            if not new_files:
                return
            logger.info("Drive scan: %d new file(s) found", len(new_files))
            for f in new_files:
                fid = f["id"]
                fname = f.get("name", "")
                mime = f.get("mimeType", "application/octet-stream")
                # Only process PDFs and images
                if not any(mime.startswith(t) for t in ("application/pdf", "image/")):
                    continue
                content = drive_service.get_download_bytes(fid)
                if not content:
                    continue
                result = process_inspection_report(
                    db, content, mime, fname, source="drive",
                    existing_drive_file_id=fid,
                )
                if result.get("status") == "duplicate":
                    logger.info("Drive scan skipped duplicate: %s", fname)
                    continue
                if result.get("report_id"):
                    report = db.query(InspectionReport).filter(
                        InspectionReport.id == result["report_id"]
                    ).first()
                    if report and report.drive_file_id != fid:
                        report.drive_file_id = fid
                        report.file_path = None
                        db.commit()
                logger.info("Drive scan processed: %s → %s", fname, result.get("status"))
        finally:
            db.close()
    except Exception as exc:
        logger.error("Drive scan failed: %s", exc)


_DEFICIENCY_THRESHOLDS = [
    # (days_since_inspection, color, label)
    (7,   "🟡", "צהוב — יש לטפל תוך שבוע"),
    (14,  "🟠", "כתום — יש לטפל בדחיפות"),
    (30,  "🔴", "אדום — נדרש טיפול מיידי!"),
]


def _check_inspection_deficiency_escalation():
    """
    Runs every 6 hours. Escalates open inspection deficiencies:

    Per-deficiency deadline (from 'תוך X יום' in description):
    - 5 days before deadline: ⚠️ approaching warning
    - On/after deadline:      🔴 overdue alert

    Fallback (no parsed deadline):
    - 7 / 14 / 30 days since inspection: yellow / orange / red
    """
    from datetime import date, timedelta
    from app.database import SessionLocal
    from app.models.inspection_report import InspectionReport
    from app.models.elevator import Elevator
    from app.services.inspection_service import _is_null_deficiency
    from app.services.whatsapp_service import notify_dispatcher

    db = SessionLocal()
    try:
        today = date.today()
        open_reports = (
            db.query(InspectionReport)
            .filter(
                InspectionReport.report_status.in_(["OPEN", "PARTIAL"]),
                InspectionReport.elevator_id.isnot(None),
                InspectionReport.inspection_date.isnot(None),
            )
            .all()
        )

        for report in open_reports:
            elevator = db.query(Elevator).filter(Elevator.id == report.elevator_id).first()
            if not elevator:
                continue
            addr = f"{elevator.address}, {elevator.city}"
            last_note = report.notes or ""
            changed = False

            # ── Per-deficiency deadline alerts ────────────────────────────────
            for idx, deficiency in enumerate((report.deficiencies or [])):
                if deficiency.get("done") or _is_null_deficiency(deficiency):
                    continue
                deadline_days = deficiency.get("deadline_days")
                if not deadline_days or not report.inspection_date:
                    continue
                deadline_date = report.inspection_date + timedelta(days=deadline_days)
                days_left = (deadline_date - today).days
                desc_short = (deficiency.get("description") or "")[:60]

                if days_left <= 0:
                    marker = f"[def_overdue_{idx}_{deadline_date}]"
                    if marker not in last_note:
                        notify_dispatcher(
                            f"🔴 *ליקוי בוקר עבר מועד טיפול!*\n"
                            f"📍 {addr}\n"
                            f"📋 {desc_short}\n"
                            f"⏰ מועד לטיפול היה: {deadline_date.strftime('%d/%m/%Y')} ({abs(days_left)} ימים באיחור)\n"
                            f"🔗 טפל בדשבורד › דוחות בודק"
                        )
                        last_note = (last_note + f"\n{marker}").strip()
                        changed = True
                elif days_left <= 5:
                    marker = f"[def_warn_{idx}_{deadline_date}]"
                    if marker not in last_note:
                        notify_dispatcher(
                            f"⚠️ *ליקוי בוקר מתקרב לדד-ליין*\n"
                            f"📍 {addr}\n"
                            f"📋 {desc_short}\n"
                            f"⏰ יש לטפל עד: {deadline_date.strftime('%d/%m/%Y')} (עוד {days_left} ימים)\n"
                            f"🔗 טפל בדשבורד › דוחות בודק"
                        )
                        last_note = (last_note + f"\n{marker}").strip()
                        changed = True

            # ── Fallback: fixed-threshold escalation for reports without deadlines ─
            days_since = (today - report.inspection_date).days
            matched_threshold = None
            for threshold_days, color, label in _DEFICIENCY_THRESHOLDS:
                if days_since >= threshold_days:
                    matched_threshold = (threshold_days, color, label)

            if matched_threshold:
                threshold_days, color, label = matched_threshold
                marker = f"[escalation_{threshold_days}d]"
                if marker not in last_note:
                    notify_dispatcher(
                        f"{color} *ליקויי בודק ממתינים* ב{addr}\n"
                        f"⏳ {days_since} ימים ללא טיפול\n"
                        f"🔧 {report.deficiency_count} ליקויים מתסקיר {report.inspection_date.strftime('%d/%m/%Y')}\n"
                        f"📊 {label}\n"
                        f"🔗 טפל בדשבורד › דוחות בודק"
                    )
                    last_note = (last_note + f"\n{marker}").strip()
                    changed = True

            if changed:
                report.notes = last_note
                db.commit()

    except Exception as exc:
        logger.error("Inspection escalation check failed: %s", exc)
    finally:
        db.close()


def _send_morning_maintenance_alerts():
    """07:35 — send daily WhatsApp to managers for all open HIGH/CRITICAL maintenance calls."""
    from app.database import SessionLocal
    from app.models.service_call import ServiceCall
    from app.models.elevator import Elevator
    from app.services.whatsapp_service import notify_dispatcher

    db = SessionLocal()
    try:
        # All open HIGH/CRITICAL maintenance calls — sent daily regardless of prior notifications
        pending = db.query(ServiceCall).filter(
            ServiceCall.fault_type == "MAINTENANCE",
            ServiceCall.status.in_(["OPEN", "ASSIGNED"]),
            ServiceCall.priority.in_(["CRITICAL", "HIGH"]),
        ).all()

        if pending:
            from datetime import date
            today = date.today()
            lines = []
            for sc in pending:
                elev = db.get(Elevator, sc.elevator_id)
                addr = f"{elev.address}, {elev.city}" if elev else "כתובת לא ידועה"
                num_str = f"S{sc.call_number:05d} " if sc.call_number else ""
                if elev and elev.next_service_date:
                    days_late = (today - elev.next_service_date).days
                    date_info = f"— באיחור {days_late} ימים" if days_late > 0 else f"— מתוכנן {elev.next_service_date.strftime('%d/%m')}"
                else:
                    date_info = ""
                lines.append(f"• {num_str}{addr} {date_info}")
                # Clear one-time marker (no longer needed — we send daily)
                if sc.description and "[maint_pending_notify]" in sc.description:
                    sc.description = sc.description.replace("[maint_pending_notify]", "[maint_notified]")

            batched = f"🔴 *טיפול מונע דחוף — {len(lines)} מעליות*\n════════════════════\n" + "\n".join(lines)
            notify_dispatcher(batched)
            db.commit()
            logger.info("Morning maintenance alerts sent for %d calls", len(pending))
        else:
            logger.info("Morning maintenance alerts: no urgent open calls today")
    except Exception as exc:
        logger.error("Morning maintenance alert job failed: %s", exc)
    finally:
        db.close()


def _geocode_all_elevators():
    """
    Background job: geocode all elevators that are missing latitude/longitude.
    Runs once at startup (with a delay) and nightly to keep coords up to date.
    Rate-limited by geocode_address (1 req/sec) and uses in-memory cache.
    """
    from app.database import SessionLocal
    from app.models.elevator import Elevator
    from app.services.maps_service import geocode_address

    db = SessionLocal()
    try:
        elevators = (
            db.query(Elevator)
            .filter(
                (Elevator.latitude == None) | (Elevator.longitude == None)  # noqa: E711
            )
            .all()
        )
        if not elevators:
            logger.info("✅ All elevators already have coordinates.")
            return
        logger.info("📍 Geocoding %d elevators without coordinates...", len(elevators))
        updated = 0
        for elev in elevators:
            try:
                coords = geocode_address(elev.address, elev.city)
                if coords:
                    elev.latitude, elev.longitude = coords
                    db.commit()
                    updated += 1
            except Exception as exc:
                logger.warning("Geocode failed for %s %s: %s", elev.address, elev.city, exc)
        logger.info("📍 Geocoding complete: %d/%d elevators updated.", updated, len(elevators))
    except Exception as exc:
        logger.error("_geocode_all_elevators failed: %s", exc)
    finally:
        db.close()


def _run_auto_invoicing():
    """Daily 06:00 job: create invoices for contracts with auto_invoice=True."""
    from datetime import date, timedelta
    from app.database import SessionLocal
    from app.models.contract import Contract
    from app.models.invoice import Invoice
    from sqlalchemy import func

    FREQ_DAYS = {"MONTHLY": 30, "QUARTERLY": 90, "ANNUAL": 365}
    FREQ_LABEL = {"MONTHLY": "חודשית", "QUARTERLY": "רבעונית", "ANNUAL": "שנתית"}

    db = SessionLocal()
    try:
        today = date.today()
        contracts = (
            db.query(Contract)
            .filter(
                Contract.auto_invoice == True,  # noqa: E712
                Contract.status == "ACTIVE",
                Contract.invoice_frequency.isnot(None),
                Contract.monthly_price.isnot(None),
            )
            .all()
        )

        created = 0
        for contract in contracts:
            freq_days = FREQ_DAYS.get(contract.invoice_frequency)
            if not freq_days:
                continue
            if contract.last_invoiced_at:
                if today < contract.last_invoiced_at + timedelta(days=freq_days):
                    continue

            monthly = float(contract.monthly_price)
            multiplier = {"MONTHLY": 1, "QUARTERLY": 3, "ANNUAL": 12}.get(contract.invoice_frequency, 1)
            subtotal = round(monthly * multiplier, 2)
            vat_rate = float(contract.vat_percent or 18.0)
            vat_amount = round(subtotal * vat_rate / 100, 2)
            total = round(subtotal + vat_amount, 2)

            year = today.year
            count = db.query(func.count(Invoice.id)).filter(
                func.extract("year", Invoice.created_at) == year
            ).scalar() or 0
            number = f"INV-{year}-{count + 1:04d}"

            inv = Invoice(
                customer_id=contract.customer_id,
                contract_id=contract.id,
                number=number,
                issue_date=today,
                due_date=today + timedelta(days=int(contract.payment_terms or 30)),
                items=[{
                    "description": f"חיוב {FREQ_LABEL.get(contract.invoice_frequency, '')} — חוזה {contract.number}",
                    "quantity": 1,
                    "unit_price": subtotal,
                    "total": subtotal,
                }],
                subtotal=subtotal,
                vat_rate=vat_rate,
                vat_amount=vat_amount,
                total=total,
                status="DRAFT",
                notes=f"חשבונית אוטומטית לחוזה {contract.number}",
            )
            db.add(inv)
            contract.last_invoiced_at = today
            db.commit()
            created += 1
            logger.info("Auto-invoice %s created for contract %s (₪%.0f)", number, contract.number, total)

        if created:
            logger.info("Auto-invoicing complete: %d invoices created", created)

    except Exception as exc:
        logger.error("_run_auto_invoicing failed: %s", exc)
        db.rollback()
    finally:
        db.close()


def _auto_refresh_holidays():
    """Pull next year's Israeli holidays from Hebcal and merge into the DB + memory set.

    Runs Dec 1st so the new year's dates are ready before the calendar turns.
    """
    try:
        from datetime import date
        import json
        from app.database import SessionLocal
        from app.services.working_hours import fetch_holidays_from_hebcal
        from app.services import working_hours as wh_module
        from app.routers.settings import _get_setting, _set_setting

        next_year = date.today().year + 1
        new_dates = fetch_holidays_from_hebcal(next_year)

        db = SessionLocal()
        try:
            existing_raw = _get_setting(db, "holidays")
            existing_dict = {}
            if existing_raw:
                parsed = json.loads(existing_raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "date" in item:
                            existing_dict[item["date"]] = item.get("name", "")
                        elif isinstance(item, str):
                            existing_dict[item] = "חג ישן"
            
            for item in new_dates:
                existing_dict[item["date"]] = item["name"]

            merged = [{"date": d, "name": existing_dict[d]} for d in sorted(existing_dict.keys())]
            
            _set_setting(db, "holidays", json.dumps(merged))
            wh_module._HOLIDAYS = set(existing_dict.keys())
            logger.info(f"Auto-refreshed holidays: +{len(new_dates)} dates for {next_year}, total={len(merged)}")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"Holiday auto-refresh failed: {exc}")


def start_scheduler():
    """Start the APScheduler background scheduler."""
    from zoneinfo import ZoneInfo
    global _scheduler
    # All cron times are in Israel local time (Asia/Jerusalem)
    _scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Jerusalem"))
    _scheduler.add_job(_run_auto_invoicing,               "cron", hour=6,  minute=0)
    _scheduler.add_job(_run_nightly_maintenance,         "cron", hour=0,  minute=5,  day_of_week="sun,mon,tue,wed,thu,fri")
    _scheduler.add_job(_send_morning_maintenance_alerts, "cron", hour=7,  minute=35, day_of_week="sun,mon,tue,wed,thu,fri")
    _scheduler.add_job(_send_morning_location_requests,  "cron", hour=7,  minute=15, day_of_week="sun,mon,tue,wed,thu,fri")
    # WhatsApp replies now handled via webhook (POST /webhooks/whatsapp)
    # _scheduler.add_job(_poll_whatsapp_replies,               "interval", seconds=15)
    _scheduler.add_job(_poll_email_calls,                    "interval", seconds=60)
    _scheduler.add_job(_check_pending_assignment_timeouts,   "interval", seconds=60)
    _scheduler.add_job(_poll_inspection_emails,              "interval", hours=1)
    _scheduler.add_job(_scan_drive_inspections,              "interval", minutes=15)
    _scheduler.add_job(_check_location_reminders,            "interval", minutes=10)
    _scheduler.add_job(_check_monitoring_calls,              "cron",     hour=8,  minute=0)
    _scheduler.add_job(_check_inspection_deficiency_escalation, "interval", hours=6)
    # Geocode elevators missing coordinates: once 90s after startup + nightly at 02:00
    from datetime import timedelta
    _scheduler.add_job(
        _geocode_all_elevators, "date",
        run_date=datetime.now() + timedelta(seconds=90),
        id="geocode_startup", max_instances=1,
    )
    _scheduler.add_job(_geocode_all_elevators, "cron", hour=2, minute=0,
                       id="geocode_nightly", max_instances=1)
    # Fetch next year's holidays from Hebcal every Dec 1st at 03:00
    _scheduler.add_job(_auto_refresh_holidays, "cron", month=12, day=1, hour=3, minute=0,
                       id="holiday_refresh_annual", max_instances=1)
    _scheduler.start()
    logger.info("Background scheduler started (timezone: Asia/Jerusalem)")


def stop_scheduler():
    """Gracefully stop the scheduler on application shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
