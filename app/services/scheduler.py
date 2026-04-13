"""APScheduler background job runner — nightly maintenance + morning WhatsApp reminders."""

import logging
import tempfile
import os

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


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


def _run_nightly_maintenance():
    """Nightly job: mark overdue maintenances and send 30-day reminders."""
    from app.database import SessionLocal
    from app.services.maintenance_service import (
        mark_overdue_maintenances,
        send_upcoming_reminders,
    )

    db = SessionLocal()
    try:
        overdue_count = mark_overdue_maintenances(db)
        reminder_count = send_upcoming_reminders(db)
        logger.info(
            "Nightly maintenance job: %d overdue, %d reminders sent",
            overdue_count,
            reminder_count,
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
    """Morning job (08:00): send each active technician a WhatsApp with location request + motivational quote."""
    import random
    from app.database import SessionLocal
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message

    db = SessionLocal()
    try:
        technicians = (
            db.query(Technician)
            .filter(Technician.is_active == True, Technician.role == "TECHNICIAN")  # noqa: E712
            .all()
        )
        sent = 0
        for tech in technicians:
            phone = tech.whatsapp_number or tech.phone
            if not phone:
                continue

            # Reset daily GPS so first location triggers route build
            tech.current_latitude  = None
            tech.current_longitude = None

            from app.config import get_settings
            base_url = get_settings().app_base_url
            portal_link = f"{base_url}/app/tech/{tech.id}"
            quote = random.choice(_MORNING_QUOTES)
            gemini_key = getattr(get_settings(), "gemini_api_key", "")
            personal = _generate_personal_motivation(tech.name, gemini_key) if gemini_key else ""

            msg = (
                f"בוקר טוב {tech.name} 👋\n\n"
                f"{quote}\n"
                + (f"{personal}\n\n" if personal else "\n")
                +
                f"────────────────────\n"
                f"────────────────────\n"
                f"📍 *לשיתוף מיקום חי* — פתח את הקישור ואפשר גישה למיקום:\n\n"
                f"{base_url}/webhooks/track/{tech.id}\n\n"
                f"השאר את הדף פתוח — המיקום יתעדכן אוטומטית כל 5 דקות.\n\n"
                f"🔗 *פורטל הטכנאי שלך*:\n\n"
                f"{portal_link}\n\n"
                f"תודה ובהצלחה! 🙏"
            )
            if _send_message(phone, msg):
                sent += 1
        db.commit()
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
    logger.info("📋 %d call(s) resolved by %s", closed, tech.name)


def _handle_tech_reply(db, phone: str, text: str, pending: list, s) -> None:
    """
    Parse a technician's free-text reply using Gemini and accept/reject
    the relevant pending assignments.
    Falls back to classic 1/2 if only one pending call or Gemini unavailable.
    """
    from app.services import ai_assignment_agent

    # Classic 1/2: always act on the oldest pending assignment (FIFO)
    if text.strip() == "1":
        oldest = min(pending, key=lambda x: x["assigned_at"])
        ai_assignment_agent.confirm_assignment_by_id(db, phone, oldest["assignment_id"])
        return
    if text.strip() == "2":
        oldest = min(pending, key=lambda x: x["assigned_at"])
        ai_assignment_agent.reject_assignment_by_id(db, phone, oldest["assignment_id"])
        return

    # Gemini natural-language parsing
    gemini_key = getattr(s, "gemini_api_key", "")
    result = {"accept": [], "reject": []} if not gemini_key else _parse_reply_gemini(text, pending, gemini_key)

    if not result["accept"] and not result["reject"]:
        # Could not parse → treat as free text
        _handle_free_text(db, phone, text, s)
        return

    for aid in result["accept"]:
        ai_assignment_agent.confirm_assignment_by_id(db, phone, aid)
    for aid in result["reject"]:
        ai_assignment_agent.reject_assignment_by_id(db, phone, aid)


def _parse_reply_gemini(text: str, pending: list, api_key: str) -> dict:
    """
    Ask Gemini to match a technician's free-text reply to pending assignments.
    Returns {"accept": [assignment_id, ...], "reject": [assignment_id, ...]}.
    """
    import json as _json
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
                    if msg_kind == "liveLocationMessage":
                        # Live location → update technician's current position
                        loc = msg_data.get("liveLocationMessageData", {})
                        lat, lng = loc.get("latitude"), loc.get("longitude")
                        if lat and lng:
                            from app.models.technician import Technician
                            digits = "".join(c for c in phone if c.isdigit())
                            if digits.startswith("972"):
                                digits = "0" + digits[3:]
                            tech = (db.query(Technician)
                                    .filter(Technician.phone.contains(digits[-9:]) |
                                            Technician.whatsapp_number.contains(digits[-9:]))
                                    .first())
                            if tech:
                                prev_lat = tech.current_latitude
                                tech.current_latitude  = float(lat)
                                tech.current_longitude = float(lng)
                                db.commit()
                                logger.info("📍 Live location updated for %s", tech.name)

                                # First location of the day → send daily route
                                if not prev_lat:
                                    try:
                                        from app.services.route_service import send_route_to_technician
                                        send_route_to_technician(db, tech)
                                    except Exception as exc:
                                        logger.error("Route build failed for %s: %s", tech.name, exc)

                    elif msg_kind == "locationMessage":
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
                        if msg_kind == "extendedTextMessage":
                            text = msg_data.get("extendedTextMessageData", {}).get("text", "").strip()
                        else:
                            text = msg_data.get("textMessageData", {}).get("textMessage", "").strip()

                        logger.info("📩 Message from %s: %r", phone, text)
                        pending = ai_assignment_agent.get_pending_assignments_for_phone(db, phone)
                        if pending:
                            _handle_tech_reply(db, phone, text, pending, s)
                        elif len(text) > 0:
                            _handle_free_text(db, phone, text, s)
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


def _handle_free_text(db, phone: str, text: str, settings, is_reply: bool = False) -> None:
    """
    Route ANY free-text message from a technician through Gemini for intent detection.
    Always sends a reply — never silently ignores a message.
      - REPORT   → close active call with notes
      - TAKE     → self-assign an open call
      - QUESTION → answer via chat agent
      - IGNORE   → echo the message back and ask for clarification

    Args:
        is_reply: True when the message is a quoted/reply message — passes with_history to chat agent.
    """
    import urllib.request
    from app.models.technician import Technician
    from app.services.whatsapp_service import _send_message

    def _fallback_reply():
        """Reply when we genuinely can't understand the message."""
        _send_message(phone,
            f"❓ לא הבנתי את הבקשה.\n"
            f"האם התכוונת: *\"{text}\"*?\n\n"
            f"ניתן לשלוח:\n"
            f"• *דוח* + תיאור — לסגירת קריאה\n"
            f"• *לקחתי* + כתובת — לרישום עצמי\n"
            f"• שאלה חופשית — ואני אנסה לענות 🤖"
        )

    if not settings.gemini_api_key:
        # Fallback to keyword routing if Gemini not configured
        if any(w in text for w in ["דוח", "סיום", "סיימתי", "טיפלתי", "סגור"]):
            _handle_technician_report(db, phone, text)
        elif any(w in text for w in ["לקחתי", "קיבלתי", "אני לוקח", "אטפל", "הולך"]):
            _handle_self_assign(db, phone, text)
        else:
            _handle_chat_question_simple(db, phone, text, settings)
        return

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

    if not tech and not is_dispatcher:
        logger.warning("📵 Message from unregistered number %s — ignored", phone)
        return

    if is_dispatcher:
        from app.services.dispatcher_commands import handle_dispatcher_command
        handle_dispatcher_command(db, phone, text, settings)
        return

    try:
        import json, urllib.request as _ur, urllib.error
        _prompt = (
            "אתה מנתח כוונות של הודעות ווצאפ מטכנאים של חברת מעליות. "
            "החזר JSON בלבד (ללא הסברים) עם שדה 'intent' אחד מתוך:\n"
            "- REPORT   (הטכנאי מדווח שסיים טיפול / שולח סיכום)\n"
            "- TAKE     (הטכנאי מודיע שהוא לוקח/מטפל בקריאה)\n"
            "- QUESTION (שאלה על המערכת, מעלית, לקוח, היסטוריה, סטטוס)\n"
            "- IGNORE   (ברכה קצרה כמו 'אוקיי', 'תודה', 'סבבה', אמוג'י בלבד)\n"
            "ושדה 'extract' עם הטקסט הרלוונטי לפעולה (כתובת / שם לקוח / תיאור תקלה).\n\n"
            "חשוב: רק הודעות קצרות וחסרות תוכן כמו 'אוקיי', 'תודה', 'סבבה' הן IGNORE. "
            "כל הודעה שיש בה תוכן מהותי — אפילו אם לא ברור — תהיה QUESTION.\n\n"
            f"הודעה: {text}"
        )
        import urllib.request, json as _json
        import urllib.error
        _payload = json.dumps({
            "contents": [{"parts": [{"text": _prompt}]}],
            "generationConfig": {"maxOutputTokens": 150},
        }).encode()
        _req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.gemini_api_key}",
            data=_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(_req, timeout=10) as _r:
            _data = json.loads(_r.read())
        raw = _data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        parsed  = json.loads(raw)
        intent  = parsed.get("intent", "QUESTION")
        extract = parsed.get("extract", text)

        logger.info("🧠 Intent '%s' detected for msg: %s", intent, text[:60])

        if intent == "REPORT":
            _handle_technician_report(db, phone, extract or text)
        elif intent == "TAKE":
            _handle_self_assign(db, phone, extract or text)
        elif intent == "QUESTION":
            _handle_chat_question(db, phone, text, settings, with_history=is_reply)
        else:
            # IGNORE — short ack only (ok, thanks, 👍) — brief confirmation
            _send_message(phone, "👍")

    except Exception as exc:
        logger.error("Intent detection failed: %s — falling back to clarification", exc)
        _fallback_reply()


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
            f"🚗 ~{asgn.travel_minutes or '?'} דקות"
        )
        return

    # Generic fallback — tell user to add API key or explain what's available
    _send_message(phone,
        f"🤖 שאלות פתוחות דורשות מפתח ANTHROPIC_API_KEY.\n"
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
    except Exception as exc:
        logger.error("Chat agent error: %s", exc)
        _send_message(phone, "⚠️ שגיאה בעיבוד השאלה — נסה שוב מאוחר יותר.")


_REMINDER_AFTER_MINUTES  = 10   # send reminder if no reply after 10 min
_ESCALATE_AFTER_MINUTES  = 20   # reassign if still no reply after 20 min


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
        orphaned = [c for c in open_calls if c.id not in active_assignment_call_ids]

        if orphaned:
            logger.info("🔄 Found %d orphaned OPEN call(s) — attempting assignment", len(orphaned))
            from app.config import get_settings
            from app.services.whatsapp_service import notify_dispatcher_unassigned
            s = get_settings()

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
                        db, call, exclude_tech_ids=rejected_ids
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
                                )
                                # Tag the call so we don't alert again
                                call.description = (call.description or "") + " [dispatcher_notified]"
                                db.commit()
                                logger.info("📢 Dispatcher alerted for unassigned call %s", call.id)
                    else:
                        logger.info("✅ Orphaned call %s re-assigned", call.id)
                except Exception as exc:
                    logger.error("Failed to assign orphaned call %s: %s", call.id, exc)

        # ── Part A: PENDING_CONFIRMATION timeouts ─────────────────────────────
        pending = (
            db.query(Assignment)
            .filter(Assignment.status == "PENDING_CONFIRMATION")
            .all()
        )

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

            # ── Stage 2: escalate (20 min) ────────────────────────────────────
            if age_minutes >= _ESCALATE_AFTER_MINUTES:
                logger.warning(
                    "⏰ Assignment %s timed out (%.0f min) — escalating from %s",
                    assignment.id, age_minutes, tech.name,
                )

                assignment.status = "REJECTED"
                if call:
                    call.status = "OPEN"
                    db.add(AuditLog(
                        service_call_id=call.id,
                        changed_by="system",
                        old_status="ASSIGNED",
                        new_status="OPEN",
                        notes=f"{tech.name} לא השיב תוך {_ESCALATE_AFTER_MINUTES} דקות — הקריאה הועברה",
                    ))
                db.commit()

                if phone:
                    _send_message(
                        phone,
                        f"⏰ הקריאה ב-{addr} הועברה לטכנאי אחר\n"
                        f"(לא התקבלה תגובה תוך {_ESCALATE_AFTER_MINUTES} דקות)"
                    )

                # Collect all rejecters for this call and try next technician
                if call:
                    rejected_ids = [
                        a.technician_id
                        for a in db.query(Assignment).filter(
                            Assignment.service_call_id == call.id,
                            Assignment.status.in_(["REJECTED", "CANCELLED"]),
                        ).all()
                    ]
                    next_a = ai_assignment_agent.assign_with_confirmation(
                        db, call, exclude_tech_ids=rejected_ids
                    )
                    if not next_a:
                        from app.config import get_settings
                        from app.services.whatsapp_service import notify_dispatcher_unassigned
                        s = get_settings()
                        if s.dispatcher_whatsapp and elevator:
                            notify_dispatcher_unassigned(
                                s.dispatcher_whatsapp,
                                elevator.address, elevator.city, call.fault_type,
                            )

            # ── Stage 1: reminder (10 min, only once) ────────────────────────
            elif age_minutes >= _REMINDER_AFTER_MINUTES and not assignment.reminder_sent_at:
                logger.info(
                    "🔔 Sending reminder to %s for assignment %s (%.0f min)",
                    tech.name, assignment.id, age_minutes,
                )
                if phone:
                    _send_message(
                        phone,
                        f"🔔 *תזכורת — קריאה ממתינה לאישורך*\n"
                        f"📍 {addr}\n\n"
                        f"השב *1* לקבלה ✅ או *2* לדחייה ❌\n"
                        f"_(אי-מענה תוך {_ESCALATE_AFTER_MINUTES - _REMINDER_AFTER_MINUTES} דקות יעביר את הקריאה לטכנאי אחר)_"
                    )
                assignment.reminder_sent_at = now
                db.commit()

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
        if count:
            logger.info("📧 Email poller created %d new service call(s)", count)
    except Exception as exc:
        logger.error("Email poller job failed: %s", exc)
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
        cutoff = now - timedelta(minutes=20)

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
            tracking_url = f"{s.app_base_url}/webhooks/track/{tech.id}"
            _send_message(phone,
                f"📍 {tech.name}, המיקום שלך הפסיק להתעדכן.\n"
                f"פתח שוב את הקישור כדי להמשיך:\n{tracking_url}"
            )
            logger.warning("📍 Location reminder sent to %s", tech.name)
    except Exception as exc:
        logger.error("Location reminder job failed: %s", exc)
    finally:
        db.close()


def start_scheduler():
    """Start the APScheduler background scheduler."""
    from zoneinfo import ZoneInfo
    global _scheduler
    # All cron times are in Israel local time (Asia/Jerusalem)
    _scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Jerusalem"))
    _scheduler.add_job(_run_nightly_maintenance,             "cron",     hour=0,  minute=5)
    _scheduler.add_job(_send_morning_location_requests,      "cron",     hour=7,  minute=45)
    # WhatsApp replies now handled via webhook (POST /webhooks/whatsapp)
    # _scheduler.add_job(_poll_whatsapp_replies,               "interval", seconds=15)
    _scheduler.add_job(_poll_email_calls,                    "interval", seconds=60)
    _scheduler.add_job(_check_pending_assignment_timeouts,   "interval", seconds=60)
    _scheduler.add_job(_check_location_reminders,            "interval", minutes=5)
    _scheduler.start()
    logger.info("Background scheduler started (timezone: Asia/Jerusalem)")


def stop_scheduler():
    """Gracefully stop the scheduler on application shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
