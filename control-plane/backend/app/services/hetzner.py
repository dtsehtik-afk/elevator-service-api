"""Hetzner Cloud API — provision and destroy tenant servers."""

import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_BASE = "https://api.hetzner.cloud/v1"


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_settings().hetzner_api_token}"}


def _cloud_init(slug: str, env_vars: dict, docker_image: str) -> str:
    """Generate cloud-init user-data script for a new tenant server."""
    domain = f"{slug}.lift-agent.com"
    env_lines = "\n".join(f"{k}={v}" for k, v in env_vars.items())
    return f"""#!/bin/bash
set -e
exec > /var/log/liftapp-init.log 2>&1

# ── System packages ───────────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y -qq git docker.io docker-compose-plugin nginx certbot python3-certbot-nginx

systemctl enable docker
systemctl start docker

# ── Clone repo ────────────────────────────────────────────────────────────────
git clone https://github.com/dtsehtik-afk/elevator-service-api.git /opt/liftapp
cd /opt/liftapp

# ── .env ──────────────────────────────────────────────────────────────────────
cat > /opt/liftapp/.env << 'ENVEOF'
{env_lines}
APP_BASE_URL=https://{domain}
CORS_ORIGINS=https://{domain}
ENVEOF

# ── Start only db + app ───────────────────────────────────────────────────────
docker compose up -d --build db app

# ── Wait for app ──────────────────────────────────────────────────────────────
sleep 30

# ── nginx reverse proxy ───────────────────────────────────────────────────────
cat > /etc/nginx/sites-available/liftapp << 'NGINXEOF'
server {{
    listen 80;
    server_name {domain} _;

    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }}
}}
NGINXEOF

ln -sf /etc/nginx/sites-available/liftapp /etc/nginx/sites-enabled/liftapp
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl enable nginx && systemctl restart nginx

echo "lift-agent tenant '{slug}' ready at http://{domain}"
"""


def create_tenant_server(slug: str, env_vars: dict) -> int:
    """Create a Hetzner server for the given tenant. Returns server ID."""
    settings = get_settings()
    user_data = _cloud_init(slug, env_vars, "")

    payload = {
        "name": f"lift-{slug}",
        "server_type": settings.hetzner_server_type,
        "image": settings.hetzner_image,
        "location": settings.hetzner_location,
        "user_data": user_data,
        "labels": {"tenant": slug, "app": "lift-agent"},
    }
    if settings.hetzner_ssh_key_name:
        payload["ssh_keys"] = [settings.hetzner_ssh_key_name]

    resp = httpx.post(f"{_BASE}/servers", json=payload, headers=_headers(), timeout=30)
    if not resp.is_success:
        logger.error("Hetzner error %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    server_id = resp.json()["server"]["id"]
    logger.info("Created Hetzner server %s for tenant %s", server_id, slug)
    return server_id


def wait_for_server_ip(server_id: int, timeout: int = 180) -> str:
    """Poll until the server has a public IPv4. Returns the IP."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = httpx.get(f"{_BASE}/servers/{server_id}", headers=_headers(), timeout=10)
        resp.raise_for_status()
        ip = resp.json()["server"]["public_net"]["ipv4"]["ip"]
        if ip:
            return ip
        time.sleep(5)
    raise TimeoutError(f"Server {server_id} did not get an IP within {timeout}s")


def delete_server(server_id: int) -> None:
    """Delete a Hetzner server by ID."""
    resp = httpx.delete(f"{_BASE}/servers/{server_id}", headers=_headers(), timeout=15)
    if resp.status_code not in (200, 204, 404):
        resp.raise_for_status()
    logger.info("Deleted Hetzner server %s", server_id)


def list_servers() -> list[dict]:
    """Return all servers tagged with app=lift-agent."""
    resp = httpx.get(
        f"{_BASE}/servers",
        params={"label_selector": "app=lift-agent"},
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("servers", [])
