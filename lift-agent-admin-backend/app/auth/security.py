from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(email: str, extra: dict | None = None, expires: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires or timedelta(minutes=settings.access_token_expire_minutes))
    data = {"sub": email, "exp": expire}
    if extra:
        data.update(extra)
    return jwt.encode(data, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> str:
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    return payload["sub"]


def decode_token_raw(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
