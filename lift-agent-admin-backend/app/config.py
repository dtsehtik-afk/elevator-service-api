from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@db:5432/liftadmin"
    secret_key: str = _INSECURE_DEFAULT_SECRET
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24h
    environment: str = "development"
    cors_origins: str = "http://localhost:5174"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _validate_secret(self):
        if self.environment == "production" and (
            not self.secret_key or self.secret_key == _INSECURE_DEFAULT_SECRET
        ):
            raise ValueError("SECRET_KEY must be set to a strong random value in production")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
