# Lift Agent — System Knowledge Base

This file is read automatically at the start of every Claude session.
**Update this file at the END of every session with all changes made.**

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
- Active dev branch: `claude/mystifying-mcnulty-a91ece`
- **NEVER push to main without explicit permission**
- After every commit: `git push -u origin claude/mystifying-mcnulty-a91ece`

---

## Server

- Host: `elevator-server` (Google Cloud VM, Google Cloud)
- Connect: `ssh dtsehtik@lift-agent.com`
- Stack: Docker Compose
- Services: `app` (FastAPI uvicorn), `db` (PostgreSQL 16), `nginx`, `certbot`, `ngrok`
- **Deploy command** (saved as `~/deploy.sh` on server):
  ```bash
  cd ~/elevator-service-api && git fetch origin claude/fix-elevator-assignment-error-aUvEz && git reset --hard origin/claude/fix-elevator-assignment-error-aUvEz && sudo docker compose up -d --build app
  ```
- Logs: `sudo docker compose logs app -f`
- **IMPORTANT**: Never edit files directly on the server. Always commit here → push → run `~/deploy.sh`
- **IMPORTANT**: `npm run build` was changed from `tsc && vite build` to `vite build` to prevent OOM during Docker build (TypeScript type-checking consumed all server RAM)

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
| AI — Reports | Gemini 2.0 Flash — natural language → filter params → narrative answer |
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
- **Elevator** — physical elevator unit
  - Fields: address, city, floor_count, latitude, longitude, serial_number, labor_file_number
  - Service: service_type (REGULAR/COMPREHENSIVE), service_contract (ANNUAL_6/ANNUAL_12)
  - Maintenance: `maintenance_times_per_year` (2/4/6/12, default=6), `maintenance_interval_days` (legacy), `last_service_date`, `next_service_date`
  - Inspection: last_inspection_date, next_inspection_date, inspector_name
  - CRM: customer_id (FK → Customer), management_company_id
- **ServiceCall** — a repair/rescue request
  - Fields: fault_type, status, priority, after_hours_pending, call_number (BIGINT, S+5 digits format)
  - call_number auto-assigned via PostgreSQL sequence `service_calls_call_number_seq`
- **Technician** — field technician (phone, whatsapp_number, role, is_available, current_latitude/longitude)
- **Assignment** — links ServiceCall ↔ Technician (status: PENDING_CONFIRMATION → ACCEPTED/REJECTED)
- **ManagementCompany** — building management company (caller_phones: TEXT[])
- **Contact** — contact directory. Has `elevator_id` FK (scoped per elevator, not per building)

### Supporting
- **MaintenanceSchedule** — planned quarterly/annual maintenance per elevator
- **InspectionReport** — safety inspection with checklist (deficiencies JSON with `done`, `action_notes` fields)
  - Fields: drive_file_id, labor_file_number, match_status (AUTO_MATCHED/PENDING_REVIEW/UNMATCHED)
  - report_status: NA / OPEN / PARTIAL / CLOSED
- **Building** — building record linked to elevators
- **WhatsAppMessage** — message log
- **ServiceCallEmailScan** — dedup table for processed service-call email message IDs
- **InspectionEmailScan** — dedup table for inspection report email message IDs
- **SystemSettings** — key-value store (working hours, field label overrides)
- **SavedView** — user-saved report views (columns, filters, sort)
- **Customer**, **Contract**, **Invoice**, **Lead**, **Part** — CRM/ERP models

### fault_type enum
`STUCK | DOOR | ELECTRICAL | MECHANICAL | SOFTWARE | RESCUE | MAINTENANCE | OTHER`

### ServiceCall.status
`OPEN → ASSIGNED → IN_PROGRESS → RESOLVED → CLOSED | MONITORING`

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
| `inspections` | `/inspection-reports` | Reports + checklist + `POST /rewrite-action-note` |
| `management_companies` | `/management-companies` | CRUD + elevator assignment |
| `webhooks` | `/webhooks` | WhatsApp + phone call webhooks + pending unmatched calls |
| `settings` | `/settings` | Working hours (GET/POST) |
| `analytics` | `/analytics` | Stats |
| `buildings` | `/buildings` | Building CRUD |
| `contacts` | `/contacts` | Contact directory (elevator_id filter supported) |
| `conversations` | `/conversations` | WhatsApp conversation history |
| `data_import` | `/import` | Excel/PDF import |
| `schedule` | `/schedule` | Schedule management |
| `reports` | `/reports` | Dynamic report builder + saved views + AI query |

---

## Key Services (`/app/services/`)

| Service | Purpose |
|---|---|
| `email_poller.py` | IMAP Gmail polling — pulls UNSEEN emails every 60s, marks as read after processing. Gemini parses content. |
| `ai_assignment_agent.py` | Assigns technician to service call using AI. Sends WhatsApp confirmation request (1=accept, 2=reject). |
| `whatsapp_service.py` | All WhatsApp messaging via Green API. notify_rescue_emergency, assign_with_confirmation, after_hours messages. |
| `working_hours.py` | In-memory working hours schedule. `is_working_hours()` checks if current time is within schedule. Hot-reloadable via settings endpoint. |
| `scheduler.py` | APScheduler jobs (see table below). All maintenance jobs restricted to Sun–Fri (no Saturday). |
| `inspection_email_poller.py` | Polls separate Gmail for inspection report emails (hourly). Deduplicates by message_id. |
| `inspection_service.py` | Processes inspection PDFs via Gemini Vision. Deduplicates by labor_file_number+inspection_date. |
| `drive_service.py` | Google Drive integration for inspection report PDFs. |
| `call_parser.py` | Parses incoming phone call data into structured fields. |
| `report_builder.py` | Dynamic multi-entity query engine. Schema cached in `_SCHEMAS` global. All column defs use `"filter"` key (not `"filter_attr"`). |
| `service_call_service.py` | When MAINTENANCE call resolved/closed → auto-advances elevator.next_service_date by interval. |
| `maintenance_service.py` | mark_overdue_maintenances, create/update/list MaintenanceSchedule records. |

---

## WhatsApp Flow

1. **Incoming call** → webhook `POST /webhooks/receive-call` → parse → find elevator → check working hours
2. **During hours**: AI assigns technician → sends WhatsApp "קריאה חדשה, 1=קבל 2=דחה"
3. **After hours (non-RESCUE)**: sends caller WhatsApp asking "1=אשר תוספת, 2=דחה למחר" → `after_hours_pending=True`
4. **Caller replies 1**: dispatch technician. Caller replies 2: defer.
5. **Technician replies 1**: accept → status ASSIGNED. Replies 2: reject → try next technician.
6. **RESCUE calls**: always dispatch immediately, blast ALL technicians.
7. **Unmatched calls** (no elevator found): saved to `incoming_call_logs` with match_status=UNMATCHED/PARTIAL → visible in PendingCallsPage → dispatcher can add new elevator or match to existing.

---

## Inspection Report Flow

1. **Email poller** (`inspection_email_poller.py`) or **Drive scanner** (`_scan_drive_inspections`) picks up PDF
2. `process_inspection_report()` in `inspection_service.py`:
   - Uploads to Google Drive (or uses existing drive_file_id if called from Drive scanner)
   - Calls Gemini Vision to extract: street, city, labor_file_number, inspection_date, deficiencies
   - **Dedup check**: if same labor_file_number + inspection_date exists within 30 days → skip
   - Matches to elevator: labor_file_number (tier 0) → address fuzzy match ≥90% (tier 1) → 30–90% (PENDING_REVIEW) → UNMATCHED
   - Creates InspectionReport record, notifies dispatcher via WhatsApp
3. **Deficiencies** stored as JSON array: `[{description, severity, done, action_notes}]`
4. Technician checks deficiency → modal opens → enters action description → optional AI rewrite to professional Hebrew via `POST /inspection-reports/rewrite-action-note`

---

## Reports Module (`/app/routers/reports.py` + `/app/services/report_builder.py`)

### Endpoints
- `GET /reports/schema` — all entity schemas (columns, filterable flags)
- `GET /reports/schema/{entity_type}` — single entity schema
- `POST /reports/query` — run dynamic query with filters/sort/pagination
- `GET /reports/export` — export to Excel (.xlsx)
- `POST /reports/ai-query` — natural language Hebrew → Gemini → filter params → execute → narrative answer
- `GET /reports/views` — list saved views
- `POST /reports/views` — create saved view
- `PUT /reports/views/{id}` — update saved view
- `DELETE /reports/views/{id}` — delete saved view

### Supported Entity Types
`service_calls`, `elevators`, `customers`, `invoices`, `inventory`, `maintenance`, `contracts`, `leads`, `inspections`

### Known Pitfall
Column defs in `report_builder.py` use `"filter"` key. The `filterable` flag in schema endpoints must check `v.get("filter") is not None` — **NOT** `v.get("filter_attr")`. This bug was fixed in both `get_all_schemas` and `get_entity_schema`.

---

## Frontend Pages (`/frontend/src/pages/`)

| Page | Route | Notes |
|---|---|---|
| `CallsPage` | `/calls` | Service calls list + detail. # column shows S00042 format. LocationPickerModal. |
| `ElevatorDetailPage` | `/elevators/:id` | Elevator details + location picker + Waze link. Maintenance frequency dropdown (2/4/6/12× per year). |
| `MaintenancePage` | `/maintenance` | Scheduled maintenance + OPEN MAINTENANCE calls with urgency blink. |
| `InspectionsPage` | `/inspections` | Inspection reports list + deficiency checklist. Checking deficiency opens action modal (voice + AI rewrite). |
| `TechAppPage` | `/tech/*` | Mobile technician interface. ReportsTab has same deficiency action modal. |
| `ReportsPage` | `/reports` | Dynamic report builder. AI query panel (violet box). Saved views. |
| `PendingCallsPage` | `/pending-calls` | Unmatched calls awaiting manual elevator assignment. Search with loading + error states. |
| `SettingsPage` | `/settings` | Working hours editor (admin only). |
| `WhatsAppAgentPage` | `/whatsapp-agent` | Conversation history viewer + system prompt editor + agent stats. |
| `HRPage` | `/hr` | HR records per employee — employment type, salary, dates. |
| `DashboardPage` | `/` | Mission Control — LiveStatusBar, KPI cards, priority queue, charts. |

### LocationPickerModal
Lazy-loads Leaflet from CDN. Click-to-pin, draggable marker, GPS button.
Used in ElevatorDetailPage and CallsPage.

---

## Scheduled Jobs (APScheduler)

| Job | Schedule | Day restriction | Purpose |
|---|---|---|---|
| `_poll_email_calls` | every 60s | — | Pull UNSEEN service-call emails from Gmail |
| `_check_pending_assignment_timeouts` | every 60s | — | Auto-cancel timed-out assignment confirmations |
| `_poll_inspection_emails` | every 1h | — | Pull inspection report emails |
| `_scan_drive_inspections` | every 15min | — | Scan Google Drive for new inspection PDFs |
| `_run_nightly_maintenance` | 00:05 daily | Sun–Fri only | Create scheduled maintenance calls |
| `_send_morning_maintenance_alerts` | 07:35 daily | Sun–Fri only | WhatsApp alerts for upcoming/overdue maintenance |
| `_check_monitoring_calls` | 08:00 daily | — | Morning monitoring check |
| `_check_inspection_deficiency_escalation` | every 6h | — | Escalate unresolved inspection deficiencies |

---

## Maintenance System

- `Elevator.maintenance_times_per_year` — visits per year: **2 / 4 / 6 / 12** (default: **6**)
- `Elevator.next_service_date` — computed from `last_service_date + (365 / times_per_year)` days
- Next service date always skips Saturday (Israeli day off): `while date.weekday() == 5: date += 1 day`
- When MAINTENANCE ServiceCall is RESOLVED or CLOSED → `_advance_next_service_date()` auto-sets next date
- Migration backfills `maintenance_times_per_year` from existing `maintenance_interval_days` values
- `maintenance_interval_days` kept for legacy reads; UI uses `maintenance_times_per_year` dropdown

---

## DB Migrations (in `app/main.py` lifespan)

All wrapped in `if engine.dialect.name == "postgresql":`. Key migrations:
- `elevator_id` FK on contacts table
- `call_number` BIGINT with sequence `service_calls_call_number_seq`
- `maintenance_times_per_year` INTEGER DEFAULT 6 on elevators
- Backfill: derive `next_service_date` from `last_service_date` for elevators missing it

---

## Important Constraints

- **Never touch working code unless fixing a bug in it**
- SQLite for tests, PostgreSQL for production — all models use `sqlalchemy.types.Uuid` (not `postgresql.UUID`) and `JSON` (not `postgresql.JSONB`)
- Rate limiter must be disabled in tests: `app.state.limiter.enabled = False`
- PostgreSQL migrations wrapped in `if engine.dialect.name == "postgresql":` in lifespan
- 66 tests, all passing — run with `pytest tests/`
- `npm run build` = `vite build` only (no `tsc`) to prevent OOM on server

---

## Known Issues / Watch Out For

- Maintenance page: MAINTENANCE fault_type calls with urgency blink (LOW=green, MEDIUM=orange, HIGH/CRITICAL=flashing red)
- Location picker: Leaflet map modal in elevator detail + calls page
- After-hours caller confirmation: WhatsApp flow for non-RESCUE calls outside working hours
- Working hours settings UI: editable per-day schedule in admin panel
- Email poller fixed: UNSEEN-only, no date restriction, OVERQUOTA handling
- lift-agent-admin control plane: super-admin dashboard for managing tenants
- ERP מלא: customers, quotes, contracts, invoices, inventory, leads, CRM
- Report Builder: custom fields, saved views, role permissions, date range filter, Excel/PDF export
- AI דוחות: POST /reports/ai-query — שאלה חופשית בעברית → Gemini → פילטרים → תוצאות + תשובה נרטיבית
- Nav config: הסתרה/שינוי שמות פריטי תפריט מהגדרות
- `report_builder.py` schema defs must match actual model columns — any mismatch causes `AttributeError` and crashes ALL report endpoints (the `_SCHEMAS` cache won't recover)
- When adding columns to report_builder, always verify the column exists in the model first
- Drive scanner (`_scan_drive_inspections`) passes `existing_drive_file_id` to `process_inspection_report` to avoid re-uploading files already in Drive
- Inspection dedup: checks `labor_file_number + inspection_date` within 30 days before creating new record
- Contacts are scoped per `elevator_id` (not building), preventing cross-elevator contamination
- Service call `call_number` displayed as `S00042` (S + 5-digit zero-padded) in UI

---

## Changes Made (11/05/2026)

### Navigation Redesign — Shell.tsx
- Replaced vertical sidebar with horizontal top bar + contextual side panels
- Header: dark gradient background (`#1a1b2e → #16213e → #0f3460`)
- Section tabs (9 total): דשבורד, שירות, כספים, קשרי לקוחות, פרויקטים, כח אדם, הגדרות, תמיכה, סוכן ווצאפ
- Active tab highlighted in blue with bottom border (`#74c0fc`)
- Side panel (220px) only appears for sections with sub-items; collapsed otherwise
- Mobile: burger → expanded navbar with all sections listed
- navConfig overrides applied to both header tabs and side-panel sub-items
- `DEFAULT_NAV_ITEMS` export preserved for SettingsPage compatibility

### WhatsApp Agent Management Page — `/whatsapp-agent`
- New page `WhatsAppAgentPage.tsx` with 3 tabs:
  - **שיחות**: filter by phone/name, chat bubble UI, voice transcription badge, cleanup unknown button
  - **הגדרות**: system prompt editor (monospace RTL textarea), save/cancel with dirty indicator
  - **סטטיסטיקות**: 8 metric cards (conversations, messages, voice, identified/unknown)
- Backend: `GET/POST /settings/agent-config` in `settings.py` (stores in system_settings table as `wa_agent_config`)
- Saving config immediately updates `chat_agent._SYSTEM_PROMPT` in memory (no restart needed)

### Known Pitfall — settings table schema
- `system_settings` table uses key/value TEXT columns (from first migration), NOT the SystemSettings ORM model schema (id/key/modules)
- `_get_setting` / `_set_setting` helpers in `settings.py` use raw SQL → works correctly in production
- On fresh DB: `create_all` creates table with ORM schema → settings router queries fail. Only affects fresh installs.

---

## Known Bugs Fixed (10/05/2026)

### report_builder.py — שגיאות schemas
- `Invoice.invoice_type` — לא קיים במודל, הוסר
- `Part.unit_cost` → `cost_price`, `Part.unit_price` → `sell_price`, הוסר `location`
- `Contract.monthly_value` → `monthly_price`, `Contract.auto_renew` → `auto_invoice`
- 3 עמודות עם `label` במקום `label_he`: `resolution_notes`, `last_service_date`, `next_service_date`
- הוספו עמודות `technician_name` ו-`customer_name` לקריאות שירות בדוחות
- **כלל:** לפני deploy, לאמת schemas: `python3 -c "from app.services.report_builder import _build_schemas; _build_schemas(); print('OK')"`

### PendingCallsPage — חיפוש מעלית
- `GET /elevators/` עם slash בסוף → SPA middleware מחזיר HTML במקום JSON
- **תיקון:** תמיד `/elevators` ללא trailing slash
- הוסף `search` param ל-backend (`ilike` על address + city + building_name)
- הוסף loading spinner + error handling ל-modal

### webhooks.py — שיוך קריאה ממתינה למעלית
- `log.call_type = 'אחר'` (3 תווים) נכשל ב-`ServiceCallCreate.description min_length=5`
- **תיקון:** preserve call_type אם ≥5 תווים, אחרת `"קריאת שירות: {call_type}"` או `"קריאת שירות"`
- validation על fault_type ו-priority לפני יצירת ServiceCallCreate
- reported_by: שם אם ≥2 תווים, אחרת טלפון

### git pull על השרת
- שגיאה "divergent branches" — פתרון: `git config --global pull.rebase false` (פעם אחת על השרת)
- לעולם לא להשתמש ב-`git pull` סתם — אם בעיה: `git fetch origin && git reset --hard origin/$(git branch --show-current)`

---

## Session End Checklist

At the end of every session:
1. Commit and push all changes to `main`
2. Update this CLAUDE.md with any new features, bug fixes, or architectural changes
3. Tell the user to run `~/deploy.sh` on the server
