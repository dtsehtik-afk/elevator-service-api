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
- Active dev branch: `claude/project-reset-EUIb0`
- **NEVER push to main without explicit permission**
- After every commit: `git push -u origin claude/project-reset-EUIb0`

---

## Server

- Host: `elevator-server` (Google Cloud VM, Google Cloud)
- Connect: `ssh dtsehtik@lift-agent.com`
- Stack: Docker Compose
- Services: `app` (FastAPI uvicorn), `db` (PostgreSQL 16), `nginx`, `certbot`, `ngrok`
- **Deploy command** (saved as `~/deploy.sh` on server):
  ```bash
  cd ~/elevator-service-api && git fetch origin main && git reset --hard origin/main && sudo docker compose up -d --build app
  ```
- Logs: `sudo docker compose logs app -f`
- **IMPORTANT**: Never edit files directly on the server. Always commit here → push → run `~/deploy.sh`
- **IMPORTANT**: `npm run build` = `vite build` only (no `tsc`) to prevent OOM during Docker build
- **IMPORTANT**: `frontend/dist` is excluded from Docker build context to prevent stale bundle
- **IMPORTANT**: `index.html` served with `no-store` to prevent Cloudflare caching old bundles

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
| AI — Chat agent | Gemini (WhatsApp chatbot for technicians/managers, tool-use) |
| AI — Reports | Gemini 2.0 Flash — natural language → filter params → narrative answer |
| AI — Documents | Gemini Vision — contract/agreement analysis |
| Voice transcription | OpenAI Whisper |
| Maps | Google Maps API |
| Address lookup | data.gov.il API — Israeli address auto-correction + autocomplete |
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
- Tenant name/industry synced from admin console → tenant app on update

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
  - CRM: customer_id (FK → Customer), management_company_id, consultant_id
  - Responsible technician: `responsible_technician_id` (FK → Technician) — first in line for assignment
  - Maintenance technician: `maintenance_technician_id` (FK → Technician) — auto-assigned for MAINTENANCE calls
- **ServiceCall** — a repair/rescue request
  - Fields: fault_type, status, priority, after_hours_pending, call_number (BIGINT, S+5 digits format)
  - SLA: `sla_duration` computed from OPEN→RESOLVED timestamps
  - call_number auto-assigned via PostgreSQL sequence `service_calls_call_number_seq`
- **Technician** — field technician (phone, whatsapp_number, role, is_available, current_latitude/longitude, last_location_at)
  - Roles: TECHNICIAN, SENIOR_TECHNICIAN, MAINTENANCE_TECHNICIAN, MANAGER
- **Assignment** — links ServiceCall ↔ Technician (status: PENDING_CONFIRMATION → ACCEPTED/REJECTED)
- **ManagementCompany** — building management company (caller_phones: TEXT[])
- **Contact** — contact directory. Has `elevator_id` FK (scoped per elevator, not per building)

### Supporting
- **MaintenanceSchedule** — planned quarterly/annual maintenance per elevator
- **InspectionReport** — safety inspection with checklist (deficiencies JSON with `done`, `action_notes` fields)
  - Fields: drive_file_id, labor_file_number, match_status (AUTO_MATCHED/PENDING_REVIEW/UNMATCHED)
  - report_status: NA / OPEN / PARTIAL / CLOSED
  - PENDING_REVIEW triggered also by labor_file_number mismatch between extracted vs. elevator record
- **Building** — building record linked to elevators
- **WhatsAppMessage** — message log (includes bot replies)
- **ServiceCallEmailScan** — dedup table for processed service-call email message IDs
- **InspectionEmailScan** — dedup table for inspection report email message IDs
- **SystemSettings** — key-value store (working hours, field label overrides, `wa_agent_config`, `bot_qa_entries`)
- **SavedView** — user-saved report views (columns, filters, sort)
- **ActivityLog** — system event stream (who did what, when)
- **Customer**, **Contract**, **Invoice**, **Lead**, **Part**, **Quote**, **Project** — CRM/ERP models
- **PartRequest** — technician part replacement request with approval workflow
- **BotQAEntry** — knowledge base entries for WhatsApp chat agent
- **Consultant** — external consultant linked to elevators

### fault_type enum
`STUCK | DOOR | ELECTRICAL | MECHANICAL | SOFTWARE | RESCUE | MAINTENANCE | OTHER`

### ServiceCall.status
`OPEN → ASSIGNED → IN_PROGRESS → RESOLVED → CLOSED | MONITORING`

### Technician roles
`TECHNICIAN | SENIOR_TECHNICIAN | MAINTENANCE_TECHNICIAN | MANAGER`

---

## API Routers (`/app/routers/`)

| Router | Prefix | Notes |
|---|---|---|
| `auth` | `/auth` | JWT login, register, me, TOTP 2FA, login history |
| `elevators` | `/elevators` | CRUD + location update + elevator log (date filter + export) |
| `service_calls` | `/service-calls` | CRUD + filters + SLA |
| `assignments` | `/assignments` | Manual assign, confirm, reject |
| `technicians` | `/technicians` | CRUD + location POST |
| `technician_app` | `/technician-app` | Mobile app endpoints |
| `maintenance` | `/maintenance` | Scheduled maintenance |
| `inspections` | `/inspection-reports` | Reports + checklist + `POST /rewrite-action-note` |
| `management_companies` | `/management-companies` | CRUD + elevator assignment |
| `webhooks` | `/webhooks` | WhatsApp + phone call webhooks + pending unmatched calls |
| `settings` | `/settings` | Working hours, agent config (GET/POST), nav config |
| `analytics` | `/analytics` | Stats |
| `buildings` | `/buildings` | Building CRUD |
| `contacts` | `/contacts` | Contact directory (elevator_id filter supported) |
| `conversations` | `/conversations` | WhatsApp conversation history |
| `data_import` | `/import` | Excel/PDF import |
| `schedule` | `/schedule` | Schedule management |
| `reports` | `/reports` | Dynamic report builder + saved views + AI query |
| `activity_log` | `/activity-log` | Real-time event stream |
| `addresses` | `/addresses` | data.gov.il address autocomplete |
| `admin_console` | `/admin-console` | Tenant management endpoints |
| `admin_control` | `/admin-control` | Super-admin control plane |
| `ai` | `/ai` | AI utility endpoints |
| `bot_qa` | `/bot-qa` | WhatsApp agent QA knowledge base CRUD |
| `consultants` | `/consultants` | Consultant directory |
| `contracts` | `/contracts` | Contract management |
| `custom_fields` | `/custom-fields` | Custom field definitions |
| `customers` | `/customers` | Customer CRM |
| `documents` | `/documents` | Document upload + AI analysis |
| `erp_dashboard` | `/erp-dashboard` | ERP KPI dashboard |
| `hr` | `/hr` | HR records |
| `inventory` | `/inventory` | Parts inventory |
| `invoices` | `/invoices` | Invoice management |
| `leads` | `/leads` | Lead CRM |
| `part_requests` | `/part-requests` | Part replacement approval workflow |
| `projects` | `/projects` | Project management |
| `quotes` | `/quotes` | Quote management |
| `search` | `/search` | Global search |

---

## Key Services (`/app/services/`)

| Service | Purpose |
|---|---|
| `email_poller.py` | IMAP Gmail polling — pulls UNSEEN emails every 60s, `BODY.PEEK` (no mark-as-read side effects). Gemini parses content. |
| `ai_assignment_agent.py` | Assigns technician to service call using AI. Respects responsible_technician_id + maintenance_technician_id. |
| `whatsapp_service.py` | All WhatsApp messaging via Green API. notify_rescue_emergency, assign_with_confirmation, after_hours messages. |
| `working_hours.py` | In-memory working hours schedule. `is_working_hours()` checks if current time is within schedule. Hot-reloadable. |
| `scheduler.py` | APScheduler jobs (see table below). All maintenance jobs restricted to Sun–Fri (no Saturday). |
| `inspection_email_poller.py` | Polls separate Gmail for inspection report emails (hourly). Deduplicates by message_id. |
| `inspection_service.py` | Processes inspection PDFs via Gemini Vision. Dedup by labor_file_number+inspection_date. PENDING_REVIEW on mismatch. |
| `drive_service.py` | Google Drive integration for inspection report PDFs. |
| `call_parser.py` | Parses incoming phone call data into structured fields. |
| `report_builder.py` | Dynamic multi-entity query engine. Schema cached in `_SCHEMAS` global. Column defs use `"filter"` key. |
| `service_call_service.py` | When MAINTENANCE call resolved/closed → auto-advances elevator.next_service_date by interval. |
| `maintenance_service.py` | mark_overdue_maintenances, create/update/list MaintenanceSchedule records. |
| `chat_agent.py` | WhatsApp conversational AI. Gemini tool-use against live DB. Role-based permissions. QA knowledge base. |
| `activity_service.py` | Records activity log events. |
| `address_service.py` | data.gov.il address validation + autocomplete for Israeli addresses. |
| `document_ai_service.py` | Gemini Vision analysis of uploaded contracts/agreements/PDFs. |
| `report_ai_agent.py` | AI-powered report query: Hebrew NL → Gemini → filter params → execute → narrative answer. |
| `route_service.py` | Technician route optimization (multi-stop, dedup). |
| `inventory_service.py` | Parts inventory management. |
| `part_request_service.py` | Part replacement request lifecycle + WhatsApp notifications. |

---

## WhatsApp Flow

1. **Incoming call** → webhook `POST /webhooks/receive-call` → parse → find elevator → check working hours
2. **During hours**: AI assigns technician → sends WhatsApp "קריאה חדשה, 1=קבל 2=דחה"
   - Checks `responsible_technician_id` first, then `maintenance_technician_id` for MAINTENANCE calls
3. **After hours (non-RESCUE)**: sends caller WhatsApp asking "1=אשר תוספת, 2=דחה למחר" → `after_hours_pending=True`
4. **Caller replies 1**: dispatch technician. Caller replies 2: defer.
5. **Technician replies 1**: accept → status ASSIGNED. Replies 2: reject → try next technician.
6. **RESCUE calls**: always dispatch immediately, blast ALL technicians.
7. **Unmatched calls** (no elevator found): saved to `incoming_call_logs` with match_status=UNMATCHED/PARTIAL → visible in PendingCallsPage → dispatcher can add new elevator or match to existing.

---

## WhatsApp Chat Agent (`/app/services/chat_agent.py`)

Conversational AI for technicians and managers via WhatsApp.

### Architecture
- **Gemini tool-use** — handles all intent types (questions + actions)
- System prompt loaded from DB (`wa_agent_config` in system_settings); hot-reloadable without restart
- Bot replies saved to WhatsApp history (WhatsAppMessage table)
- Role-based permissions: MANAGER gets full access, TECHNICIAN gets limited scope

### Tools available to the bot
| Tool | Description |
|---|---|
| `search_elevators` | Search by address, city, building, serial number |
| `get_elevator_calls` | Call history for a specific elevator |
| `get_recent_calls` | Calls from the last N days (filterable) |
| `get_technician_location` | Last known GPS location + staleness |
| `search_inspection_reports` | Search inspection reports by elevator/date |
| `get_maintenance_schedule` | Upcoming/overdue maintenance |
| `create_service_call` | Create new service call (requires confirmation) |
| `assign_technician` | Assign technician to call (requires confirmation) |

### QA Knowledge Base (`bot_qa.py` router + `BotQAEntry` model)
- Managers can add Q&A pairs via the WhatsApp Agent page
- Auto-built from resolved service calls history
- Injected into bot context for domain-specific answers

### Key behaviors
- **Explicit confirmation required** before any action (create/assign) — NLP-inferred intent is not enough
- **Intent detection fix**: questions are never misclassified as action intents
- **Context awareness**: bot tracks conversation thread, knows who is talking

---

## Inspection Report Flow

1. **Email poller** (`inspection_email_poller.py`) or **Drive scanner** (`_scan_drive_inspections`) picks up PDF
2. `process_inspection_report()` in `inspection_service.py`:
   - Uploads to Google Drive (or uses existing drive_file_id if called from Drive scanner)
   - Calls Gemini Vision to extract: street, city, labor_file_number, inspection_date, deficiencies
   - **Dedup check**: if same labor_file_number + inspection_date exists within 30 days → skip
   - Matches to elevator: labor_file_number (tier 0) → address fuzzy match ≥90% (tier 1) → 30–90% (PENDING_REVIEW) → UNMATCHED
   - **Mismatch check**: if extracted labor_file_number ≠ elevator.labor_file_number → set PENDING_REVIEW
   - Creates InspectionReport record, notifies dispatcher via WhatsApp
3. **Deficiencies** stored as JSON array: `[{description, severity, done, action_notes}]`
4. Technician checks deficiency → modal opens → enters action description → optional AI rewrite to professional Hebrew via `POST /inspection-reports/rewrite-action-note`

---

## GPS & Technician Location

- Technician app sends GPS every **60 seconds** (heartbeat) using `maximumAge: 0` (always fresh)
- `last_location_at` timestamp stored on Technician model
- UI shows staleness: "לפני 3 דקות" — never says "עכשיו" for data older than 30s
- WhatsApp location updates also update `last_location_at`
- Age-aware call titles in morning alerts: mentions how old the call is

---

## SLA

- `sla_duration` computed from OPEN → RESOLVED timestamps
- Shown in call detail view and reports
- SLA badge in calls list with readability improvements

---

## Address Autocomplete (data.gov.il)

- `GET /addresses/autocomplete?q=...` — queries Israeli government address API
- Returns normalized street + city
- Used in elevator creation/edit forms for accurate Israeli addresses
- Auto-correction: if saved address differs from gov.il canonical form, suggests correction

---

## Two-Factor Authentication (TOTP)

- `POST /auth/totp/setup` — generates QR code for Google Authenticator
- `POST /auth/totp/verify` — verifies and enables TOTP
- `POST /auth/totp/disable` — disables TOTP
- Login history stored per user (IP, timestamp, device)
- Login with TOTP: standard JWT flow + `totp_code` param

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

### Sort fix
Report sort column change now triggers re-fetch (was broken — `sortBy` state change wasn't wired to query).

---

## Frontend Pages (`/frontend/src/pages/`)

| Page | Route | Notes |
|---|---|---|
| `DashboardPage` | `/` | Mission Control — LiveStatusBar, KPI cards, priority queue, charts, ActivityFeed |
| `CallsPage` | `/calls` | Service calls list + detail. # column shows S00042 format. LocationPickerModal. SLA badge. |
| `ElevatorDetailPage` | `/elevators/:id` | Elevator details + location picker + Waze link. Maintenance frequency. Responsible/maintenance technician. |
| `MaintenancePage` | `/maintenance` | Scheduled maintenance + OPEN MAINTENANCE calls with urgency blink. |
| `InspectionsPage` | `/inspections` | Inspection reports list + deficiency checklist. Action modal (voice + AI rewrite). |
| `TechAppPage` | `/tech/*` | Mobile technician interface. Clickable call cards + enriched metadata. Deficiency action modal. |
| `ReportsPage` | `/reports` | Dynamic report builder. AI query panel (violet box). Saved views. Sort fix applied. |
| `PendingCallsPage` | `/pending-calls` | Unmatched calls awaiting manual elevator assignment. Search with loading + error states. |
| `SettingsPage` | `/settings` | Working hours editor (admin only). Nav config. |
| `WhatsAppAgentPage` | `/whatsapp-agent` | Conversation history + system prompt editor + agent stats + QA knowledge base. |
| `HRPage` | `/hr` | HR records per employee — employment type, salary, dates. |
| `CustomersPage` | `/customers` | Customer CRM with sortable columns. |
| `CustomerDetailPage` | `/customers/:id` | Full customer detail with elevator relationships. |
| `LeadsPage` | `/leads` | Lead CRM → project chain. |
| `ProjectsPage` | `/projects` | Project management → auto-activates elevators + auto-invoicing on completion. |
| `ContractsPage` | `/contracts` | Contract management. |
| `QuotesPage` / `QuoteDetailPage` | `/quotes` | Quote management. |
| `InvoicesPage` | `/invoices` | Invoice management. |
| `InventoryPage` | `/inventory` | Parts inventory. Part images. Delete with confirmation. |
| `PartRequestsPage` | `/part-requests` | Technician part replacement requests + approval workflow. |
| `ERPDashboardPage` | `/erp` | ERP KPI overview. |
| `ManagementCompaniesPage` | `/management-companies` | Management company CRUD. |
| `TechniciansPage` | `/technicians` | Technician management. |
| `MapPage` | `/map` | Live technician map. |
| `ImportPage` | `/import` | Excel/PDF bulk import. AI Excel import. |
| `AdminConsolePage` | `/admin` | Tenant admin panel (super-admin only). |
| `ConsultantsPage` | `/consultants` | Consultant directory. |
| `RolesPage` | `/roles` | Role permissions management. |
| `ConversationsPage` | `/conversations` | WhatsApp conversation viewer. |
| `SupportPage` | `/support` | Support page. |
| `LoginPage` | `/login` | Login + TOTP 2FA. |

### Key Components
- **LocationPickerModal** — Lazy-loads Leaflet from CDN. Click-to-pin, draggable marker, GPS button. Used in ElevatorDetailPage and CallsPage.
- **CustomerSearchSelect** — Autocomplete with contact preview, used across all forms with customer FK.
- **ActivityFeed** — Real-time event stream component on Dashboard + ERP dashboard.
- **DocumentUploadPanel** — File upload with Gemini AI analysis for contracts/agreements.
- **GlobalSearch** — Cross-entity search bar.
- **AIRefineButton** — Inline AI text improvement button (used in notes, descriptions).

---

## Scheduled Jobs (APScheduler)

| Job | Schedule | Day restriction | Purpose |
|---|---|---|---|
| `_poll_email_calls` | every 60s | — | Pull UNSEEN service-call emails from Gmail (BODY.PEEK) |
| `_check_pending_assignment_timeouts` | every 60s | — | Auto-cancel timed-out assignment confirmations |
| `_poll_inspection_emails` | every 1h | — | Pull inspection report emails |
| `_scan_drive_inspections` | every 15min | — | Scan Google Drive for new inspection PDFs |
| `_run_nightly_maintenance` | 00:05 daily | Sun–Fri only | Create scheduled maintenance calls |
| `_send_morning_maintenance_alerts` | 07:35 daily | Sun–Fri only | WhatsApp alerts — batched per manager, age-aware titles, deduped |
| `_check_monitoring_calls` | 08:00 daily | — | Morning monitoring check |
| `_check_inspection_deficiency_escalation` | every 6h | — | Escalate unresolved inspection deficiencies |

---

## Maintenance System

- `Elevator.maintenance_times_per_year` — visits per year: **2 / 4 / 6 / 12** (default: **6**)
- `Elevator.next_service_date` — computed from `last_service_date + (365 / times_per_year)` days
- Next service date always skips Saturday (Israeli day off): `while date.weekday() == 5: date += 1 day`
- When MAINTENANCE ServiceCall is RESOLVED or CLOSED → `_advance_next_service_date()` auto-sets next date
- `Elevator.maintenance_technician_id` — if set, MAINTENANCE calls auto-assigned to this technician
- `Elevator.responsible_technician_id` — if set, all calls try this technician first
- Migration backfills `maintenance_times_per_year` from existing `maintenance_interval_days` values
- `maintenance_interval_days` kept for legacy reads; UI uses `maintenance_times_per_year` dropdown
- Morning alerts: batched per manager (one WhatsApp message with all elevators), each service call appears once (deduped)

---

## Lead → Project → Elevator Chain

When a project is marked complete:
1. Linked elevators set to `active = True`
2. Auto-invoice generated from project contract value
3. Service contract starts from project completion date

This closes the full CRM-to-service lifecycle loop.

---

## Part Requests Workflow

1. Technician creates part request from mobile app or tech page
2. Manager notified via WhatsApp (`send_whatsapp_message` in `whatsapp_service.py`)
3. Manager approves/rejects via UI (`PartRequestsPage`)
4. Approved: inventory deducted, technician notified
5. Rejected: technician notified with reason

Bug fixed: `send_whatsapp_message` was a private `_send_whatsapp_message` — renamed to public.
Bug fixed: approve/reject buttons used `s.role` instead of `s.userRole` — never showed for managers.

---

## DB Migrations (in `app/main.py` lifespan)

All wrapped in `if engine.dialect.name == "postgresql":`. Key migrations:
- `elevator_id` FK on contacts table
- `call_number` BIGINT with sequence `service_calls_call_number_seq`
- `maintenance_times_per_year` INTEGER DEFAULT 6 on elevators
- `maintenance_technician_id`, `responsible_technician_id` FKs on elevators
- `last_location_at` TIMESTAMP on technicians
- `sla_duration` on service_calls
- `system_settings` value column (fixes ORM schema mismatch on fresh installs)
- Parts table: barcode, weight, dimensions, storage_slot and other missing columns
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

- **report_builder.py schema**: defs must match actual model columns — mismatch causes `AttributeError` and crashes ALL report endpoints. Validate: `python3 -c "from app.services.report_builder import _build_schemas; _build_schemas(); print('OK')"`
- **system_settings table**: uses key/value TEXT columns (raw SQL helpers `_get_setting`/`_set_setting`). On fresh DB, `create_all` creates wrong schema — only affects fresh installs.
- **Trailing slash on `/elevators/`**: SPA middleware returns HTML instead of JSON. Always use `/elevators` (no trailing slash).
- **WhatsApp bot actions**: always require explicit user confirmation before executing — NLP intent alone is insufficient.
- **Drive scanner**: passes `existing_drive_file_id` to `process_inspection_report` to avoid re-uploading.
- **Inspection dedup**: checks `labor_file_number + inspection_date` within 30 days before creating new record.
- **Contacts scoped per `elevator_id`** (not building) — prevents cross-elevator contamination.
- **Service call `call_number`** displayed as `S00042` (S + 5-digit zero-padded) in UI.
- **git pull on server**: use `git fetch origin && git reset --hard origin/main` — never plain `git pull`.
- **Mantine v7**: tab values must never be empty string — use `'ALL'` or another non-empty default.

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

---

## Changes Made (12–22/05/2026)

### WhatsApp Chat Agent — Full Refactor
- Gemini now handles all intents (questions + actions) via tool-use
- System prompt loaded from DB on startup + hot-reloadable
- Bot replies saved to WhatsApp history
- Role-based permissions: MANAGER vs TECHNICIAN scope
- QA knowledge base: auto-built from resolved calls + manual entries via `/bot-qa`
- Intent detection fix: questions no longer misclassified as action intents
- Explicit confirmation required before any action (create_service_call, assign_technician)
- Context awareness: bot tracks thread, knows caller identity
- `search_inspection_reports` tool added to bot

### GPS Tracking Improvements
- `maximumAge: 0` — always requests fresh GPS (no cached position)
- Heartbeat every 60 seconds from technician app
- `last_location_at` timestamp on Technician model
- WhatsApp location messages update `last_location_at`
- UI shows staleness: "לפני X דקות" — never says "עכשיו" for stale data
- Morning maintenance alerts show age-aware call titles

### SLA
- `sla_duration` field on ServiceCall (OPEN → RESOLVED duration)
- SLA badge in calls list with improved readability
- SLA duration shown in call detail and reports

### Address Autocomplete (data.gov.il)
- `GET /addresses/autocomplete` endpoint queries Israeli government address database
- Used in elevator create/edit forms
- Auto-corrects non-canonical Israeli addresses

### Two-Factor Authentication (TOTP)
- Google Authenticator compatible TOTP setup, verify, disable endpoints
- Login history per user (IP, timestamp, device)
- Login flow supports optional `totp_code` param

### New Roles
- `MAINTENANCE_TECHNICIAN` role added
- `Elevator.maintenance_technician_id` — auto-assigned for MAINTENANCE fault_type calls
- `Elevator.responsible_technician_id` — first in line for all call types

### CRM/ERP Enhancements
- Lead → Project → Elevator activation chain complete
- Project completion: activates elevators + auto-generates invoice
- Industry selector replaces company icon field (auto-derives icon from industry)
- `CustomerSearchSelect` component — autocomplete across all forms with customer FK
- Consultant model + router + page

### Activity Log Feed
- Real-time event stream: who did what, when
- `ActivityLog` model + `activity_service.py`
- `ActivityFeed` component on DashboardPage and ERPDashboardPage

### Part Requests Workflow
- Full approval lifecycle: create → notify manager → approve/reject → inventory update
- Part images support in inventory
- AI document analysis for contracts/agreements (Gemini Vision via `DocumentUploadPanel`)
- Bug fixes: public `send_whatsapp_message`, `userRole` store key fix

### Inspection Improvements
- PENDING_REVIEW now also triggered by labor_file_number mismatch (extracted ≠ elevator record)
- Deduplication of morning reminder WhatsApp alerts (each call appears once)

### Reports / Data
- Report sort column change now triggers re-fetch (was broken)
- Sortable columns added to customers list
- Elevator log: date range filter + Excel export
- AI Excel import for bulk elevator data

### Infrastructure / Bug Fixes
- `frontend/dist` excluded from Docker build context (prevents stale bundle on deploy)
- `index.html` served with `Cache-Control: no-store` (prevents Cloudflare caching old bundles)
- `system_settings` value column migration (fixes ORM schema mismatch on fresh installs)
- Parts table missing columns migration: barcode, weight, dimensions, storage_slot
- Email poller uses `BODY.PEEK` (no side effects on mail server read state)
- Tenant name/industry synced from admin console to tenant app

---

## Known Bugs Fixed (10/05/2026)

### report_builder.py — שגיאות schemas
- `Invoice.invoice_type` — לא קיים במודל, הוסר
- `Part.unit_cost` → `cost_price`, `Part.unit_price` → `sell_price`, הוסר `location`
- `Contract.monthly_value` → `monthly_price`, `Contract.auto_renew` → `auto_invoice`
- 3 עמודות עם `label` במקום `label_he`: `resolution_notes`, `last_service_date`, `next_service_date`
- הוספו עמודות `technician_name` ו-`customer_name` לקריאות שירות בדוחות

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

---

## Session End Checklist

At the end of every session:
1. Commit and push all changes to the active dev branch
2. Update this CLAUDE.md with any new features, bug fixes, or architectural changes
3. Tell the user to run `~/deploy.sh` on the server
