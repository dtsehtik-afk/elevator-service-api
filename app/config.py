"""Application configuration — loaded exclusively from environment variables."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All sensitive configuration comes from environment variables only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql://user:password@localhost:5432/elevator_db"

    # JWT
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # App
    environment: str = "development"
    admin_email: str = "admin@example.com"
    admin_password: str = "changeme123"

    # Webhook security — set a strong random string in .env
    webhook_secret: str = "change-this-webhook-secret"

    # Google Maps API
    google_maps_api_key: str = ""

    # Green API (WhatsApp)
    greenapi_instance_id: str = ""
    greenapi_api_token: str = ""

    # Dispatcher WhatsApp (for unassigned-call alerts)
    dispatcher_whatsapp: str = ""

    # Public base URL for technician portal links (e.g. http://192.168.1.100:8000)
    app_base_url: str = "http://localhost:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
