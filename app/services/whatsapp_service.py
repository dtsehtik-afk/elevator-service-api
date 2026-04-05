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
    try:
        resp = httpx.post(url, json=payload, timeout=8)
        if resp.status_code == 200:
            msg_id = resp.json().get("idMessage")
            if msg_id:
                logger.info("WhatsApp sent to %s (msgId=%s)", phone, msg_id)
                return msg_id
        logger.warning("Green API error %s: %s", resp.status_code, resp.text[:200])
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
) -> bool:
    """Send a new-call notification to a technician asking for 1/2 confirmation."""
    fault  = _FAULT_LABEL.get(fault_type, fault_type)
    pri    = _PRIORITY_LABEL.get(priority, priority)
    ts     = _now_il()

    desc_line    = f"📝 *פירוט:* {description}\n" if description else ""
    caller_line  = f"👤 *מתקשר:* {caller_name}\n" if caller_name else ""
    phone_line   = f"📞 *טל׳:* {caller_phone}\n" if caller_phone else ""

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
        f"────────────────────\n"
        f"השב *1* לקבלת הקריאה ✅\n"
        f"השב *2* לדחייה ❌"
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

    maps_url = f"https://maps.google.com/?q={address}+{city}+ישראל"

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
        f"🔗 {maps_url}\n"
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


def notify_dispatcher_unassigned(phone: str, address: str, city: str, fault_type: str) -> bool:
    """Notify the dispatcher that no technician could be assigned."""
    fault = _FAULT_LABEL.get(fault_type, fault_type)
    message = (
        f"⚠️ *לא נמצא טכנאי פנוי*\n"
        f"קריאה בכתובת {address}, {city} ({fault}) "
        f"לא שובצה אוטומטית — נא לשבץ ידנית."
    )
    return _send_message(phone, message)
