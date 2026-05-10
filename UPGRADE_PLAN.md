# Lift Agent — Upgrade Plan

> Last updated: 2026-05-10

---

## Current State Assessment

| Feature Area | Already Built | Missing |
|---|---|---|
| Deep linking | Partial — `/customers/:id`, `/elevators/:id`, `/quotes/:id` routes exist | Entity IDs in tables are not clickable links; dashboard widgets are not clickable |
| 360 Customer View | CustomerDetailPage exists with related data | No tabs for Invoices, Debts, Safety Inspector Reports |
| AI Reports | AI chat in ReportsPage exists (Gemini) | No voice/textarea AI refinement button |
| Admin Console | `admin_control.py` + Settings page exist | No unified visual "toggle modules ON/OFF" UI |
| Technical specs | Elevator model has some fields | Missing: Motor type, Controller model, Door type, Pit/Headroom |
| Safety expiry indicators | None | Green/Red visual alerts |
| SLA tracking | Calls have priority levels | No SLA deadline field or breach indicator |
| Inventory barcodes | InventoryPage exists | No barcode scan input support |
| Gantt/Projects | None | Entire Construction/Projects module |

---

## Phase 1 — Hyper-Connectivity (Deep Linking)
**Effort: 1–2 days | Risk: Low**

### A. Clickable entity IDs in all tables
Every table that shows an ID, customer name, elevator SN, invoice number wraps it in a `<Link>` to the detail page.

Affected pages:
- [ ] CallsPage
- [ ] MaintenancePage
- [ ] InspectionsPage
- [ ] InvoicesPage
- [ ] QuotesPage
- [ ] ContractsPage
- [ ] InventoryPage
- [ ] LeadsPage
- [ ] TechniciansPage

### B. Dashboard widgets → filtered list views
Each KPI card/chart on DashboardPage and ERPDashboardPage becomes a link.

Examples:
- "12 Open Calls" → `/calls?status=OPEN`
- "3 Critical" → `/calls?priority=CRITICAL`
- Chart segments become clickable

Affected pages:
- [ ] DashboardPage KPI cards
- [ ] ERPDashboardPage KPI cards
- [ ] Chart segment click handlers

### C. Customer 360 — add missing tabs
CustomerDetailPage gets tabs: **Elevators | Service Calls | Contracts | Invoices | Debt Summary | Inspection Reports**

- [ ] Elevators tab
- [ ] Service Calls tab
- [ ] Contracts tab
- [ ] Invoices tab
- [ ] Debt Summary tab
- [ ] Inspection Reports tab

---

## Phase 2 — Branch & Field Completeness
**Effort: 1–2 days | Risk: Medium (model changes via ALTER)**

### A. Elevator technical specs
New fields via startup `ALTER TABLE IF NOT EXISTS`:
```sql
motor_type VARCHAR
controller_model VARCHAR
door_type VARCHAR
pit_depth_cm INTEGER
headroom_cm INTEGER
safety_certificate_expiry DATE
```

- [ ] Backend: add fields to Elevator model + migration
- [ ] Frontend: editable fields in ElevatorDetailPage
- [ ] Frontend: colored expiry badge (green/orange/red) based on days remaining

### B. SLA tracking on Service Calls
New field `sla_deadline TIMESTAMP` on ServiceCall.

Computed at creation by priority:
- CRITICAL = 4h
- HIGH = 8h
- MEDIUM = 24h
- LOW = 72h

- [ ] Backend: add `sla_deadline` field + auto-compute logic
- [ ] Frontend: countdown badge in CallsPage
- [ ] Frontend: countdown badge in CallDetail
- [ ] Frontend: red color when breached

### C. Inventory barcode scan
Text input in InventoryPage that listens for barcode scanner keystrokes (HID keyboard — rapid string + Enter). Filters parts list immediately.

- [ ] InventoryPage: barcode input field

### D. Construction/Projects module (new)
New page `/projects` with Gantt chart.

Models:
- `Project` (site, status, start/end date)
- `ProjectTask` (task, assignee, dates)

- [ ] Backend: Project + ProjectTask models + CRUD router
- [ ] Frontend: ProjectsPage with Gantt view

---

## Phase 3 — AI Speech-to-Professional (Hebrew Refinement)
**Effort: 1 day | Risk: Low**

Reusable `useAIRefinement()` hook + `AIRefineButton` component next to every `<Textarea>` for notes/actions.

Flow: raw text → POST `/ai/refine-text` → Gemini prompt → formal Hebrew → replaces textarea

Backend prompt:
> "You are a professional elevator technician report writer. Rewrite the following in formal, high-level Hebrew. Input: {text}"

- [ ] Backend: new `app/routers/ai.py` with `/ai/refine-text` endpoint
- [ ] Frontend: `AIRefineButton.tsx` component
- [ ] Add to CallsPage (actions/notes fields)
- [ ] Add to InspectionsPage (deficiency notes)
- [ ] Add to QuoteDetailPage (description)
- [ ] Add to InvoicesPage (notes)

---

## Phase 4 — Admin Console (Module Toggle UI)
**Effort: 1 day | Risk: Low**

New page `/admin` (ADMIN role only). Three panels:

1. **Module Toggles** — toggle switches per module (Field Service, ERP, Reports, HR, Inspections…)
2. **Nav Config** — visual checkbox list to show/hide nav items (move from SettingsPage)
3. **System Health** — open calls count, active technicians, last email poll time

- [ ] Frontend: AdminConsolePage at `/admin`
- [ ] Module Toggles panel (consuming `admin_control.py` endpoints)
- [ ] Nav Config panel
- [ ] System Health panel

---

## Phase 5 — UX / Mission Control Dashboard
**Effort: 1–2 days | Risk: Low**

### A. Dashboard redesign
- [ ] Larger KPI cards (min height ~80px), high-contrast, icon + number + trend indicator
- [ ] All cards clickable (links to filtered views — Phase 1 prerequisite)

### B. Global search (Spotlight)
Mantine `@mantine/spotlight` component, keyboard shortcut `Ctrl+K`.

Searches across: elevators (SN/address), customers, calls, technicians.

- [ ] Backend: new `/search?q=` endpoint querying multiple tables
- [ ] Frontend: Spotlight component wired to `/search`

### C. Mobile tap targets
- [ ] Audit all table action buttons — minimum `size="md"`
- [ ] Audit TechAppPage button sizes

---

## Execution Summary

| Phase | Description | Effort | Status |
|---|---|---|---|
| Phase 1 | Deep links in tables + dashboard clickable widgets | 1–2 days | ⬜ Not started |
| Phase 2 | Customer 360 tabs + Elevator tech specs + Safety expiry badges | 1–2 days | ⬜ Not started |
| Phase 3 | AI Refine button (new endpoint + component) | 1 day | ⬜ Not started |
| Phase 4 | SLA tracking (model + UI) | 1 day | ⬜ Not started |
| Phase 5 | Admin Console page | 1 day | ⬜ Not started |
| Phase 6 | Global search (Spotlight) | 1 day | ⬜ Not started |
| Phase 7 | Construction/Projects module (Gantt) | 2–3 days | ⬜ Not started |
| Phase 8 | Inventory barcode scan | 0.5 days | ⬜ Not started |
