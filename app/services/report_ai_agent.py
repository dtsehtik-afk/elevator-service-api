"""Report AI agent — answers natural-language questions about the database via Gemini."""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_PRIMARY = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_FALLBACK = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

_TOOLS = [{
    "function_declarations": [
        {
            "name": "query_data",
            "description": (
                "שלוף נתונים מהמסד. entity_type אפשרי: service_calls, elevators, customers, "
                "invoices, inventory, maintenance, contracts, leads, inspections. "
                "שדות נפוצים ב-service_calls: status (OPEN/ASSIGNED/IN_PROGRESS/RESOLVED/CLOSED), "
                "priority (CRITICAL/HIGH/MEDIUM/LOW), fault_type, city, created_at, resolved_at. "
                "שדות ב-maintenance: status (SCHEDULED/COMPLETED/OVERDUE/CANCELLED), technician_name, city, scheduled_date. "
                "שדות ב-elevators: status (ACTIVE/INACTIVE/UNDER_REPAIR), city, model, manufacturer, risk_score."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "entity_type": {"type": "STRING"},
                    "filters": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "field": {"type": "STRING"},
                                "op": {
                                    "type": "STRING",
                                    "description": "eq | neq | contains | starts_with | gt | gte | lt | lte | is_null | is_not_null",
                                },
                                "value": {"type": "STRING"},
                            },
                        },
                    },
                    "columns": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "sort_by": {"type": "STRING"},
                    "sort_dir": {"type": "STRING", "description": "asc | desc"},
                    "limit": {"type": "INTEGER"},
                },
                "required": ["entity_type"],
            },
        },
        {
            "name": "count_records",
            "description": "ספור רשומות בלי לשלוף את כולן — חוזר רק מספר.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "entity_type": {"type": "STRING"},
                    "filters": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "field": {"type": "STRING"},
                                "op": {"type": "STRING"},
                                "value": {"type": "STRING"},
                            },
                        },
                    },
                },
                "required": ["entity_type"],
            },
        },
        {
            "name": "system_overview",
            "description": "סיכום מהיר של מצב המערכת: קריאות פתוחות, טכנאים, קריאות קריטיות.",
            "parameters": {"type": "OBJECT", "properties": {}, "required": []},
        },
    ]
}]

_SYSTEM = """אתה עוזר AI לניהול חברת תחזוקת מעליות. יש לך גישה לבסיס הנתונים דרך כלים.
ענה בעברית בצורה תמציתית וברורה. אם שואלים על נתונים — השתמש בכלים לשליפת מידע עדכני.
כשמציגים רשימות ארוכות — סכם בטבלה קצרה או בנקודות עיקריות.
אם השאלה עמומה — עשה הנחה סבירה ועשה אותה ברורה בתשובה."""


def _run_tool(name: str, args: dict, db: Session) -> Any:
    if name in ("query_data", "count_records"):
        from app.services.report_builder import run_report, get_schemas
        etype = args.get("entity_type", "service_calls")
        schemas = get_schemas()
        if etype not in schemas:
            return {"error": f"entity_type לא מוכר: {etype}"}
        schema = schemas[etype]

        if name == "count_records":
            result = run_report(
                db=db, entity_type=etype,
                columns=["id"],
                filters=args.get("filters") or [],
                sort_by=None, sort_dir="desc",
                skip=0, limit=1,
                include_custom_fields=False,
            )
            return {"count": result["total"]}

        cols = args.get("columns") or schema["default_columns"]
        cols = [c for c in cols if c in schema["columns"]] or schema["default_columns"]
        result = run_report(
            db=db, entity_type=etype,
            columns=cols,
            filters=args.get("filters") or [],
            sort_by=args.get("sort_by"),
            sort_dir=args.get("sort_dir", "desc"),
            skip=0, limit=min(int(args.get("limit") or 20), 100),
            include_custom_fields=False,
        )
        return {"total": result["total"], "rows": result["rows"]}

    if name == "system_overview":
        from app.models.service_call import ServiceCall
        from app.models.technician import Technician
        open_c = db.query(ServiceCall).filter(ServiceCall.status == "OPEN").count()
        assigned_c = db.query(ServiceCall).filter(ServiceCall.status == "ASSIGNED").count()
        ip_c = db.query(ServiceCall).filter(ServiceCall.status == "IN_PROGRESS").count()
        crit_c = db.query(ServiceCall).filter(
            ServiceCall.status.in_(["OPEN", "ASSIGNED", "IN_PROGRESS"]),
            ServiceCall.priority == "CRITICAL",
        ).count()
        tech_total = db.query(Technician).count()
        tech_avail = db.query(Technician).filter(Technician.is_available == True).count()  # noqa: E712
        return {
            "open_calls": open_c,
            "assigned_calls": assigned_c,
            "in_progress_calls": ip_c,
            "critical_calls": crit_c,
            "technicians_total": tech_total,
            "technicians_available": tech_avail,
        }

    return {"error": f"כלי לא מוכר: {name}"}


async def answer_question(question: str, db: Session, api_key: str) -> str:
    """Answer a natural-language question using Gemini + live DB tools."""
    messages: list[dict] = [{"role": "user", "parts": [{"text": question}]}]
    payload: dict = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": messages,
        "tools": _TOOLS,
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
    }
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as http:
        for _ in range(6):
            resp = await http.post(f"{_PRIMARY}?key={api_key}", json=payload, headers=headers)
            if resp.status_code != 200:
                resp = await http.post(f"{_FALLBACK}?key={api_key}", json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error("Gemini error %d: %s", resp.status_code, resp.text[:300])
                return "שגיאה בתקשורת עם מודל השפה. נסה שוב."

            data = resp.json()
            candidate = data.get("candidates", [{}])[0]
            parts = candidate.get("content", {}).get("parts", [])
            tool_calls = [p for p in parts if "functionCall" in p]
            text_parts = [p for p in parts if "text" in p]

            if not tool_calls:
                return " ".join(p["text"] for p in text_parts) or "לא נמצאה תשובה."

            tool_results = []
            for tc in tool_calls:
                fn = tc["functionCall"]
                result = _run_tool(fn["name"], fn.get("args", {}), db)
                tool_results.append({
                    "functionResponse": {
                        "name": fn["name"],
                        "response": {"result": result},
                    }
                })

            messages.append({"role": "model", "parts": parts})
            messages.append({"role": "user", "parts": tool_results})
            payload["contents"] = messages

    return "לא הצלחתי לענות על השאלה."
