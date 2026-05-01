"""Control plane configuration — all from environment variables."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database (tenant registry)
    database_url: str = "postgresql://user:password@localhost:5432/control_plane_db"

    # JWT auth (superadmin)
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24h

    # Superadmin credentials (Denis only)
    superadmin_email: str = "admin@lift-agent.com"
    superadmin_password: str = ""  # bcrypt hash stored here

    # CORS — control plane frontend domain
    cors_origins: str = "http://localhost:5174,https://admin.lift-agent.com"

    # Hetzner Cloud
    hetzner_api_token: str = ""
    hetzner_server_type: str = "cx22"       # 2 vCPU, 4GB RAM — ~€4/mo
    hetzner_image: str = "ubuntu-24.04"
    hetzner_location: str = "nbg1"          # Nuremberg (EU)
    hetzner_ssh_key_name: str = ""          # name of SSH key in Hetzner project

    # Docker image for tenant deployments
    tenant_docker_image: str = "ghcr.io/your-org/elevator-service-api:latest"

    # Cloudflare DNS
    cloudflare_api_token: str = ""
    cloudflare_zone_id: str = ""   # Zone ID for lift-agent.com

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Monitoring
    monitor_interval_seconds: int = 300     # 5 minutes

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
