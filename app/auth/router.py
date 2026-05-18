"""Authentication router — login, TOTP MFA, and password reset endpoints."""

import io
import random
import time
from datetime import timedelta
from typing import Optional

import pyotp
import qrcode
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth.schemas import TokenResponse
from app.auth.security import create_access_token, hash_password, verify_password, decode_token
from app.database import get_db
from app.models.technician import Technician

router = APIRouter()
_limiter = Limiter(key_func=get_remote_address)

# In-memory OTP store: phone_normalized -> (otp, expires_at)
_otp_store: dict[str, tuple[str, float]] = {}
_OTP_TTL = 900  # 15 minutes

_MFA_PENDING_EXPIRE = timedelta(minutes=10)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _record_login(db: Session, technician_id, ip: str, user_agent: str, success: bool):
    try:
        db.execute(
            text(
                "INSERT INTO login_history (technician_id, ip_address, user_agent, success) "
                "VALUES (:tid, :ip, :ua, :ok)"
            ),
            {"tid": str(technician_id), "ip": ip, "ua": user_agent[:500], "ok": success},
        )
        db.commit()
    except Exception:
        db.rollback()


def _is_new_ip(db: Session, technician_id, ip: str) -> bool:
    row = db.execute(
        text(
            "SELECT 1 FROM login_history WHERE technician_id = :tid AND ip_address = :ip "
            "AND success = TRUE LIMIT 1"
        ),
        {"tid": str(technician_id), "ip": ip},
    ).fetchone()
    return row is None


def _alert_admins_new_ip(db: Session, user: Technician, ip: str):
    """Send WhatsApp alert to all ADMIN-role technicians about a new IP login."""
    try:
        from app.services.whatsapp_service import _send_message

        admins = db.query(Technician).filter(
            Technician.role == "ADMIN",
            Technician.is_active == True,  # noqa: E712
        ).all()
        msg = (
            f"🔐 *התחברות מכתובת IP חדשה*\n\n"
            f"משתמש: *{user.name}* ({user.email})\n"
            f"כתובת IP: `{ip}`\n\n"
            f"אם אינך מכיר פעולה זו — שנה את הסיסמה מיד."
        )
        for admin in admins:
            phone = admin.whatsapp_number or admin.phone
            if phone:
                _send_message(phone, msg)
    except Exception:
        pass


@router.post(
    "/login",
    summary="Login",
    description="Authenticate with email and password. Returns JWT token or mfa_required signal.",
)
@_limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate user. If TOTP is enabled returns mfa_required=True with a temp token."""
    ip = _get_client_ip(request)
    ua = request.headers.get("User-Agent", "")

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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    if user.totp_enabled and user.totp_secret:
        # Return a short-lived pending token — frontend must complete TOTP step
        pending_token = create_access_token(
            {"sub": user.email, "role": user.role, "mfa_pending": True},
            expires_delta=_MFA_PENDING_EXPIRE,
        )
        return {"mfa_required": True, "pending_token": pending_token}

    # No MFA — full login
    _record_login(db, user.id, ip, ua, True)
    if _is_new_ip(db, user.id, ip):
        _alert_admins_new_ip(db, user, ip)

    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token)


@router.post("/totp/verify", response_model=TokenResponse, summary="Complete TOTP MFA step")
@_limiter.limit("10/minute")
def totp_verify(
    request: Request,
    pending_token: str = Body(...),
    code: str = Body(...),
    db: Session = Depends(get_db),
):
    """Verify a TOTP code after password login. Returns full JWT on success."""
    from jose import JWTError

    ip = _get_client_ip(request)
    ua = request.headers.get("User-Agent", "")

    try:
        payload = decode_token(pending_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="קוד גישה זמני לא תקין או פג תוקף")

    if not payload.get("mfa_pending"):
        raise HTTPException(status_code=400, detail="טוקן לא מתאים לאימות דו-שלבי")

    user = (
        db.query(Technician)
        .filter(func.lower(Technician.email) == payload["sub"].lower())
        .first()
    )
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="משתמש לא נמצא")

    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP לא מוגדר למשתמש זה")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="קוד אימות שגוי — נסה שנית")

    _record_login(db, user.id, ip, ua, True)
    if _is_new_ip(db, user.id, ip):
        _alert_admins_new_ip(db, user, ip)

    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token)


@router.post("/totp/setup", summary="Generate TOTP secret for authenticated user")
def totp_setup(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(
        __import__("app.auth.dependencies", fromlist=["get_current_user"]).get_current_user
    ),
):
    """Generate a new TOTP secret. Returns base32 secret + provisioning URI."""
    secret = pyotp.random_base32()
    current_user.totp_secret = secret
    current_user.totp_enabled = False  # not active until confirmed
    db.commit()

    company = "LiftAgent"
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.email, issuer_name=company
    )
    return {"secret": secret, "otpauth_uri": uri}


@router.get("/totp/qr", summary="Return QR code PNG for TOTP setup")
def totp_qr(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(
        __import__("app.auth.dependencies", fromlist=["get_current_user"]).get_current_user
    ),
):
    """Return a QR code image for the current user's TOTP secret."""
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="יש להפעיל תחילה את /auth/totp/setup")

    company = "LiftAgent"
    uri = pyotp.totp.TOTP(current_user.totp_secret).provisioning_uri(
        name=current_user.email, issuer_name=company
    )
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf)  # type: ignore[arg-type]
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.post("/totp/confirm", summary="Confirm TOTP setup with first code")
def totp_confirm(
    code: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(
        __import__("app.auth.dependencies", fromlist=["get_current_user"]).get_current_user
    ),
):
    """Verify first TOTP code to activate 2FA. Must call /totp/setup first."""
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="יש להפעיל תחילה את /auth/totp/setup")

    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="קוד שגוי — נסה שנית")

    current_user.totp_enabled = True
    db.commit()
    return {"detail": "אימות דו-שלבי הופעל בהצלחה"}


@router.post("/totp/disable", summary="Disable TOTP for authenticated user")
def totp_disable(
    code: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(
        __import__("app.auth.dependencies", fromlist=["get_current_user"]).get_current_user
    ),
):
    """Disable TOTP by supplying one final valid code."""
    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="אימות דו-שלבי אינו מופעל")

    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="קוד שגוי")

    current_user.totp_enabled = False
    current_user.totp_secret = None
    db.commit()
    return {"detail": "אימות דו-שלבי בוטל"}


@router.get("/totp/status", summary="Check TOTP status for current user")
def totp_status(
    current_user: Technician = Depends(
        __import__("app.auth.dependencies", fromlist=["get_current_user"]).get_current_user
    ),
):
    return {"totp_enabled": current_user.totp_enabled}


@router.get("/login-history", summary="Recent login history for current user")
def login_history(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(
        __import__("app.auth.dependencies", fromlist=["get_current_user"]).get_current_user
    ),
):
    rows = db.execute(
        text(
            "SELECT ip_address, user_agent, success, created_at FROM login_history "
            "WHERE technician_id = :tid ORDER BY created_at DESC LIMIT 20"
        ),
        {"tid": str(current_user.id)},
    ).fetchall()
    return [
        {
            "ip_address": r[0],
            "user_agent": r[1],
            "success": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]


@router.post("/forgot-password", summary="Request password reset OTP via WhatsApp")
@_limiter.limit("5/minute")
def forgot_password(
    request: Request,
    phone: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Generate a 6-digit OTP and send it via WhatsApp to the technician's phone."""
    from app.services.whatsapp_service import _normalize_phone, _send_message

    digits = "".join(c for c in phone if c.isdigit())
    user: Optional[Technician] = None
    for tech in db.query(Technician).filter(Technician.is_active == True).all():  # noqa: E712
        candidate = tech.whatsapp_number or tech.phone or ""
        c_digits = "".join(c for c in candidate if c.isdigit())
        if c_digits and digits and c_digits[-9:] == digits[-9:]:
            user = tech
            break

    if not user:
        return {"detail": "אם המספר קיים במערכת, ישלח קוד לווצאפ"}

    otp = f"{random.randint(0, 999999):06d}"
    chat_phone = user.whatsapp_number or user.phone
    normalized = _normalize_phone(chat_phone)
    if normalized:
        key = normalized
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
    current_user: Technician = Depends(
        __import__("app.auth.dependencies", fromlist=["get_current_user"]).get_current_user
    ),
):
    """Return the current authenticated user's profile."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "totp_enabled": current_user.totp_enabled,
    }
