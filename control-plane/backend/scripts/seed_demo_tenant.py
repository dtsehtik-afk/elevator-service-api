"""
Seed script — creates a demo tenant in the control plane registry.

Usage:
    cd control-plane/backend
    python scripts/seed_demo_tenant.py

Prerequisites:
    - .env file configured with DATABASE_URL
    - DB tables created (app starts and runs create_all on first boot)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.models.tenant import Tenant


DEMO = {
    "name": "Demo — חברת מעליות לדוגמה",
    "slug": "demo",
    "contact_email": "demo@lift-agent.com",
    "contact_phone": "050-0000000",
    "plan": "PRO",
    "notes": "דייר Demo אוטומטי — לבדיקות ו-onboarding",
    "modules": {
        "whatsapp": True,
        "email_calls": True,
        "inspection_emails": True,
        "google_drive": False,
        "openai_transcription": False,
        "maps": True,
        "whatsapp_reminders": False,
    },
}


def main():
    db = SessionLocal()
    try:
        existing = db.query(Tenant).filter_by(slug=DEMO["slug"]).first()
        if existing:
            print(f"Demo tenant already exists (id={existing.id})")
            print(f"  API Key: {existing.api_key}")
            return

        tenant = Tenant(**DEMO)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        print("✓ Demo tenant created")
        print(f"  ID:      {tenant.id}")
        print(f"  Slug:    {tenant.slug}")
        print(f"  API Key: {tenant.api_key}")
        print()
        print("Next steps:")
        print("  1. Set CONTROL_PLANE_API_KEY on the demo server to the API key above")
        print("  2. Set api_url in the control plane dashboard")
        print("  3. Click 'Deploy to Hetzner' or set manually if already running")
    finally:
        db.close()


if __name__ == "__main__":
    main()
