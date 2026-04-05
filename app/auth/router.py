"""Authentication router — login endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.schemas import TokenResponse
from app.auth.security import create_access_token, verify_password
from app.database import get_db
from app.models.technician import Technician

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
    description="Authenticate with email and password. Returns a JWT Bearer token.",
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate user and return JWT access token.

    Args:
        form_data: OAuth2 form with ``username`` (email) and ``password``.
        db: Database session.

    Returns:
        TokenResponse with JWT access token.

    Raises:
        HTTPException 401: If credentials are invalid.
    """
    user = db.query(Technician).filter(Technician.email == form_data.username).first()
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
