"""WhatsApp conversation log — admin only."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from collections import defaultdict
from app.database import get_db
from app.auth.dependencies import require_admin

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("")
def list_conversations(db: Session = Depends(get_db), _=Depends(require_admin)):
    from app.models.whatsapp_message import WhatsAppMessage
    from app.models.technician import Technician

    messages = db.query(WhatsAppMessage).order_by(WhatsAppMessage.timestamp.desc()).limit(1000).all()

    # Build technician name lookup
    techs = db.query(Technician).all()
    phone_to_name = {}
    for t in techs:
        digits = "".join(c for c in (t.phone or "") if c.isdigit())
        if digits.startswith("0") and len(digits) == 10:
            phone_to_name[f"972{digits[1:]}"] = t.name
        elif digits.startswith("972"):
            phone_to_name[digits] = t.name
        wdigits = "".join(c for c in (t.whatsapp_number or "") if c.isdigit())
        if wdigits.startswith("0") and len(wdigits) == 10:
            phone_to_name[f"972{wdigits[1:]}"] = t.name

    grouped = defaultdict(list)
    for m in reversed(messages):
        grouped[m.phone].append({
            "id": str(m.id),
            "direction": m.direction,
            "msg_type": m.msg_type,
            "text": m.text,
            "transcription": m.transcription,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        })

    result = []
    for phone, msgs in grouped.items():
        result.append({
            "phone": phone,
            "technician_name": phone_to_name.get(phone),
            "messages": msgs,
        })
    # Sort by most recent message
    result.sort(key=lambda x: x["messages"][-1]["timestamp"] if x["messages"] else "", reverse=True)
    return result
