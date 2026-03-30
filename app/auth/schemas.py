"""Pydantic schemas for authentication endpoints."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Credentials for the /auth/login endpoint."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token returned after successful login."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Claims extracted from a JWT token."""
    sub: str
    role: str
