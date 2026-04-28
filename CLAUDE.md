# Lift Agent — System Knowledge Base

This file is read automatically at the start of every Claude session.
**Update this file whenever a significant change is made to the system.**

---

## What Is This System?

**Lift Agent** is a SaaS field-service platform for elevator maintenance companies.
It handles incoming service calls (via phone/WhatsApp/email), assigns them to technicians using AI,
tracks maintenance, inspections, and communicates via WhatsApp (Green API).

Live at: **https://lift-agent.com**
Admin panel: **https://lift-agent.com** (frontend on port 3000 / Nginx proxy)
APK: built via GitHub Actions, server URL points to `https://lift-agent.com`

---

## Repository & Branch

- Repo: `dtsehtik-afk/elevator-service-api`
- Active dev branch: `claude/technician-request-assignment-NofCx`
- **NEVER push to main without explicit permission**
- After every commit: `git push -u origin claude/technician-request-assignment-NofCx`

---

## Server

- Host: `elevator-server` (Google Cloud VM)
- Connect: `ssh dtsehtik@lift-agent.com`
- Stack: Docker Compose
- Services: `app` (FastAPI uvicorn), `db` (PostgreSQL 16), `nginx`, `certbot`, `ngrok`
- Deploy: `sudo docker compose up -d --build app`
- Logs: `sudo docker compose logs app -f`

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 (Docker) |
| Frontend | React + Mantine UI + TanStack Query + Vite |
| Mobile | Capacitor (Android APK) |
| WhatsApp | Green API |
| AI — Email parsing | Gemini 2.0 Flash (primary) |
| AI — Assignment | Gemini 2.0 Flash (primary), falls back to regex |
| AI — Chat agent | Gemini (WhatsApp chatbot for technicians/managers) |
| Voice transcription | OpenAI Whisper |
| Maps | Google Maps API |
| Email polling | IMAP Gmail (denis@akordelevator.com is the mailbox) |
| Scheduling | APScheduler (BackgroundScheduler) |

---

## Architecture

### Multi-Tenant Strategy: Silo Model
Each customer (tenant) = **separate VPS + separate DB + separate deployment**.
No shared data between tenants whatsoever.

### Control Plane (lift-agent-admin)
Separate FastAPI + React app at `lift-agent-admin-backend/` and `lift-agent-admin-frontend/`
inside this repo. Manages all tenants from a super-admin dashboard.
- Backend runs on port 8001
- Frontend runs on port 5174
- Uses SQLite locally, PostgreSQL in production
- Run locally: `bash lift-agent-admin-run-local.sh`
- Default admin: `admin@lift-agent.com` / `changeme123` (created via `/auth/seed-admin`)

---

## Key Environment Variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing key |
| `GREENAPI_INSTANCE_ID` | WhatsApp (Green API) instance |
| `GREENAPI_API_TOKEN` | WhatsApp (Green API) token |
| `GEMINI_API_KEY` | Google Gemini AI |
| `OPENAI_API_KEY` | Whisper voice transcription |
| `GOOGLE_MAPS_API_KEY` | Maps / geocoding |
| `DISPATCHER_WHATSAPP` | Comma-separated manager WhatsApp numbers for alerts |
| `GMAIL_USER_CALLS` | Gmail account for polling service-call emails |
| `GMAIL_APP_PASSWORD_CALLS` | Gmail app password for IMAP |
| `CALL_EMAIL_SENDERS` | Comma-separated allowed senders (default: `TELESERVICE@beepertalk.co.il`) |
| `APP_BASE_URL` | Public URL for technician portal links |
| `WEBHOOK_SECRET` | Shared secret for webhook auth |

---

## Data Models

### Core
- **Elevator** — physical elevator unit (address, city, floor_count, latitude, longitude, serial_number)
- **ServiceCall** — a repair/rescue request (fault_type, status, priority, after_hours_pending)
- **Technician** — field technician (phone, whatsapp_number, role, is_available, current_latitude/longitude)
- **Assignment** — links ServiceCall ↔ Technician (status: PENDING_CONFIRMATION → ACCEPTED/REJECTED)
- **ManagementCompany** — building management company (caller_phones: TEXT[])

### Supporting
- **MaintenanceSchedule** — planned quarterly/annual maintenance per elevator
- **InspectionReport** — safety inspection with checklist (deficiencies JSON)
- **Building** — building record linked to elevators
- **Contact** — contact directory
- **WhatsAppMessage** — message log
- **ServiceCallEmailScan** — dedup table for processed email message IDs
- **InspectionEmailScan** — dedup table for inspection emails
- **SystemSettings** — key-value store (working hours, config)

### fault_type enum
`STUCK | DOOR | ELECTRICAL | MECHANICAL | SOFTWARE | RESCUE | MAINTENANCE | OTHER`

### ServiceCall.status
`OPEN → ASSIGNED → IN_PROGRESS → RESOLVED → CLOSED`

---

## API Routers (`/app/routers/`)

| Router | Prefix | Notes |
|---|---|---|
| `auth` | `/auth` | JWT login, register, me |
| `elevators` | `/elevators` | CRUD + location update |
| `service_calls` | `/service-calls` | CRUD + filters |
| `assignments` | `/assignments` | Manual assign, confirm, reject |
| `technicians` | `/technicians` | CRUD + location POST |
| `technician_app` | `/technician-app` | Mobile app endpoints |
| `maintenance` | `/maintenance` | Scheduled maintenance |
| `inspections` | `/inspection-reports` | Reports + checklist |
| `management_companies` | `/management-companies` | CRUD + elevator assignment |
| `webhooks` | `/webhooks` | WhatsApp + phone call webhooks |
| `settings` | `/settings` | Working hours (GET/POST) |
| `analytics` | `/analytics` | Stats |
| `buildings` | `/buildings` | Building CRUD |
| `contacts` | `/contacts` | Contact directory |
| `conversations` | `/conversations` | WhatsApp conversation history |
| `data_import` | `/import` | Excel/PDF import |
| `schedule` | `/schedule` | Schedule management |

---

## Key Services (`/app/services/`)

| Service | Purpose |
|---|---|
| `email_poller.py` | IMAP Gmail polling — pulls UNSEEN emails every 60s, marks as read after processing. Gemini parses content. denis@akordelevator.com is the inbox. |
| `ai_assignment_agent.py` | Assigns technician to service call using AI. Sends WhatsApp confirmation request (1=accept, 2=reject). |
| `whatsapp_service.py` | All WhatsApp messaging via Green API. notify_rescue_emergency, assign_with_confirmation, after_hours messages. |
| `working_hours.py` | In-memory working hours schedule. `is_working_hours()` checks if current time is within schedule. Hot-reloadable via settings endpoint. |
| `scheduler.py` | APScheduler jobs: email polling (60s), assignment timeout check (60s), inspection email (1h), Drive scan (15min), nightly maintenance (00:05), morning monitoring (08:00). |
| `inspection_email_poller.py` | Polls separate Gmail for inspection report emails (hourly). |
| `drive_service.py` | Google Drive integration for inspection report PDFs. |
| `call_parser.py` | Parses incoming phone call data into structured fields. |

---

## WhatsApp Flow

1. **Incoming call** → webhook `POST /webhooks/receive-call` → parse → find elevator → check working hours
2. **During hours**: AI assigns technician → sends WhatsApp "קריאה חדשה, 1=קבל 2=דחה"
3. **After hours (non-RESCUE)**: sends caller WhatsApp asking "1=אשר תוספת, 2=דחה למחר" → `after_hours_pending=True`
4. **Caller replies 1**: dispatch technician. Caller replies 2: defer.
5. **Technician replies 1**: accept → status ASSIGNED. Replies 2: reject → try next technician.
6. **RESCUE calls**: always dispatch immediately, blast ALL technicians.

---

## Frontend Pages (`/frontend/src/pages/`)

| Page | Route | Notes |
|---|---|---|
| `CallsPage` | `/calls` | Service calls list + detail. Has "עדכן מיקום" button (LocationPickerModal). |
| `ElevatorDetailPage` | `/elevators/:id` | Elevator details + location picker + Waze link. |
| `MaintenancePage` | `/maintenance` | Scheduled maintenance + OPEN MAINTENANCE calls with urgency blink. |
| `SettingsPage` | `/settings` | Working hours editor (admin only). |
| `TechnicianApp` | `/tech/*` | Mobile technician interface. |

### LocationPickerModal
Lazy-loads Leaflet from CDN. Click-to-pin, draggable marker, GPS button.
Used in ElevatorDetailPage and CallsPage.

---

## Scheduled Jobs (APScheduler)

| Job | Interval | Purpose |
|---|---|---|
| `_poll_email_calls` | 60s | Pull UNSEEN service-call emails from Gmail |
| `_check_pending_assignment_timeouts` | 60s | Auto-cancel timed-out assignment confirmations |
| `_poll_inspection_emails` | 1h | Pull inspection report emails |
| `_scan_drive_inspections` | 15min | Scan Google Drive for new inspection PDFs |
| `_run_nightly_maintenance` | 00:05 daily | Create scheduled maintenance calls |
| `_check_monitoring_calls` | 08:00 daily | Morning monitoring check |
| `_check_inspection_deficiency_escalation` | 6h | Escalate unresolved inspection deficiencies |

---

## Important Constraints

- **"חשוב מאד שלא תבצע שום שינוי בקוד שעובד כרגע"** — never touch working code unless fixing a bug in it
- SQLite for tests, PostgreSQL for production — all models use `sqlalchemy.types.Uuid` (not `postgresql.UUID`) and `JSON` (not `postgresql.JSONB`)
- Rate limiter must be disabled in tests: `app.state.limiter.enabled = False`
- PostgreSQL migrations wrapped in `if engine.dialect.name == "postgresql":` in lifespan
- 66 tests, all passing — run with `pytest tests/`

---

## Recently Completed Features

- Maintenance page: MAINTENANCE fault_type calls with urgency blink (LOW=green, MEDIUM=orange, HIGH/CRITICAL=flashing red)
- Location picker: Leaflet map modal in elevator detail + calls page
- After-hours caller confirmation: WhatsApp flow for non-RESCUE calls outside working hours
- Working hours settings UI: editable per-day schedule in admin panel
- Email poller fixed: UNSEEN-only, no date restriction, OVERQUOTA handling
- lift-agent-admin control plane: super-admin dashboard for managing tenants
