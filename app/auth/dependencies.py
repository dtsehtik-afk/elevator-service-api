"""FastAPI dependency functions for authentication and role-based access control."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.auth.security import decode_token
from app.database import get_db
from app.models.technician import Technician

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Technician:
    """Extract and validate the JWT token; return the authenticated user.

    Raises:
        HTTPException 401: If the token is missing, invalid, or the user does not exist.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(Technician).filter(Technician.email == email).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*roles: str):
    """Return a FastAPI dependency that enforces one of the given roles.

    Usage:
        Depends(require_roles("ADMIN", "DISPATCHER"))
    """
    def checker(current_user: Technician = Depends(get_current_user)) -> Technician:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access requires one of: {', '.join(roles)}",
            )
        return current_user

    return checker


def require_admin(current_user: Technician = Depends(get_current_user)) -> Technician:
    """Shortcut dependency — ADMIN only."""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_dispatcher_or_admin(
    current_user: Technician = Depends(get_current_user),
) -> Technician:
    """Shortcut dependency — ADMIN or DISPATCHER."""
    if current_user.role not in ("ADMIN", "DISPATCHER"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dispatcher or Admin access required",
        )
    return current_user
