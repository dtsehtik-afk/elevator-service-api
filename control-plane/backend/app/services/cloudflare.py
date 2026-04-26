"""Cloudflare DNS automation — create/delete A records for tenant subdomains."""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
_BASE = "https://api.cloudflare.com/client/v4"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_settings().cloudflare_api_token}",
        "Content-Type": "application/json",
    }


def _zone_id() -> str:
    return get_settings().cloudflare_zone_id


def create_dns_record(slug: str, ip: str) -> str:
    """
    Create an A record: <slug>.lift-agent.com → <ip>
    Returns the Cloudflare DNS record ID.
    Idempotent — deletes existing record with same name first.
    """
    name = f"{slug}.lift-agent.com"

    # Delete any existing record with the same name to avoid conflicts
    _delete_by_name(name)

    resp = httpx.post(
        f"{_BASE}/zones/{_zone_id()}/dns_records",
        json={"type": "A", "name": name, "content": ip, "ttl": 60, "proxied": False},
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    record_id = resp.json()["result"]["id"]
    logger.info("DNS: %s → %s (record %s)", name, ip, record_id)
    return record_id


def delete_dns_record(record_id: str) -> None:
    """Delete a DNS record by its Cloudflare record ID."""
    resp = httpx.delete(
        f"{_BASE}/zones/{_zone_id()}/dns_records/{record_id}",
        headers=_headers(),
        timeout=15,
    )
    if resp.status_code not in (200, 404):
        resp.raise_for_status()
    logger.info("DNS record %s deleted", record_id)


def _delete_by_name(name: str) -> None:
    """Delete all existing A records matching this name."""
    resp = httpx.get(
        f"{_BASE}/zones/{_zone_id()}/dns_records",
        params={"type": "A", "name": name},
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    for record in resp.json().get("result", []):
        delete_dns_record(record["id"])
