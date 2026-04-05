"""Poll Gmail via IMAP for incoming service call emails from TELESERVICE@beepertalk.co.il."""

import email
import email.message
import html as html_mod
import imaplib
import json
import logging
import re
from datetime import date
from email.header import decode_header
from typing import Optional

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SENDER_FILTER = "TELESERVICE@beepertalk.co.il"

# Maps Hebrew call-type strings to our fault_type enum values
_FAULT_TYPE_MAP = {
    "תקיעה":  "STUCK",
    "תקועה":  "STUCK",
    "דלת":    "DOOR",
    "חשמל":   "ELECTRICAL",
    "מכני":   "MECHANICAL",
    "תוכנה":  "SOFTWARE",
    "תקלה":   "MECHANICAL",
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _html_to_text(html: str) -> str:
    """Convert HTML email body to clean plain text."""
    # Decode HTML entities first (&#39; → ', &amp; → &, etc.)
    text = html_mod.unescape(html)
    # Replace block-level tags with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|tr|li|h\d)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(?:p|div|tr|li|h\d)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip ALL remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Clean up remaining entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # Collapse multiple blank lines / spaces
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_body(msg: email.message.Message) -> str:
    """Return the plain-text body of an email message (handles HTML-only emails)."""
    plain = None
    html = None

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            if ct == "text/plain" and plain is None:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                plain = payload.decode(charset, errors="replace")
            elif ct == "text/html" and html is None:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace")
    else:
        ct = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        body = payload.decode(charset, errors="replace")
        if ct == "text/html":
            html = body
        else:
            plain = body

    # Prefer plain text if available, but always clean it too
    if plain:
        # Even "plain text" emails may contain inline HTML tags from bad generators
        if re.search(r"<[a-zA-Z][^>]*>", plain):
            return _html_to_text(plain)
        return html_mod.unescape(plain).strip()
    if html:
        return _html_to_text(html)
    return ""


def _field(body: str, label: str) -> str:
    """Extract a single-line field value from the email body (strips inline HTML)."""
    escaped = re.escape(label)
    m = re.search(rf"{escaped}[:\s]\s*(.+)", body)
    if not m:
        return ""
    value = m.group(1).strip()
    # Extra safety: strip any leftover HTML tags or entities from the captured value
    value = re.sub(r"<[^>]+>", "", value)
    value = html_mod.unescape(value).strip()
    # Remove trailing pipe characters (common in beepertalk format)
    value = value.rstrip(" |").strip()
    return value


# ── Gemini-powered smart parser ────────────────────────────────────────────────

_GEMINI_PROMPT = (
    "אתה מנתח מיילים של קריאות שירות למעליות שמגיעות מחברת beepertalk. "
    "המיילים כתובים בעברית ועשויים להכיל אימוג'ים כמו 📍 לכתובת, 👤 לשם, 📞 לטלפון. "
    "חלץ את השדות הבאים והחזר JSON בלבד, ללא הסברים, ללא markdown:\n"
    "{\n"
    '  "name": "שם המתקשר",\n'
    '  "city": "שם העיר בלבד",\n'
    '  "address": "שם הרחוב + מספר בית (ללא שם עיר)",\n'
    '  "phone": "מספר טלפון ספרות בלבד",\n'
    '  "floor": "מספר קומה או ריקה",\n'
    '  "call_type": "סוג הפניה כפי שנכתב במייל",\n'
    '  "fault_type": "STUCK|DOOR|ELECTRICAL|MECHANICAL|SOFTWARE|OTHER",\n'
    '  "description": "תיאור קצר של התקלה"\n'
    "}\n\n"
    "fault_type בחר לפי: תקועה/תקיעה→STUCK, דלת→DOOR, חשמל→ELECTRICAL, "
    "מכני/ג'נרטור→MECHANICAL, תוכנה→SOFTWARE, אחר→OTHER.\n"
    "אם שדה לא קיים — החזר מחרוזת ריקה."
)


def _parse_with_gemini(body: str, api_key: str) -> Optional[dict]:
    """
    Use Gemini to extract structured fields from an arbitrary email body.
    Returns a dict with keys: name, city, address, phone, floor, call_type, fault_type
    or None on failure.
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=_GEMINI_PROMPT,
        )
        resp = model.generate_content(f"גוף המייל:\n\n{body}")
        raw = resp.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw.strip())

    except Exception as exc:
        logger.error("Gemini email parsing failed: %s", exc)
        return None


# ── Regex-based fallback parser ────────────────────────────────────────────────

def _parse_email_regex(body: str) -> dict:
    """Parse the beeper email body into a structured dict (regex-based fallback)."""

    # ── Try "📍 {city} {street} {number}" first-line format ─────────────────
    # beepertalk sometimes puts the full address on one line after 📍
    loc_match = re.search(r"📍\s+(.+?)(?:\n|$)", body)
    loc_line = loc_match.group(1).strip() if loc_match else ""

    # ── Traditional "רחוב: / עיר:" field format ─────────────────────────────
    street_raw = _field(body, "רחוב")
    floor_raw  = _field(body, "קומה")
    house_raw  = _field(body, "מס' בית") or _field(body, "מספר בית")
    house_num  = re.sub(r"קומה.*", "", house_raw).strip()

    if street_raw:
        # Traditional format — use רחוב field
        if house_num and house_num not in street_raw:
            address = f"{street_raw} {house_num}".strip()
        else:
            address = street_raw.strip()
        # City from עיר field
        city_raw = _field(body, "עיר")
        city = city_raw.split("|")[0].strip()
        city = re.sub(r"[📞📍👤].*", "", city).strip()
    elif loc_line:
        # 📍 line format: "טבריה שזר 27" — last word may be number, then street, then city
        # Strategy: use עיר field for city if available, otherwise take first token of loc_line
        city_raw = _field(body, "עיר")
        city = city_raw.split("|")[0].strip() if city_raw else ""
        city = re.sub(r"[📞📍👤|].*", "", city).strip()

        if city and city in loc_line:
            # Remove the city from the loc_line to get the address
            address = loc_line.replace(city, "").strip()
        else:
            # Fallback: first word = city, rest = address
            parts = loc_line.split()
            if len(parts) > 1:
                city = parts[0]
                address = " ".join(parts[1:])
            else:
                city = ""
                address = loc_line
    else:
        # Nothing useful found
        city_raw = _field(body, "עיר")
        city = city_raw.split("|")[0].strip()
        city = re.sub(r"[📞📍👤].*", "", city).strip()
        address = ""

    call_type_raw = _field(body, "סוג פניה") or _field(body, "סוג")
    fault_type = "OTHER"
    for key, val in _FAULT_TYPE_MAP.items():
        if key in call_type_raw:
            fault_type = val
            break

    name = _field(body, "שם")
    if not name:
        m = re.search(r"👤\s*([^\n|📞]+)", body)
        name = m.group(1).strip() if m else ""
    # Clean up name (remove trailing city info like "עיר: ...")
    name = re.split(r"\s*עיר\s*[:\-]", name)[0].strip()

    phone = _field(body, "טלפון")
    if not phone:
        m = re.search(r"[|]?\s*📞\s*([\d\-\s]+)", body)
        phone = m.group(1).strip() if m else ""
    # Keep only digits and hyphens
    phone = re.sub(r"[^\d\-]", "", phone)

    # Floor: extract from "קומה" field or from house_raw if it contained floor text
    floor = floor_raw
    if not floor and "קומה" in house_raw:
        m = re.search(r"קומה\s*(\w+)", house_raw)
        floor = m.group(1) if m else ""

    return {
        "name":        name or "לא ידוע",
        "city":        city,
        "address":     address,
        "phone":       phone,
        "floor":       floor,
        "call_type":   call_type_raw,
        "fault_type":  fault_type,
        "description": "",
    }


def _parse_email(body: str, api_key: str = "") -> Optional[dict]:
    """
    Parse email body into structured fields using Gemini.
    Returns None if Gemini is unavailable or parsing fails.
    """
    if not api_key:
        logger.error(
            "GEMINI_API_KEY is not set — cannot parse email. "
            "Set GEMINI_API_KEY in .env to enable email processing."
        )
        return None

    result = _parse_with_gemini(body, api_key)
    if not result:
        logger.error("Claude failed to parse email body — skipping this email.")
        return None

    # Normalise fault_type in case Claude returned something unexpected
    valid = {"STUCK", "DOOR", "ELECTRICAL", "MECHANICAL", "SOFTWARE", "OTHER"}
    if result.get("fault_type") not in valid:
        raw = result.get("fault_type", "") + result.get("call_type", "")
        result["fault_type"] = "OTHER"
        for key, val in _FAULT_TYPE_MAP.items():
            if key in raw:
                result["fault_type"] = val
                break

    return result


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

    # Nothing found — create a placeholder and alert dispatcher
    logger.info("📍 No elevator found for %s %s — creating placeholder", city, address)
    elev = Elevator(
        address=address or "—",
        city=city or "—",
        floor_count=1,
        status="ACTIVE",
    )
    db.add(elev)
    db.flush()

    # Alert dispatcher: unknown address
    try:
        from app.config import get_settings
        from app.services.whatsapp_service import _send_message
        s = get_settings()
        if s.dispatcher_whatsapp:
            _send_message(
                s.dispatcher_whatsapp,
                f"⚠️ *קריאה מכתובת לא מוכרת*\n"
                f"📍 {city}, {address}\n"
                f"המערכת יצרה מעלית חדשה אוטומטית — נא לאמת ולעדכן."
            )
    except Exception:
        pass

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

        # Only process emails received today or later — avoids replaying old backlog
        since_str = date.today().strftime("%d-%b-%Y")  # e.g. "31-Mar-2026"
        _, ids = mail.search(None, f'(UNSEEN FROM "{SENDER_FILTER}" SINCE {since_str})')
        msg_ids = ids[0].split()
        if not msg_ids:
            mail.logout()
            return 0

        logger.info("📧 Found %d new service-call email(s)", len(msg_ids))
        api_key = getattr(s, "gemini_api_key", "")

        for mid in msg_ids:
            try:
                _, data = mail.fetch(mid, "(RFC822)")
                raw = data[0][1]
                msg = email.message_from_bytes(raw)
                body = _extract_body(msg)

                logger.debug("📧 Email body (first 300 chars): %s", body[:300])

                fields = _parse_email(body, api_key=api_key)

                if fields is None:
                    logger.warning("Email parsing returned no data — skipping (see above for reason)")
                    mail.store(mid, "+FLAGS", "\\Seen")
                    continue

                if not fields.get("city") and not fields.get("address"):
                    logger.warning("Could not extract address from email — skipping")
                    mail.store(mid, "+FLAGS", "\\Seen")
                    continue

                elevator = _find_or_create_elevator(db, fields["city"], fields["address"])

                # Build a clean human-readable description
                desc_parts = []
                if fields.get("call_type"):
                    desc_parts.append(f"סוג פניה: {fields['call_type']}")
                if fields.get("description"):
                    desc_parts.append(fields["description"])
                if fields.get("floor"):
                    desc_parts.append(f"קומה: {fields['floor']}")
                description = " | ".join(desc_parts)

                # reported_by format expected by _extract_caller / _extract_phone
                caller_name  = fields.get("name", "לא ידוע")
                caller_phone = fields.get("phone", "")
                if caller_phone:
                    reported_by = f"{caller_name} | טל׳: {caller_phone}"
                else:
                    reported_by = caller_name

                from app.models.service_call import ServiceCall
                call = ServiceCall(
                    elevator_id=elevator.id,
                    reported_by=reported_by,
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
                    fields["city"], fields["address"], fields.get("name"),
                )

                # Run AI assignment — email calls are auto-confirmed (no 1/2 needed)
                assignment = None
                try:
                    from app.services import ai_assignment_agent
                    assignment = ai_assignment_agent.assign_with_confirmation(
                        db, call, needs_confirmation=False
                    )
                except Exception as exc:
                    logger.error("AI assignment failed for email-polled call: %s", exc)

                # Fall back: notify dispatcher if no technician could be assigned
                if not assignment:
                    try:
                        from app.services.whatsapp_service import notify_dispatcher_unassigned
                        if s.dispatcher_whatsapp:
                            notify_dispatcher_unassigned(
                                s.dispatcher_whatsapp,
                                fields["address"],
                                fields["city"],
                                fields["fault_type"],
                            )
                    except Exception:
                        pass  # best-effort

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
