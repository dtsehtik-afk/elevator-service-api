"""Green API — WhatsApp messaging service."""

import logging
from typing import Optional

import httpx

from app.config import get_settings

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


def _send_message(phone: str, text: str) -> bool:
    """
    Send a WhatsApp message via Green API.

    Args:
        phone: Israeli phone number (e.g. '0521234567' or '972521234567')
        text:  Message body

    Returns:
        True on success, False on failure.
    """
    instance_id = settings.greenapi_instance_id
    api_token   = settings.greenapi_api_token

    if not instance_id or not api_token:
        logger.warning("Green API not configured — WhatsApp message skipped")
        return False

    # Normalize phone to international format without '+'
    chat_id = _normalize_phone(phone)
    if not chat_id:
        logger.warning("Invalid phone number: %s", phone)
        return False

    url = f"{_BASE_URL}/waInstance{instance_id}/sendMessage/{api_token}"
    try:
        resp = httpx.post(
            url,
            json={"chatId": chat_id, "message": text},
            timeout=8,
        )
        if resp.status_code == 200 and resp.json().get("idMessage"):
            logger.info("WhatsApp sent to %s", phone)
            return True
        logger.warning("Green API error %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("WhatsApp send error: %s", exc)
    return False


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
) -> bool:
    """Send a new-call notification to a technician asking for confirmation."""
    fault  = _FAULT_LABEL.get(fault_type, fault_type)
    pri    = _PRIORITY_LABEL.get(priority, priority)

    message = (
        f"🔔 *קריאת שירות חדשה*\n"
        f"────────────────────\n"
        f"📍 *כתובת:* {address}, {city}\n"
        f"⚡ *תקלה:* {fault}\n"
        f"⚠️ *עדיפות:* {pri}\n"
        f"👤 *מתקשר:* {caller_name}\n"
        f"📞 *טל׳:* {caller_phone}\n"
        f"🚗 *זמן נסיעה משוער:* ~{travel_minutes} דקות\n"
        f"────────────────────\n"
        f"השב *1* לקבלת הקריאה ✅\n"
        f"השב *2* לדחייה ❌"
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
