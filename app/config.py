"""Application configuration — loaded exclusively from environment variables."""

from functools import lru_cache
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All sensitive configuration comes from environment variables only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://user:password@localhost:5432/elevator_db"

    # JWT
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days — suitable for mobile apps

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # App
    environment: str = "development"

    # Webhook security — set a strong random string in .env
    webhook_secret: str = ""

    # Google Maps API
    google_maps_api_key: str = ""

    # Green API (WhatsApp)
    greenapi_instance_id: str = ""
    greenapi_api_token: str = ""

    # Dispatcher WhatsApp (for unassigned-call alerts) — comma-separated list of manager WhatsApp numbers
    dispatcher_whatsapp: str = ""  # comma-separated list of manager WhatsApp numbers

    # Public base URL for technician portal links (e.g. http://192.168.1.100:8000)
    app_base_url: str = "http://localhost:8000"

    # Gmail IMAP — shared fallback (used if the specific vars below are not set)
    gmail_user: str = ""
    gmail_app_password: str = ""

    # Service-call emails (beepertalk) — set GMAIL_USER_CALLS + GMAIL_APP_PASSWORD_CALLS
    gmail_user_calls: str = ""
    gmail_app_password_calls: str = ""
    gmail_imap_folder: str = "[Gmail]/All Mail"
    call_email_senders: str = "TELESERVICE@beepertalk.co.il,denis@akordelevator.com"

    # Inspection-report emails — set GMAIL_USER_REPORTS + GMAIL_APP_PASSWORD_REPORTS
    gmail_user_reports: str = ""
    gmail_app_password_reports: str = ""

    # OpenAI — used for Whisper voice transcription
    openai_api_key: str = ""

    # Google Gemini — used for email parsing and WhatsApp chat agent
    gemini_api_key: str = ""

    # Google Drive integration — optional, falls back to local storage if unset
    # GOOGLE_SERVICE_ACCOUNT_JSON: full JSON content of the service account key file
    google_service_account_json: str = ""
    # GOOGLE_DRIVE_FOLDER_ID: ID from the Drive folder URL
    google_drive_folder_id: str = ""
    # How often (minutes) to scan Drive folder for new inspection reports
    google_drive_scan_interval: int = 15

    @model_validator(mode="after")
    def _validate_secrets(self):
        if self.environment == "production":
            if not self.secret_key:
                raise ValueError("SECRET_KEY must be set in production")
            if not self.webhook_secret:
                raise ValueError("WEBHOOK_SECRET must be set in production")
        return self

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
