"""Poll Gmail via IMAP for incoming service call emails from TELESERVICE@beepertalk.co.il."""

import email
import email.message
import email.utils
import html as html_mod
import imaplib
import json
import logging
import re
from datetime import date, datetime, timezone
from email.header import decode_header
from typing import Optional

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SENDER_FILTER = "TELESERVICE@beepertalk.co.il"  # legacy constant — overridden by settings

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
        # Check for both opening (<p>) and closing (</p>) tags
        if re.search(r"</?[a-zA-Z][^>]*>", plain):
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
        import httpx
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            json={
                "system_instruction": {"parts": [{"text": _GEMINI_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": f"גוף המייל:\n\n{body}"}]}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
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


# ── rescue blast ──────────────────────────────────────────────────────────────

def _send_rescue_blast(db, fields: dict, caller_name: str, caller_phone: str, description: str):
    """Send an emergency rescue alert to ALL active technicians."""
    import math
    from app.models.technician import Technician
    from app.services.whatsapp_service import notify_rescue_emergency

    technicians = (
        db.query(Technician)
        .filter(Technician.is_active == True, Technician.role == "TECHNICIAN")  # noqa: E712
        .all()
    )
    if not technicians:
        return

    # Find closest technician by GPS (if available)
    elev_lat = fields.get("_lat")
    elev_lon = fields.get("_lon")
    closest_name = None

    if elev_lat and elev_lon:
        def _dist(t):
            if t.current_latitude and t.current_longitude:
                dlat = float(t.current_latitude) - elev_lat
                dlon = float(t.current_longitude) - elev_lon
                return math.sqrt(dlat**2 + dlon**2)
            return float("inf")

        sorted_techs = sorted(technicians, key=_dist)
        if sorted_techs[0].current_latitude:
            closest_name = sorted_techs[0].name
    else:
        # No GPS — mark first available technician as closest
        available = [t for t in technicians if t.is_available]
        if available:
            closest_name = available[0].name

    for tech in technicians:
        phone = tech.whatsapp_number or tech.phone
        if not phone:
            continue
        notify_rescue_emergency(
            phone=phone,
            technician_name=tech.name,
            address=fields.get("address", ""),
            city=fields.get("city", ""),
            caller_name=caller_name,
            caller_phone=caller_phone,
            description=description,
            closest_tech_name=closest_name,
            is_closest=(tech.name == closest_name),
        )
    logger.info("🚨 Rescue blast sent to %d technicians", len(technicians))


# ── main poller ────────────────────────────────────────────────────────────────

def poll_emails(db) -> int:
    """
    Connect to Gmail, read unread service-call emails, create service calls.
    Returns the number of calls created.
    """
    from app.config import get_settings
    s = get_settings()

    user = s.gmail_user_calls or s.gmail_user
    password = s.gmail_app_password_calls or s.gmail_app_password
    if not user or not password:
        logger.debug("Email polling skipped — GMAIL_USER_CALLS / GMAIL_APP_PASSWORD_CALLS not set")
        return 0

    senders = [addr.strip() for addr in s.call_email_senders.split(",") if addr.strip()]
    imap_folder = s.gmail_imap_folder

    created = 0
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(user, password)

        # Select folder — quoted to handle spaces in Gmail folder names
        status, resp = mail.select(f'"{imap_folder}"')
        if status != "OK":
            # Fallback to INBOX if the configured folder doesn't exist
            logger.warning("📧 Could not select folder '%s' (%s) — falling back to INBOX", imap_folder, resp)
            mail.select("INBOX")

        # Only process emails received today or later — avoids replaying old backlog
        since_str = date.today().strftime("%d-%b-%Y")  # e.g. "20-Apr-2026"

        # Build OR query across all configured senders
        if len(senders) == 1:
            from_filter = f'FROM "{senders[0]}"'
        else:
            # IMAP OR is binary: (OR (FROM "a") (FROM "b"))
            def _or_chain(addresses):
                if len(addresses) == 1:
                    return f'FROM "{addresses[0]}"'
                return f'(OR (FROM "{addresses[0]}") ({_or_chain(addresses[1:])}))'
            from_filter = _or_chain(senders)

        # Search ALL matching emails (not just UNSEEN) — filter by Message-ID in DB instead
        # This prevents missing emails that were already read by a human before the poller ran
        _, all_ids = mail.search(None, f'({from_filter} SINCE {since_str})')
        total_count = len(all_ids[0].split()) if all_ids[0] else 0
        logger.warning("📧 [%s] today(%s): %d from senders | senders=%s",
                       imap_folder, since_str, total_count, ", ".join(senders))

        msg_ids = all_ids[0].split()
        if not msg_ids:
            mail.logout()
            return 0

        logger.info("📧 Found %d service-call email(s) since today", len(msg_ids))
        api_key = getattr(s, "gemini_api_key", "")

        from app.models.service_call_email_scan import ServiceCallEmailScan

        for mid in msg_ids:
            try:
                _, data = mail.fetch(mid, "(RFC822)")
                raw = data[0][1]
                msg = email.message_from_bytes(raw)

                # Skip already-processed emails (by Message-ID, regardless of SEEN flag)
                message_id = (msg.get("Message-ID") or f"uid-{mid.decode()}").strip()
                already = db.query(ServiceCallEmailScan).filter(
                    ServiceCallEmailScan.message_id == message_id
                ).first()
                if already:
                    continue

                # Extract email send time — use as created_at for the service call
                email_date: datetime | None = None
                try:
                    date_str = msg.get("Date", "")
                    if date_str:
                        email_date = email.utils.parsedate_to_datetime(date_str)
                        if email_date.tzinfo is None:
                            email_date = email_date.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

                body = _extract_body(msg)
                body = _html_to_text(body)

                logger.info("📧 Email body (first 400 chars): %s", body[:400])

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

                # Detect rescue/emergency (people trapped)
                _RESCUE_KEYWORDS = {"חילוץ", "לכודים", "לכוד", "כלואים", "כלוא", "תקועים", "נתקע"}
                combined_text = f"{fields.get('call_type','')} {fields.get('description','')}".lower()
                is_rescue = any(kw in combined_text for kw in _RESCUE_KEYWORDS)
                fault_type = "RESCUE" if is_rescue else fields["fault_type"]

                # Duplicate detection: same elevator + same fault type + open call today
                from app.models.service_call import ServiceCall
                from datetime import timezone as _tz
                _today = datetime.now(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                duplicate = db.query(ServiceCall).filter(
                    ServiceCall.elevator_id == elevator.id,
                    ServiceCall.fault_type == fault_type,
                    ServiceCall.created_at >= _today,
                    ServiceCall.status.notin_(["CLOSED", "RESOLVED"]),
                ).first()
                if duplicate:
                    logger.info(
                        "⏭️ Duplicate call for elevator %s (%s) — already open call %s, skipping",
                        elevator.id, fault_type, duplicate.id,
                    )
                    db.add(ServiceCallEmailScan(message_id=message_id))
                    db.commit()
                    continue

                call = ServiceCall(
                    elevator_id=elevator.id,
                    reported_by=reported_by,
                    description=description,
                    fault_type=fault_type,
                    priority="CRITICAL" if is_rescue else "MEDIUM",
                    status="OPEN",
                    **({"created_at": email_date} if email_date else {}),
                )
                db.add(call)
                db.add(ServiceCallEmailScan(message_id=message_id))
                db.commit()
                created += 1
                logger.info(
                    "✅ Service call created for elevator %s (%s %s) — reported by %s%s",
                    elevator.serial_number or elevator.id,
                    fields["city"], fields["address"], fields.get("name"),
                    " [RESCUE]" if is_rescue else "",
                )

                # Rescue: blast ALL technicians immediately
                if is_rescue:
                    try:
                        _send_rescue_blast(db, fields, caller_name, caller_phone, description)
                    except Exception as exc:
                        logger.error("Rescue blast failed: %s", exc)

                # Regular assignment — always ask for confirmation (1/2)
                assignment = None
                try:
                    from app.services import ai_assignment_agent
                    assignment = ai_assignment_agent.assign_with_confirmation(
                        db, call, needs_confirmation=True
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
