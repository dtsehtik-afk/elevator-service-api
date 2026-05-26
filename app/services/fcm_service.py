"""
FCM Service — sends silent data-only push notifications via Firebase Admin SDK.

Used to wake the technician's app and request a fresh GPS location without
showing a visible notification to the user.

Requires the FIREBASE_SERVICE_ACCOUNT_JSON environment variable to be set to
the full content of the Firebase service account JSON file.  If the variable
is absent the service is gracefully disabled — no crash, just a warning.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_app = None


def _get_app():
    global _app
    if _app is not None:
        return _app
    try:
        import firebase_admin
        from firebase_admin import credentials

        cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        if not cred_json:
            logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON not set — FCM disabled")
            return None
        cred = credentials.Certificate(json.loads(cred_json))
        _app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialised (FCM enabled)")
        return _app
    except Exception as exc:
        logger.warning("FCM init failed: %s", exc)
        return None


def send_location_request(fcm_token: str) -> bool:
    """
    Send a silent data-only push to the given FCM token.

    The app wakes up (even when backgrounded), reads the ``type`` key from
    the data payload, gets fresh GPS, and POSTs it back to the server.

    Returns True on success, False on any failure (network, token invalid, etc.).
    """
    try:
        app = _get_app()
        if not app:
            return False
        from firebase_admin import messaging

        message = messaging.Message(
            data={"type": "location_request"},
            android=messaging.AndroidConfig(
                priority="high",
                ttl=60,  # discard if not delivered within 60 s
            ),
            token=fcm_token,
        )
        messaging.send(message)
        logger.debug("FCM location_request sent to token …%s", fcm_token[-8:])
        return True
    except Exception as exc:
        logger.warning("FCM send failed: %s", exc)
        return False
