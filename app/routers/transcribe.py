"""Transcription and AI text cleanup endpoints."""

import io
import logging
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import get_settings
settings = get_settings()
from app.database import get_db
from app.models.technician import Technician

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/transcribe", tags=["Transcribe"])


class CleanTextRequest(BaseModel):
    text: str


@router.post("", summary="Transcribe audio to Hebrew text")
async def transcribe_audio(
    file: UploadFile = File(...),
    _: Technician = Depends(get_current_user),
):
    """Accept audio (webm/mp4/wav/m4a) and return Hebrew transcription."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="קובץ שמע ריק")

    # Try Gemini first
    if settings.gemini_api_key:
        try:
            import base64
            import httpx
            b64 = base64.b64encode(audio_bytes).decode()
            mime = file.content_type or "audio/webm"
            payload = {
                "contents": [{
                    "parts": [
                        {"inline_data": {"mime_type": mime, "data": b64}},
                        {"text": "תמלל את ההקלטה הזו לעברית. החזר רק את הטקסט המתומלל, ללא הסברים נוספים."},
                    ]
                }]
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.gemini_api_key}"
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(url, json=payload)
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text:
                    return {"text": text}
        except Exception as exc:
            logger.warning("Gemini transcription failed: %s", exc)

    # Fallback: Whisper
    if settings.openai_api_key:
        try:
            import openai
            suffix = "." + (file.filename or "audio.webm").rsplit(".", 1)[-1]
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            oai = openai.OpenAI(api_key=settings.openai_api_key)
            with open(tmp_path, "rb") as f:
                result = oai.audio.transcriptions.create(
                    model="whisper-1", file=f, language="he"
                )
            return {"text": result.text.strip()}
        except Exception as exc:
            logger.error("Whisper transcription failed: %s", exc)

    raise HTTPException(status_code=503, detail="שירות תמלול אינו זמין — נדרש מפתח Gemini או OpenAI")


@router.post("/clean-text", summary="AI text cleanup: fix spelling, translate to Hebrew, remove profanity")
async def clean_text(
    body: CleanTextRequest,
    _: Technician = Depends(get_current_user),
):
    """Fix spelling, improve phrasing, remove profanity, translate to Hebrew."""
    if not body.text.strip():
        return {"text": body.text}

    if not settings.gemini_api_key:
        return {"text": body.text}

    try:
        import httpx
        prompt = (
            "אתה עורך לשון מקצועי. קיבלת טקסט של טכנאי מעליות שתיאר עבודה שביצע.\n"
            "המשימה שלך:\n"
            "1. תקן שגיאות כתיב ודקדוק\n"
            "2. נסח את הטקסט בצורה מקצועית ומכובדת\n"
            "3. מחק קללות, ביטויים גסים או לא מכובדים\n"
            "4. אם הטקסט ברוסית, ערבית או שפה אחרת — תרגם לעברית\n"
            "5. שמור על המשמעות המקורית ועל הפרטים הטכניים\n"
            "6. החזר רק את הטקסט המתוקן, ללא הסברים\n\n"
            f"טקסט לתיקון:\n{body.text}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.gemini_api_key}"
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(url, json=payload)
        if r.status_code == 200:
            cleaned = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return {"text": cleaned}
    except Exception as exc:
        logger.warning("clean_text failed: %s", exc)

    return {"text": body.text}
