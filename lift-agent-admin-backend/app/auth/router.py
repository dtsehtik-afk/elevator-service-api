from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.admin_user import AdminUser
from app.auth.security import verify_password, create_token, hash_password
from app.auth.dependencies import get_current_admin

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    name: str
    email: str


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.email == form.username, AdminUser.is_active == True).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_token(user.email))


@router.get("/me", response_model=MeResponse)
def me(current: AdminUser = Depends(get_current_admin)):
    return MeResponse(id=str(current.id), name=current.name, email=current.email)


@router.post("/seed-admin", include_in_schema=False)
def seed_admin(db: Session = Depends(get_db)):
    """One-time endpoint to create the first admin user."""
    if db.query(AdminUser).count() > 0:
        raise HTTPException(status_code=409, detail="Admin already exists")
    user = AdminUser(name="Super Admin", email="admin@lift-agent.com", hashed_password=hash_password("changeme123"))
    db.add(user)
    db.commit()
    return {"ok": True, "email": user.email, "password": "changeme123"}
