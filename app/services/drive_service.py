"""
Google Drive integration — optional storage backend for inspection reports.

If GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_DRIVE_FOLDER_ID are configured,
files are uploaded to Drive and a public viewer URL is returned.
Falls back gracefully when credentials are absent.
"""

import io
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_drive_service = None  # lazy singleton


def _get_service():
    global _drive_service
    if _drive_service is not None:
        return _drive_service
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from app.config import get_settings

        settings = get_settings()
        if not settings.google_service_account_json or not settings.google_drive_folder_id:
            return None

        info = json.loads(settings.google_service_account_json)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
        logger.info("Google Drive service initialized")
        return _drive_service
    except Exception as exc:
        logger.error("Drive init failed: %s", exc)
        return None


def is_configured() -> bool:
    """Return True if Drive credentials are available."""
    from app.config import get_settings
    s = get_settings()
    return bool(s.google_service_account_json and s.google_drive_folder_id)


def upload_file(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    subfolder: str = "",
) -> Optional[str]:
    """
    Upload a file to the configured Drive folder.
    Returns the Drive file ID, or None on failure.
    """
    svc = _get_service()
    if not svc:
        return None
    try:
        from googleapiclient.http import MediaIoBaseUpload
        from app.config import get_settings

        folder_id = get_settings().google_drive_folder_id

        # Optionally create/find a subfolder (year or elevator name)
        parent_id = _ensure_subfolder(svc, folder_id, subfolder) if subfolder else folder_id

        metadata = {"name": file_name, "parents": [parent_id]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)
        file = svc.files().create(body=metadata, media_body=media, fields="id").execute()
        file_id = file.get("id")
        logger.info("Uploaded %s to Drive → %s", file_name, file_id)
        return file_id
    except Exception as exc:
        logger.error("Drive upload failed: %s", exc)
        return None


def get_viewer_url(file_id: str) -> str:
    """Return an embeddable Google Drive viewer URL for the given file ID."""
    return f"https://drive.google.com/file/d/{file_id}/view"


def get_download_bytes(file_id: str) -> Optional[bytes]:
    """Download file content from Drive (used for scheduled scan processing)."""
    svc = _get_service()
    if not svc:
        return None
    try:
        from googleapiclient.http import MediaIoBaseDownload

        req = svc.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()
    except Exception as exc:
        logger.error("Drive download failed for %s: %s", file_id, exc)
        return None


def list_folder_files(processed_ids: set) -> list[dict]:
    """
    Return files in the Drive folder that haven't been processed yet.
    Each entry: {id, name, mimeType, createdTime}
    """
    svc = _get_service()
    if not svc:
        return []
    try:
        from app.config import get_settings

        folder_id = get_settings().google_drive_folder_id
        query = (
            f"'{folder_id}' in parents"
            " and mimeType != 'application/vnd.google-apps.folder'"
            " and trashed = false"
        )
        result = (
            svc.files()
            .list(
                q=query,
                fields="files(id,name,mimeType,createdTime)",
                orderBy="createdTime desc",
                pageSize=50,
            )
            .execute()
        )
        files = result.get("files", [])
        return [f for f in files if f["id"] not in processed_ids]
    except Exception as exc:
        logger.error("Drive list failed: %s", exc)
        return []


def _ensure_subfolder(svc, parent_id: str, name: str) -> str:
    """Find or create a subfolder inside parent_id. Returns folder ID."""
    try:
        query = (
            f"'{parent_id}' in parents"
            f" and name = '{name}'"
            " and mimeType = 'application/vnd.google-apps.folder'"
            " and trashed = false"
        )
        res = svc.files().list(q=query, fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
        folder = svc.files().create(body=meta, fields="id").execute()
        return folder["id"]
    except Exception:
        return parent_id
