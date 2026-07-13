import io
from datetime import timedelta

import pyotp
import qrcode
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.admin_user import AdminUser
from app.auth.security import verify_password, create_token, hash_password, decode_token_raw
from app.auth.dependencies import get_current_admin

router = APIRouter(prefix="/auth", tags=["auth"])

_MFA_PENDING_EXPIRE = timedelta(minutes=10)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    name: str
    email: str
    totp_enabled: bool = False


def _get_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _record_login(db: Session, admin_id: str, ip: str, ua: str, success: bool):
    try:
        db.execute(
            text("INSERT INTO admin_login_history (admin_id, ip_address, user_agent, success) VALUES (:aid, :ip, :ua, :ok)"),
            {"aid": admin_id, "ip": ip, "ua": ua[:500], "ok": 1 if success else 0},
        )
        db.commit()
    except Exception:
        db.rollback()


def _is_new_ip(db: Session, admin_id: str, ip: str) -> bool:
    try:
        row = db.execute(
            text("SELECT 1 FROM admin_login_history WHERE admin_id = :aid AND ip_address = :ip AND success = 1 LIMIT 1"),
            {"aid": admin_id, "ip": ip},
        ).fetchone()
        return row is None
    except Exception:
        return False


def _alert_new_ip(db: Session, user: AdminUser, ip: str):
    """Alert all active admins via WhatsApp about a new-IP login."""
    try:
        import httpx, os
        # Alert is best-effort — skip if no WhatsApp config
        admins = db.query(AdminUser).filter(AdminUser.is_active == True).all()  # noqa: E712
        # We don't have direct WhatsApp access in admin console — log only
        import logging
        logging.getLogger(__name__).warning(
            f"New IP login for admin {user.email} from {ip}. "
            f"Active admins to notify: {[a.email for a in admins]}"
        )
    except Exception:
        pass


@router.post("/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ip = _get_ip(request)
    ua = request.headers.get("User-Agent", "")

    user = db.query(AdminUser).filter(AdminUser.email == form.username, AdminUser.is_active == True).first()  # noqa: E712
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.totp_enabled and user.totp_secret:
        pending = create_token(user.email, extra={"mfa_pending": True}, expires=_MFA_PENDING_EXPIRE)
        return {"mfa_required": True, "pending_token": pending}

    _record_login(db, str(user.id), ip, ua, True)
    if _is_new_ip(db, str(user.id), ip):
        _alert_new_ip(db, user, ip)

    return TokenResponse(access_token=create_token(user.email))


@router.post("/totp/verify", response_model=TokenResponse)
def totp_verify(request: Request, pending_token: str = Body(...), code: str = Body(...), db: Session = Depends(get_db)):
    from jose import JWTError
    ip = _get_ip(request)
    ua = request.headers.get("User-Agent", "")
    try:
        payload = decode_token_raw(pending_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid or expired")
    if not payload.get("mfa_pending"):
        raise HTTPException(status_code=400, detail="Token not for MFA")
    user = db.query(AdminUser).filter(AdminUser.email == payload["sub"], AdminUser.is_active == True).first()  # noqa: E712
    if not user or not user.totp_secret:
        raise HTTPException(status_code=401, detail="User not found")
    if not pyotp.TOTP(user.totp_secret).verify(code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    _record_login(db, str(user.id), ip, ua, True)
    if _is_new_ip(db, str(user.id), ip):
        _alert_new_ip(db, user, ip)
    return TokenResponse(access_token=create_token(user.email))


@router.post("/totp/setup")
def totp_setup(current: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    secret = pyotp.random_base32()
    current.totp_secret = secret
    current.totp_enabled = False
    db.commit()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=current.email, issuer_name="LiftAgent Admin")
    return {"secret": secret, "otpauth_uri": uri}


@router.get("/totp/qr")
def totp_qr(current: AdminUser = Depends(get_current_admin)):
    if not current.totp_secret:
        raise HTTPException(status_code=400, detail="Call /totp/setup first")
    uri = pyotp.totp.TOTP(current.totp_secret).provisioning_uri(name=current.email, issuer_name="LiftAgent Admin")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf)  # type: ignore[arg-type]
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.post("/totp/confirm")
def totp_confirm(code: str = Body(..., embed=True), current: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    if not current.totp_secret:
        raise HTTPException(status_code=400, detail="Call /totp/setup first")
    if not pyotp.TOTP(current.totp_secret).verify(code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    current.totp_enabled = True
    db.commit()
    return {"detail": "TOTP enabled"}


@router.post("/totp/disable")
def totp_disable(code: str = Body(..., embed=True), current: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    if not current.totp_enabled or not current.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP not enabled")
    if not pyotp.TOTP(current.totp_secret).verify(code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    current.totp_enabled = False
    current.totp_secret = None
    db.commit()
    return {"detail": "TOTP disabled"}


@router.get("/totp/status")
def totp_status(current: AdminUser = Depends(get_current_admin)):
    return {"totp_enabled": current.totp_enabled}


@router.get("/login-history")
def login_history(current: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    try:
        rows = db.execute(
            text("SELECT ip_address, user_agent, success, created_at FROM admin_login_history WHERE admin_id = :aid ORDER BY created_at DESC LIMIT 20"),
            {"aid": str(current.id)},
        ).fetchall()
        return [{"ip_address": r[0], "user_agent": r[1], "success": bool(r[2]), "created_at": str(r[3])} for r in rows]
    except Exception:
        return []


@router.get("/me", response_model=MeResponse)
def me(current: AdminUser = Depends(get_current_admin)):
    return MeResponse(id=str(current.id), name=current.name, email=current.email, totp_enabled=current.totp_enabled)


@router.post("/seed-admin", include_in_schema=False)
def seed_admin(db: Session = Depends(get_db)):
    import os

    if db.query(AdminUser).count() > 0:
        raise HTTPException(status_code=409, detail="Admin already exists")

    email = os.getenv("INITIAL_ADMIN_EMAIL", "admin@lift-agent.com")
    env_password = os.getenv("INITIAL_ADMIN_PASSWORD")
    password = env_password or "changeme123"

    user = AdminUser(name="Super Admin", email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()

    # Only echo the password when it's the insecure default (so the operator knows to
    # change it). When set via env it stays secret.
    resp = {"ok": True, "email": user.email}
    if not env_password:
        resp["password"] = password
        resp["warning"] = "Default password in use — change it immediately after first login."
    return resp
