"""APScheduler background job runner — nightly maintenance + morning WhatsApp reminders."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


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


def _send_morning_location_requests():
    """
    Morning job (07:15): send each active technician a WhatsApp asking
    them to share their live location for the day.
    """
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
            from app.config import get_settings
            base_url = get_settings().app_base_url
            portal_link = f"{base_url}/app/tech/{tech.id}"
            msg = (
                f"בוקר טוב {tech.name} 👋\n\n"
                f"לתיאום קריאות חכם לפי מיקום, אנא שתף *מיקום חי ל-8 שעות* בצ׳אט זה.\n\n"
                f"איך משתפים:\n"
                f"📎 → מיקום → שתף מיקום חי → 8 שעות\n\n"
                f"🔗 *פורטל הטכנאי שלך* (לדיווח על טיפולים):\n{portal_link}\n\n"
                f"תודה! 🙏"
            )
            if _send_message(phone, msg):
                sent += 1
        logger.info("Morning location request sent to %d/%d technicians", sent, len(technicians))
    except Exception as exc:
        logger.error("Morning location request job failed: %s", exc)
    finally:
        db.close()


def _handle_technician_report(db, phone: str, text: str):
    """Resolve the technician's active IN_PROGRESS call when they send a report."""
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

    # Find their active IN_PROGRESS call
    assignment = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id,
                Assignment.status == "CONFIRMED")
        .order_by(Assignment.assigned_at.desc())
        .first()
    )
    if not assignment:
        return

    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    if not call or call.status not in ("IN_PROGRESS", "ASSIGNED"):
        return

    # Extract report text (everything after "דוח ")
    notes = text
    for prefix in ("דוח ", 'דו"ח ', "סיום "):
        if notes.startswith(prefix):
            notes = notes[len(prefix):]
            break

    call.status       = "RESOLVED"
    call.resolved_at  = datetime.now(timezone.utc)
    call.resolution_notes = notes or "טופל על ידי טכנאי"
    assignment.status = "AUTO_ASSIGNED"  # completed

    audit = AuditLog(
        service_call_id=call.id,
        changed_by=tech.email,
        old_status="IN_PROGRESS",
        new_status="RESOLVED",
        notes=f"דו\"ח טכנאי: {notes or 'ללא הערות'}",
    )
    db.add(audit)
    db.commit()

    _send_message(
        tech.whatsapp_number or tech.phone,
        f"✅ הקריאה נסגרה בהצלחה. תודה {tech.name}!"
    )
    logger.info("📋 Call %s resolved by %s", call.id, tech.name)


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
            sender     = body.get("senderData", {}).get("sender", "")
            phone      = sender.replace("@c.us", "")

            if msg_type == "incomingMessageReceived":
                msg_data = body.get("messageData", {})
                msg_kind = msg_data.get("typeMessage", "")
                db = SessionLocal()
                try:
                    if msg_kind in ("locationMessage", "liveLocationMessage"):
                        loc = (msg_data.get("locationMessageData")
                               or msg_data.get("liveLocationMessageData", {}))
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
                                tech.current_latitude  = float(lat)
                                tech.current_longitude = float(lng)
                                db.commit()
                                logger.info("📍 Location updated for %s", tech.name)

                    elif msg_kind == "textMessage":
                        text = msg_data.get("textMessageData", {}).get("textMessage", "").strip()
                        if text == "1":
                            assignment = ai_assignment_agent.confirm_assignment(db, phone)
                            if assignment:
                                logger.info("✅ Assignment confirmed by %s", phone)
                        elif text == "2":
                            assignment = ai_assignment_agent.reject_assignment(db, phone)
                            if assignment:
                                logger.info("❌ Assignment rejected by %s", phone)
                        elif text.startswith("דוח") or text.startswith("דו\"ח") or text.startswith("סיום"):
                            # Technician filing a report — resolve call
                            _handle_technician_report(db, phone, text)
                finally:
                    db.close()

            # Acknowledge (delete) the notification so it won't appear again
            if receipt_id:
                httpx.delete(f"{delete_url}/{receipt_id}", timeout=5)

        except Exception as exc:
            logger.debug("WhatsApp poll error: %s", exc)
            break


def start_scheduler():
    """Start the APScheduler background scheduler."""
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_run_nightly_maintenance,        "cron",     hour=0,  minute=5)
    _scheduler.add_job(_send_morning_location_requests, "cron",     hour=7,  minute=15)
    _scheduler.add_job(_poll_whatsapp_replies,          "interval", seconds=15)
    _scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    """Gracefully stop the scheduler on application shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
