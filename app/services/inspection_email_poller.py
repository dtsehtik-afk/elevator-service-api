"""
Scan Gmail for inspection report attachments (PDF / images).

Searches all emails since a given date for any that:
  - contain PDF or image attachments, AND
  - have subject / body / filename matching "תסקיר" or related keywords.

Each matching attachment is sent through process_inspection_report().
Emails are LEFT UNREAD — the mailbox is opened in read-only (EXAMINE) mode.
Processed email Message-IDs are recorded in inspection_email_scans to avoid
re-processing the same email on the next run.
"""

import email as _email_lib
import email.utils
import imaplib
import logging
import re
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header as _decode_header
from typing import Optional

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Keywords that mark an email (subject / body / filename) as inspection-related.
# All comparisons are case-insensitive.
_KEYWORDS = [
    "תסקיר", "תסקירים", "תסקיר בודק", "תסקיר מעלית",
    "taskir", "taskirim",
    "דוח בודק", "דו\"ח בודק",
    "ביקורת תקינות", "בדיקה תקופתית", "בודק מוסמך",
    "elevator inspection", "inspection report",
]

_VALID_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}
_EXT_TO_MIME = {
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".tiff": "image/tiff",
    ".tif":  "image/tiff",
}
_CT_TO_MIME = {
    "application/pdf": "application/pdf",
    "image/jpeg":      "image/jpeg",
    "image/jpg":       "image/jpeg",
    "image/png":       "image/png",
    "image/tiff":      "image/tiff",
    "image/tif":       "image/tiff",
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _decode_str(value: str) -> str:
    if not value:
        return ""
    parts = _decode_header(value)
    out = ""
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            out += chunk.decode(charset or "utf-8", errors="replace")
        else:
            out += chunk
    return out.strip()


def _has_keyword(text: str) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in _KEYWORDS)


def _get_body_text(msg) -> str:
    """Return a short snippet of the email's text body for keyword checking."""
    text = ""
    for part in msg.walk():
        ct = part.get_content_type()
        if ct not in ("text/plain", "text/html"):
            continue
        if "attachment" in str(part.get("Content-Disposition", "")):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                text += payload.decode(charset, errors="replace")[:800]
        except Exception:
            continue
    return text


def _extract_attachments(msg) -> list[dict]:
    """Return list of {filename, mime_type, data} for all PDF/image attachments."""
    results = []
    for part in msg.walk():
        cd = str(part.get("Content-Disposition", ""))
        ct = (part.get_content_type() or "").lower()

        filename = _decode_str(part.get_filename() or "")
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

        # Must be either a known MIME type or a known extension
        valid_mime = ct in _CT_TO_MIME
        valid_ext = ext in _VALID_EXTENSIONS
        if not valid_mime and not valid_ext:
            continue

        # Must be an attachment (or inline with a filename)
        if "attachment" not in cd and "inline" not in cd and not filename:
            continue

        mime = _CT_TO_MIME.get(ct) or _EXT_TO_MIME.get(ext, "application/octet-stream")

        try:
            data = part.get_payload(decode=True)
        except Exception:
            continue
        if not data:
            continue

        results.append({
            "filename": filename or f"attachment{ext}",
            "mime_type": mime,
            "data": data,
        })
    return results


# ── deduplication ──────────────────────────────────────────────────────────────

def _already_scanned(db, message_id: str) -> bool:
    from app.models.inspection_email_scan import InspectionEmailScan
    return db.query(InspectionEmailScan).filter(
        InspectionEmailScan.message_id == message_id
    ).first() is not None


def _record_scan(db, message_id: str, uid: str, subject: str, sender: str,
                 attachment_count: int, reports_created: int):
    from app.models.inspection_email_scan import InspectionEmailScan
    scan = InspectionEmailScan(
        message_id=message_id,
        gmail_uid=uid,
        subject=subject[:500] if subject else None,
        sender=sender[:200] if sender else None,
        attachment_count=attachment_count,
        reports_created=reports_created,
    )
    db.add(scan)
    try:
        db.commit()
    except Exception:
        db.rollback()


# ── default lookback ──────────────────────────────────────────────────────────

def _default_since_date(db) -> date:
    """
    First run (empty scan log): go back 3 months.
    Subsequent runs: last 7 days (the dedup table prevents re-processing).
    """
    from app.models.inspection_email_scan import InspectionEmailScan
    has_any = db.query(InspectionEmailScan.message_id).limit(1).first()
    if has_any is None:
        logger.info("📄 First inspection email scan — backfilling 3 months")
        return date.today() - timedelta(days=90)
    return date.today() - timedelta(days=7)


# ── main poller ────────────────────────────────────────────────────────────────

def poll_inspection_emails(db, since_date: Optional[date] = None) -> int:
    """
    Scan Gmail INBOX (in read-only mode — emails stay unread) for inspection
    report attachments.  Returns the number of reports successfully processed.
    """
    from app.config import get_settings
    from app.services.inspection_service import process_inspection_report

    s = get_settings()
    if not s.gmail_user or not s.gmail_app_password:
        logger.debug("Inspection email scan skipped — Gmail credentials not configured")
        return 0
    if not s.gemini_api_key:
        logger.debug("Inspection email scan skipped — GEMINI_API_KEY not configured")
        return 0

    if since_date is None:
        since_date = _default_since_date(db)

    since_str = since_date.strftime("%d-%b-%Y")
    processed = 0

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(s.gmail_user, s.gmail_app_password)

        # EXAMINE = read-only; emails are NOT marked \Seen when fetched
        mail.select("INBOX", readonly=True)

        _, id_data = mail.search(None, f"SINCE {since_str}")
        msg_ids = id_data[0].split()

        if not msg_ids:
            mail.logout()
            return 0

        logger.info(
            "📧 Inspection scan: %d total emails since %s", len(msg_ids), since_str
        )

        for uid in msg_ids:
            try:
                # Fetch only headers first — lightweight
                _, hdr_data = mail.fetch(
                    uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM MESSAGE-ID)])"
                )
                if not hdr_data or not hdr_data[0]:
                    continue
                hdr_msg = _email_lib.message_from_bytes(hdr_data[0][1])

                subject    = _decode_str(hdr_msg.get("Subject", ""))
                sender     = hdr_msg.get("From", "")
                message_id = hdr_msg.get("Message-ID", f"uid_{uid.decode()}__{since_str}")
                message_id = message_id.strip()

                # Skip already-processed emails
                if _already_scanned(db, message_id):
                    continue

                # Quick subject filter — fetch full message only if plausibly relevant
                # (also catches filenames, so we fetch even when subject is unclear)
                _, full_data = mail.fetch(uid, "(BODY.PEEK[])")
                if not full_data or not full_data[0]:
                    continue
                msg = _email_lib.message_from_bytes(full_data[0][1])

                attachments = _extract_attachments(msg)

                # Only proceed if there are valid attachments
                if not attachments:
                    # Record as scanned so we don't re-fetch next run
                    _record_scan(db, message_id, uid.decode(), subject, sender, 0, 0)
                    continue

                # Check inspection keywords in subject + first 800 chars of body + filenames
                filenames_text = " ".join(a["filename"] for a in attachments)
                body_text      = _get_body_text(msg)
                combined       = f"{subject} {body_text[:800]} {filenames_text}"

                if not _has_keyword(combined):
                    _record_scan(db, message_id, uid.decode(), subject, sender, 0, 0)
                    continue

                logger.info(
                    "📄 Inspection email: from=%s | subject=%s | attachments=%d",
                    sender, subject[:60], len(attachments),
                )

                email_reports = 0
                for att in attachments:
                    try:
                        result = process_inspection_report(
                            db=db,
                            file_bytes=att["data"],
                            mime_type=att["mime_type"],
                            file_name=att["filename"],
                            source="email",
                        )
                        status = result.get("status", "?")
                        logger.info(
                            "  ✅ %s → %s (report_id=%s)",
                            att["filename"], status, result.get("report_id", "—"),
                        )
                        email_reports += 1
                        processed     += 1
                    except Exception as exc:
                        logger.error("  ❌ Failed to process %s: %s", att["filename"], exc)
                        db.rollback()

                _record_scan(
                    db, message_id, uid.decode(), subject, sender,
                    len(attachments), email_reports,
                )

            except Exception as exc:
                logger.error("Error handling email uid=%s: %s", uid, exc)
                continue

        mail.close()
        mail.logout()

    except imaplib.IMAP4.error as exc:
        logger.error("IMAP error (inspection poller): %s", exc)
    except Exception as exc:
        logger.error("Inspection email poller unexpected error: %s", exc)

    if processed:
        logger.info("📄 Inspection email scan done — %d report(s) processed", processed)

    return processed
