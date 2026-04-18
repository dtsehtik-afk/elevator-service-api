"""Authentication router — login endpoint."""

import random
import time
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.schemas import TokenResponse
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.technician import Technician

router = APIRouter()
_limiter = Limiter(key_func=get_remote_address)

# In-memory OTP store: phone_normalized -> (otp, expires_at)
_otp_store: dict[str, tuple[str, float]] = {}
_OTP_TTL = 900  # 15 minutes


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
    description="Authenticate with email and password. Returns a JWT Bearer token.",
)
@_limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate user and return JWT access token."""
    user = (
        db.query(Technician)
        .filter(func.lower(Technician.email) == form_data.username.lower().strip())
        .first()
    )
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token)


@router.post("/forgot-password", summary="Request password reset OTP via WhatsApp")
@_limiter.limit("5/minute")
def forgot_password(
    request: Request,
    phone: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Generate a 6-digit OTP and send it via WhatsApp to the technician's phone."""
    from app.services.whatsapp_service import _normalize_phone, _send_message

    # Find technician by whatsapp_number or phone
    digits = "".join(c for c in phone if c.isdigit())
    user: Optional[Technician] = None
    for tech in db.query(Technician).filter(Technician.is_active == True).all():  # noqa: E712
        candidate = tech.whatsapp_number or tech.phone or ""
        c_digits = "".join(c for c in candidate if c.isdigit())
        # Match on last 9 digits
        if c_digits and digits and c_digits[-9:] == digits[-9:]:
            user = tech
            break

    # Always return 200 to avoid phone enumeration
    if not user:
        return {"detail": "אם המספר קיים במערכת, ישלח קוד לווצאפ"}

    otp = f"{random.randint(0, 999999):06d}"
    chat_phone = user.whatsapp_number or user.phone
    normalized = _normalize_phone(chat_phone)
    if normalized:
        key = normalized  # use chatId as key
        _otp_store[key] = (otp, time.time() + _OTP_TTL)
        _send_message(
            chat_phone,
            f"🔐 *קוד לאיפוס סיסמה*\n\nהקוד שלך: *{otp}*\n\nהקוד תקף ל-15 דקות.",
        )

    return {"detail": "אם המספר קיים במערכת, ישלח קוד לווצאפ"}


@router.post("/reset-password", summary="Reset password using OTP")
@_limiter.limit("10/minute")
def reset_password(
    request: Request,
    phone: str = Body(...),
    otp: str = Body(...),
    new_password: str = Body(...),
    db: Session = Depends(get_db),
):
    """Verify OTP and update the technician's password."""
    from app.services.whatsapp_service import _normalize_phone

    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="הסיסמה חייבת להכיל לפחות 6 תווים")

    digits = "".join(c for c in phone if c.isdigit())
    user: Optional[Technician] = None
    matched_key: Optional[str] = None

    for tech in db.query(Technician).filter(Technician.is_active == True).all():  # noqa: E712
        candidate = tech.whatsapp_number or tech.phone or ""
        c_digits = "".join(c for c in candidate if c.isdigit())
        if c_digits and digits and c_digits[-9:] == digits[-9:]:
            chat_phone = tech.whatsapp_number or tech.phone
            normalized = _normalize_phone(chat_phone)
            if normalized:
                user = tech
                matched_key = normalized
            break

    if not user or not matched_key:
        raise HTTPException(status_code=400, detail="מספר הטלפון לא נמצא")

    stored = _otp_store.get(matched_key)
    if not stored or stored[1] < time.time():
        _otp_store.pop(matched_key, None)
        raise HTTPException(status_code=400, detail="הקוד פג תוקף — יש לבקש קוד חדש")

    if stored[0] != otp.strip():
        raise HTTPException(status_code=400, detail="הקוד שגוי")

    _otp_store.pop(matched_key, None)
    user.hashed_password = hash_password(new_password)
    db.commit()

    return {"detail": "הסיסמה עודכנה בהצלחה"}


@router.get(
    "/me",
    summary="Current user",
    description="Return profile of the currently authenticated user.",
)
def me(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(__import__("app.auth.dependencies", fromlist=["get_current_user"]).get_current_user),
):
    """Return the current authenticated user's profile."""
    return {
        "id":         str(current_user.id),
        "email":      current_user.email,
        "name":       current_user.name,
        "role":       current_user.role,
        "is_active":  current_user.is_active,
    }
