"""AI utilities router — text refinement and other AI helpers."""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.technician import Technician

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI"])

_PRIMARY = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_FALLBACK = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


class RefineTextRequest(BaseModel):
    text: str


@router.post("/refine-text", summary="Rewrite raw text as formal professional Hebrew")
async def refine_text(
    body: RefineTextRequest,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured")

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    prompt = (
        "You are a professional elevator technician report writer. "
        "Rewrite the following in formal, high-level Hebrew. "
        "Return only the rewritten text, no explanations. "
        f"Input: {text}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
    }
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=20.0) as http:
        resp = await http.post(f"{_PRIMARY}?key={api_key}", json=payload, headers=headers)
        if resp.status_code != 200:
            resp = await http.post(f"{_FALLBACK}?key={api_key}", json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("Gemini refine error %d: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=502, detail="AI service unavailable")

    data = resp.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    refined = " ".join(p["text"] for p in parts if "text" in p).strip()
    if not refined:
        raise HTTPException(status_code=502, detail="Empty response from AI")

    return {"refined": refined}
