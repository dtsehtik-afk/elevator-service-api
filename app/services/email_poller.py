"""Poll Gmail via IMAP for incoming service call emails from TELESERVICE@beepertalk.co.il."""

import email
import imaplib
import logging
import re
from email.header import decode_header
from typing import Optional

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SENDER_FILTER = "TELESERVICE@beepertalk.co.il"

# Maps Hebrew call-type strings to our fault_type enum values
_FAULT_TYPE_MAP = {
    "תקיעה": "STUCK",
    "תקועה": "STUCK",
    "דלת": "DOOR",
    "חשמל": "ELECTRICAL",
    "מכני": "MECHANICAL",
    "תוכנה": "SOFTWARE",
    "תקלה": "MECHANICAL",
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _extract_body(msg: email.message.Message) -> str:
    """Return the plain-text body of an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""


def _field(body: str, label: str) -> str:
    """Extract a single-line field value from the email body."""
    # e.g.  label = "שם"  →  r"שם:\s*(.+)"
    escaped = re.escape(label)
    m = re.search(rf"{escaped}:\s*(.+)", body)
    return m.group(1).strip() if m else ""


def _parse_email(body: str) -> dict:
    """Parse the beeper email body into a structured dict."""
    street_raw = _field(body, "רחוב")
    house      = _field(body, "מס' בית")

    # street_raw may contain the house number already (e.g. "ביאלק 1")
    # Use מס' בית if available and not already in street; otherwise keep as-is
    if house and house not in street_raw:
        address = f"{street_raw} {house}".strip()
    else:
        address = street_raw.strip()

    call_type_raw = _field(body, "סוג פניה")
    fault_type = "OTHER"
    for key, val in _FAULT_TYPE_MAP.items():
        if key in call_type_raw:
            fault_type = val
            break

    return {
        "name":       _field(body, "שם") or "לא ידוע",
        "city":       _field(body, "עיר"),
        "address":    address,
        "phone":      _field(body, "טלפון"),
        "floor":      _field(body, "קומה"),
        "call_type":  call_type_raw,
        "fault_type": fault_type,
        "context":    _field(body, "הקשר פניה"),
    }


# ── elevator matching ──────────────────────────────────────────────────────────

def _find_or_create_elevator(db, city: str, address: str):
    """
    Try to find an existing elevator by city + street.
    If not found, create a new record so the service call can be linked.
    """
    from app.models.elevator import Elevator

    if city:
        candidates = (
            db.query(Elevator)
            .filter(Elevator.city.ilike(f"%{city}%"))
            .all()
        )
        # Try street-name match (first word of address)
        street_word = address.split()[0] if address else ""
        for elev in candidates:
            if street_word and street_word in (elev.address or ""):
                return elev
        # City-only match — return first hit
        if candidates:
            return candidates[0]

    # Nothing found — create a placeholder elevator
    logger.info("📍 No elevator found for %s %s — creating placeholder", city, address)
    elev = Elevator(
        address=address or "—",
        city=city or "—",
        floor_count=1,
        status="ACTIVE",
    )
    db.add(elev)
    db.flush()  # get the ID before commit
    return elev


# ── main poller ────────────────────────────────────────────────────────────────

def poll_emails(db) -> int:
    """
    Connect to Gmail, read unread service-call emails, create service calls.
    Returns the number of calls created.
    """
    from app.config import get_settings
    s = get_settings()

    if not s.gmail_user or not s.gmail_app_password:
        logger.debug("Email polling skipped — GMAIL_USER / GMAIL_APP_PASSWORD not set")
        return 0

    created = 0
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(s.gmail_user, s.gmail_app_password)
        mail.select("INBOX")

        _, ids = mail.search(None, f'(UNSEEN FROM "{SENDER_FILTER}")')
        msg_ids = ids[0].split()
        if not msg_ids:
            mail.logout()
            return 0

        logger.info("📧 Found %d new service-call email(s)", len(msg_ids))

        for mid in msg_ids:
            try:
                _, data = mail.fetch(mid, "(RFC822)")
                raw = data[0][1]
                msg = email.message_from_bytes(raw)
                body = _extract_body(msg)
                fields = _parse_email(body)

                if not fields["city"] and not fields["address"]:
                    logger.warning("Could not extract address from email — skipping")
                    mail.store(mid, "+FLAGS", "\\Seen")
                    continue

                elevator = _find_or_create_elevator(db, fields["city"], fields["address"])

                description_parts = [f"סוג פניה: {fields['call_type']}"]
                if fields["context"]:
                    description_parts.append(fields["context"])
                description_parts.append(
                    f"כתובת: {fields['city']} {fields['address']}"
                    + (f" קומה {fields['floor']}" if fields["floor"] else "")
                )
                if fields["phone"]:
                    description_parts.append(f"טלפון: {fields['phone']}")
                description = " | ".join(description_parts)

                from app.models.service_call import ServiceCall
                call = ServiceCall(
                    elevator_id=elevator.id,
                    reported_by=fields["name"],
                    description=description,
                    fault_type=fields["fault_type"],
                    priority="MEDIUM",
                    status="OPEN",
                )
                db.add(call)
                db.commit()
                created += 1
                logger.info(
                    "✅ Service call created for elevator %s (%s %s) — reported by %s",
                    elevator.serial_number or elevator.id,
                    fields["city"], fields["address"], fields["name"],
                )

                # Send WhatsApp alert to dispatcher
                try:
                    from app.services.whatsapp_service import _send_message
                    if s.dispatcher_whatsapp:
                        _send_message(
                            s.dispatcher_whatsapp,
                            f"🚨 קריאת שירות חדשה\n"
                            f"📍 {fields['city']} {fields['address']}"
                            + (f" קומה {fields['floor']}" if fields["floor"] else "")
                            + f"\n👤 {fields['name']} | 📞 {fields['phone']}\n"
                            f"סוג: {fields['call_type']}",
                        )
                except Exception:
                    pass  # WhatsApp alert is best-effort

            except Exception as exc:
                logger.error("Failed to process email %s: %s", mid, exc)
                db.rollback()

            finally:
                # Mark as read regardless of success/failure to avoid re-processing
                mail.store(mid, "+FLAGS", "\\Seen")

        mail.close()
        mail.logout()

    except imaplib.IMAP4.error as exc:
        logger.error("IMAP login/connection error: %s", exc)
    except Exception as exc:
        logger.error("Email polling unexpected error: %s", exc)

    return created
