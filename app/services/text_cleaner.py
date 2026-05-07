"""AI text cleanup — fix spelling, improve phrasing, remove profanity, translate to Hebrew."""

import logging

logger = logging.getLogger(__name__)


def clean_tech_text(text: str) -> str:
    """
    Pass technician-submitted text through Gemini to:
    - Fix spelling / grammar
    - Improve to professional phrasing
    - Remove profanity / inappropriate language
    - Translate from Russian / Arabic / English → Hebrew

    Returns original text unchanged on any failure.
    """
    if not text or not text.strip():
        return text

    try:
        from app.config import get_settings
        settings = get_settings()
        if not settings.gemini_api_key:
            return text

        import requests
        prompt = (
            "אתה עורך לשון מקצועי לחברת תחזוקת מעליות.\n"
            "קיבלת טקסט של טכנאי שתיאר עבודה שביצע.\n"
            "המשימה שלך:\n"
            "1. תקן שגיאות כתיב ודקדוק בעברית\n"
            "2. נסח בצורה מקצועית ומכובדת\n"
            "3. מחק קללות, ביטויים גסים או לא מכובדים\n"
            "4. אם הטקסט ברוסית, ערבית, אנגלית או שפה אחרת — תרגם לעברית\n"
            "5. שמור על כל הפרטים הטכניים (מספרי חלקים, תקלות, פעולות)\n"
            "6. החזר אך ורק את הטקסט המתוקן — ללא הסברים, ללא כותרות\n\n"
            f"טקסט לתיקון:\n{text}"
        )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={settings.gemini_api_key}"
        )
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=10,
        )
        if response.status_code == 200:
            cleaned = (
                response.json()["candidates"][0]["content"]["parts"][0]["text"]
                .strip()
            )
            if cleaned:
                return cleaned
    except Exception as exc:
        logger.warning("clean_tech_text failed: %s", exc)

    return text
