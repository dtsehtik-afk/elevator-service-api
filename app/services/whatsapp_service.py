"""Green API — WhatsApp messaging service."""

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings

_IL_TZ = ZoneInfo("Asia/Jerusalem")

logger = logging.getLogger(__name__)
settings = get_settings()

_BASE_URL = "https://api.green-api.com"

# Priority Hebrew labels
_PRIORITY_LABEL = {
    "CRITICAL": "🔴 קריטי",
    "HIGH":     "🟠 גבוה",
    "MEDIUM":   "🟡 בינוני",
    "LOW":      "🟢 נמוך",
}

_FAULT_LABEL = {
    "STUCK":      "מעלית תקועה",
    "DOOR":       "תקלת דלת",
    "ELECTRICAL": "תקלה חשמלית",
    "MECHANICAL": "תקלה מכנית",
    "SOFTWARE":   "תקלת תוכנה",
    "OTHER":      "תקלה כללית",
}


def _send_message(phone: str, text: str, quoted_message_id: str = "") -> Optional[str]:
    """
    Send a WhatsApp message via Green API.

    Args:
        phone:              Israeli phone number (e.g. '0521234567' or '972521234567')
        text:               Message body
        quoted_message_id:  If set, send as a reply to this message ID

    Returns:
        idMessage string on success, None on failure.
        (bool-compatible: truthy on success, falsy on failure)
    """
    instance_id = settings.greenapi_instance_id
    api_token   = settings.greenapi_api_token

    if not instance_id or not api_token:
        logger.warning("Green API not configured — WhatsApp message skipped")
        return None

    # Normalize phone to international format without '+'
    chat_id = _normalize_phone(phone)
    if not chat_id:
        logger.warning("Invalid phone number: %s", phone)
        return None

    payload: dict = {"chatId": chat_id, "message": text}
    if quoted_message_id:
        payload["quotedMessageId"] = quoted_message_id

    url = f"{_BASE_URL}/waInstance{instance_id}/sendMessage/{api_token}"
    logger.warning("📤 Sending to %s (chatId=%s)", phone, chat_id)
    try:
        resp = httpx.post(url, json=payload, timeout=8)
        if resp.status_code == 200:
            msg_id = resp.json().get("idMessage")
            if msg_id:
                logger.warning("✅ Sent OK to %s (msgId=%s)", phone, msg_id)
                return msg_id
            logger.warning("⚠️ Green API 200 but no idMessage: %s", resp.text[:200])
        else:
            logger.warning("❌ Green API error %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("WhatsApp send error: %s", exc)
    return None


def _normalize_phone(phone: str) -> Optional[str]:
    """Convert Israeli phone to Green API chatId format (972XXXXXXXXX@c.us)."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("972") and len(digits) == 12:
        return f"{digits}@c.us"
    if digits.startswith("0") and len(digits) == 10:
        return f"972{digits[1:]}@c.us"
    if len(digits) == 9:
        return f"972{digits}@c.us"
    return None


# ── Public helpers ────────────────────────────────────────────────────────────

def _now_il() -> str:
    """Return current Israel date/time as 'DD/MM/YYYY HH:MM'."""
    return datetime.now(_IL_TZ).strftime("%d/%m/%Y %H:%M")


def notify_technician_new_call(
    phone: str,
    technician_name: str,
    call_id: str,
    address: str,
    city: str,
    fault_type: str,
    priority: str,
    caller_name: str,
    caller_phone: str,
    travel_minutes: int,
    description: str = "",
    tech_id: str = "",
) -> bool:
    """Send a new-call notification to a technician with a map confirmation link."""
    from app.config import get_settings
    fault  = _FAULT_LABEL.get(fault_type, fault_type)
    pri    = _PRIORITY_LABEL.get(priority, priority)
    ts     = _now_il()

    desc_line   = f"📝 *פירוט:* {description}\n" if description else ""
    caller_line = f"👤 *מתקשר:* {caller_name}\n" if caller_name else ""
    phone_line  = f"📞 *טל׳:* {caller_phone}\n" if caller_phone else ""

    base_url    = get_settings().app_base_url
    confirm_url = f"{base_url}/webhooks/my-calls/{tech_id}" if tech_id else ""
    confirm_line = (
        f"────────────────────\n"
        f"✅ לאישור/דחייה פתח:\n\n"
        f"{confirm_url}\n"
    ) if confirm_url else (
        f"────────────────────\n"
        f"השב *1* לקבלת הקריאה ✅\n"
        f"השב *2* לדחייה ❌"
    )

    message = (
        f"🔔 *קריאת שירות חדשה*\n"
        f"🗓 {ts}\n"
        f"────────────────────\n"
        f"📍 *כתובת:* {address}, {city}\n"
        f"⚡ *תקלה:* {fault}\n"
        f"{desc_line}"
        f"⚠️ *עדיפות:* {pri}\n"
        f"{caller_line}"
        f"{phone_line}"
        f"🚗 *זמן נסיעה משוער:* ~{travel_minutes} דקות\n"
        f"{confirm_line}"
    )
    return _send_message(phone, message)


def notify_technician_auto_assigned(
    phone: str,
    technician_name: str,
    address: str,
    city: str,
    fault_type: str,
    priority: str,
    caller_name: str,
    caller_phone: str,
    travel_minutes: int,
    description: str = "",
) -> bool:
    """
    Send a call-assignment notification WITHOUT asking for 1/2 confirmation.
    Used for email-originated calls where auto-assignment is applied.
    """
    fault  = _FAULT_LABEL.get(fault_type, fault_type)
    pri    = _PRIORITY_LABEL.get(priority, priority)
    ts     = _now_il()

    desc_line    = f"📝 *פירוט:* {description}\n" if description else ""
    caller_line  = f"👤 *מתקשר:* {caller_name}\n" if caller_name else ""
    phone_line   = f"📞 *טל׳:* {caller_phone}\n" if caller_phone else ""

    maps_url = f"https://maps.google.com/?q={address}+{city}"
    waze_url = f"https://waze.com/ul?q={address}+{city}"

    message = (
        f"📋 *שובצת לקריאת שירות*\n"
        f"🗓 {ts}\n"
        f"────────────────────\n"
        f"📍 *כתובת:* {address}, {city}\n"
        f"⚡ *תקלה:* {fault}\n"
        f"{desc_line}"
        f"⚠️ *עדיפות:* {pri}\n"
        f"{caller_line}"
        f"{phone_line}"
        f"🚗 *זמן נסיעה משוער:* ~{travel_minutes} דקות\n"
        f"🗺 גוגל מפות:\n{maps_url}\n"
        f"🚘 Waze:\n{waze_url}\n"
        f"────────────────────\n"
        f"בסיום הטיפול שלח: *דוח* + תיאור קצר"
    )
    return _send_message(phone, message)


def notify_technician_call_cancelled(phone: str, address: str, city: str) -> bool:
    """Notify a technician that a pending call was cancelled or reassigned."""
    message = (
        f"ℹ️ הקריאה בכתובת {address}, {city} "
        f"בוטלה או הועברה לטכנאי אחר."
    )
    return _send_message(phone, message)


def notify_rescue_emergency(
    phone: str,
    technician_name: str,
    address: str,
    city: str,
    caller_name: str,
    caller_phone: str,
    description: str,
    closest_tech_name: Optional[str],
    is_closest: bool,
) -> bool:
    """Send an urgent rescue alert to a technician (people trapped in elevator)."""
    ts = _now_il()
    maps_url = f"https://maps.google.com/?q={address}+{city}"
    waze_url = f"https://waze.com/ul?q={address}+{city}"

    closest_line = ""
    if closest_tech_name:
        if is_closest:
            closest_line = f"📌 *אתה הטכנאי הקרוב ביותר למיקום!*\n"
        else:
            closest_line = f"📌 *הטכנאי הקרוב ביותר:* {closest_tech_name}\n"

    caller_line = f"👤 *מתקשר:* {caller_name}\n" if caller_name else ""
    phone_line  = f"📞 *טל׳:* {caller_phone}\n" if caller_phone else ""
    desc_line   = f"📝 {description}\n" if description else ""

    message = (
        f"🚨🚨🚨 *חילוץ — אנשים לכודים במעלית* 🚨🚨🚨\n"
        f"🗓 {ts}\n"
        f"════════════════════\n"
        f"📍 *כתובת:* {address}, {city}\n"
        f"{desc_line}"
        f"{caller_line}"
        f"{phone_line}"
        f"{closest_line}"
        f"🗺 גוגל מפות:\n{maps_url}\n"
        f"🚘 Waze:\n{waze_url}\n"
        f"════════════════════\n"
        f"⚡ *נדרשת הגעה מיידית!*\n"
        f"השב *1* לאישור הגעה"
    )
    return _send_message(phone, message)


def _get_admin_phones_from_db() -> list[str]:
    """Get WhatsApp/phone numbers of all active ADMIN technicians from DB."""
    try:
        from app.database import SessionLocal
        from app.models.technician import Technician
        db = SessionLocal()
        try:
            admins = db.query(Technician).filter(
                Technician.role == "ADMIN",
                Technician.is_active == True,  # noqa: E712
            ).all()
            return [a.whatsapp_number or a.phone for a in admins if (a.whatsapp_number or a.phone)]
        finally:
            db.close()
    except Exception:
        return []


def notify_dispatcher(text: str) -> bool:
    """Send notification to ALL configured dispatcher/manager numbers + all ADMIN technicians in DB."""
    config_phones = [n.strip() for n in (settings.dispatcher_whatsapp or "").split(",") if n.strip()]
    db_phones = _get_admin_phones_from_db()
    # Merge and deduplicate (normalize to last-9-digits key)
    seen: set[str] = set()
    all_phones: list[str] = []
    for p in config_phones + db_phones:
        digits = "".join(c for c in p if c.isdigit())
        key = digits[-9:] if len(digits) >= 9 else digits
        if key and key not in seen:
            seen.add(key)
            all_phones.append(p)
    if not all_phones:
        return False
    success = False
    for number in all_phones:
        if _send_message(number, text):
            success = True
    return success


def notify_dispatcher_unassigned(phone: str, address: str, city: str, fault_type: str) -> bool:
    """Notify the dispatcher that no technician could be assigned."""
    fault = _FAULT_LABEL.get(fault_type, fault_type)
    message = (
        f"⚠️ *לא נמצא טכנאי פנוי*\n"
        f"קריאה בכתובת {address}, {city} ({fault}) "
        f"לא שובצה אוטומטית — נא לשבץ ידנית."
    )
    return _send_message(phone, message)


def notify_dispatcher_elevator_not_found(
    street: str,
    house_number: str,
    city: str,
    fault_type: str,
    caller_name: str,
    caller_phone: str,
    score: float,
    closest_address: str | None = None,
    closest_city: str | None = None,
) -> bool:
    """Notify the dispatcher that an incoming call could not be matched to any elevator."""
    fault = _FAULT_LABEL.get(fault_type, fault_type)
    address_str = f"{street} {house_number}".strip()

    lines = [
        "🔍 *קריאה נכנסה — לא נמצאה מעלית תואמת*",
        f"📍 כתובת שדווחה: {address_str}, {city}",
        f"🔧 תקלה: {fault}",
    ]
    if caller_name or caller_phone:
        caller = " | ".join(filter(None, [caller_name, caller_phone]))
        lines.append(f"📞 מתקשר: {caller}")
    if closest_address:
        lines.append(f"\n🏢 הכי קרוב שנמצא: {closest_address}, {closest_city or ''} ({score:.0%})")
        lines.append("❓ האם זו אותה כתובת? אם לא — האם להוסיף מעלית חדשה?")
    else:
        lines.append("❓ לא נמצאה מעלית — האם להוסיף מעלית חדשה?")

    lines.append("\n⚠️ *הקריאה לא נפתחה במערכת — נא לטפל ידנית*")

    return notify_dispatcher("\n".join(lines))
