"""Application entry point — FastAPI app factory with middleware and routers."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.routers import elevators, service_calls, technicians, assignments, maintenance, analytics, schedule, webhooks, technician_app, inspections, management_companies, buildings, contacts, data_import, admin_control
from app.routers import customers, quotes, contracts, invoices, inventory, leads, erp_dashboard
from app.routers import settings as settings_router, conversations
from app.routers import reports as reports_router, custom_fields as custom_fields_router
from app.routers import hr as hr_router
from app.routers import part_requests as part_requests_router
from app.routers import consultants as consultants_router
from app.routers import ai as ai_router
from app.routers import projects as projects_router
from app.routers import admin_console as admin_console_router
from app.routers import search as search_router
from app.auth.router import router as auth_router

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# Resolved once at startup — used by the SPA middleware and static mounts
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    from pathlib import Path
    from app.database import Base, engine
    import app.models  # register all models
    Base.metadata.create_all(bind=engine)  # creates any missing tables
    Path("uploads/elevators").mkdir(parents=True, exist_ok=True)
    Path("uploads/inspections").mkdir(parents=True, exist_ok=True)
    # Incremental migrations — PostgreSQL only (skipped for SQLite in tests)
    from sqlalchemy import text as _text
    with engine.connect() as _conn:
        if engine.dialect.name == "postgresql":
            for _col_sql in [
                # inspection_reports
                "ALTER TABLE inspection_reports ADD COLUMN IF NOT EXISTS file_path VARCHAR(500)",
                "ALTER TABLE inspection_reports ADD COLUMN IF NOT EXISTS report_status VARCHAR(20) NOT NULL DEFAULT 'NA'",
                "ALTER TABLE inspection_reports ADD COLUMN IF NOT EXISTS assigned_technician_id UUID",
                "ALTER TABLE inspection_reports ADD COLUMN IF NOT EXISTS drive_file_id VARCHAR(200)",
                # management_companies — caller_phones may be missing
                "ALTER TABLE management_companies ADD COLUMN IF NOT EXISTS caller_phones TEXT[] DEFAULT '{}'",
                # Fix: if column was created as JSONB by create_all, convert to TEXT[]
                """DO $$ BEGIN
                    IF (SELECT data_type FROM information_schema.columns
                        WHERE table_name='management_companies' AND column_name='caller_phones') = 'jsonb'
                    THEN
                        ALTER TABLE management_companies ADD COLUMN caller_phones_new TEXT[] DEFAULT '{}';
                        UPDATE management_companies SET caller_phones_new = ARRAY(SELECT jsonb_array_elements_text(caller_phones));
                        ALTER TABLE management_companies DROP COLUMN caller_phones;
                        ALTER TABLE management_companies RENAME COLUMN caller_phones_new TO caller_phones;
                    END IF;
                END $$""",
                # elevators — management_company_id added after initial migration
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS management_company_id UUID REFERENCES management_companies(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_elevators_management_company_id ON elevators (management_company_id)",
                # after_hours_pending flag for caller approval flow
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS after_hours_pending BOOLEAN NOT NULL DEFAULT FALSE",
                # resolved_by — name of technician who closed the call
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(150)",
                # system_settings key-value store
                """CREATE TABLE IF NOT EXISTS system_settings (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                # Remove service calls auto-created from inspection escalation (now silent flow)
                "DELETE FROM service_calls WHERE reported_by = 'system | escalation' AND description LIKE '%ליקויי בודק%' AND status IN ('OPEN','ASSIGNED')",
                # system_settings — control plane module flags
                """CREATE TABLE IF NOT EXISTS system_settings (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    key VARCHAR(50) UNIQUE NOT NULL DEFAULT 'default',
                    modules JSONB NOT NULL DEFAULT '{}',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                # ERP: customer_id on elevators + buildings
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_elevators_customer_id ON elevators (customer_id)",
                "ALTER TABLE buildings ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_buildings_customer_id ON buildings (customer_id)",
                # Report Builder: saved_views, custom_fields, custom_field_values
                """CREATE TABLE IF NOT EXISTS saved_views (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES technicians(id) ON DELETE CASCADE,
                    entity_type VARCHAR(50) NOT NULL,
                    name VARCHAR(150) NOT NULL,
                    columns JSONB NOT NULL DEFAULT '[]',
                    filters JSONB NOT NULL DEFAULT '[]',
                    sort_by VARCHAR(100),
                    sort_dir VARCHAR(4) NOT NULL DEFAULT 'desc',
                    is_default BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                "CREATE INDEX IF NOT EXISTS ix_saved_views_user_id ON saved_views (user_id)",
                "CREATE INDEX IF NOT EXISTS ix_saved_views_entity_type ON saved_views (entity_type)",
                """CREATE TABLE IF NOT EXISTS custom_fields (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_type VARCHAR(50) NOT NULL,
                    field_name VARCHAR(100) NOT NULL,
                    field_label VARCHAR(150) NOT NULL,
                    field_type VARCHAR(20) NOT NULL DEFAULT 'TEXT',
                    options JSONB,
                    required BOOLEAN NOT NULL DEFAULT FALSE,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    display_order INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_custom_field_entity_name UNIQUE (entity_type, field_name)
                )""",
                "CREATE INDEX IF NOT EXISTS ix_custom_fields_entity_type ON custom_fields (entity_type)",
                """CREATE TABLE IF NOT EXISTS custom_field_values (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_id UUID NOT NULL,
                    entity_type VARCHAR(50) NOT NULL,
                    field_id UUID NOT NULL REFERENCES custom_fields(id) ON DELETE CASCADE,
                    value TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_cfv_entity_field UNIQUE (entity_id, entity_type, field_id)
                )""",
                "CREATE INDEX IF NOT EXISTS ix_custom_field_values_entity_id ON custom_field_values (entity_id)",
                "CREATE INDEX IF NOT EXISTS ix_custom_field_values_entity_type ON custom_field_values (entity_type)",
                # Elevator extended tech specs
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS motor_type VARCHAR(100)",
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS controller_model VARCHAR(100)",
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS door_type VARCHAR(100)",
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS pit_depth_cm INTEGER",
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS headroom_cm INTEGER",
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS safety_certificate_expiry DATE",
                # SLA deadline on service calls
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS sla_deadline TIMESTAMPTZ",
                # HR module
                """CREATE TABLE IF NOT EXISTS hr_records (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    technician_id UUID NOT NULL UNIQUE REFERENCES technicians(id) ON DELETE CASCADE,
                    employment_start DATE,
                    employment_end DATE,
                    employment_type VARCHAR(20) NOT NULL DEFAULT 'FULL_TIME',
                    salary_type VARCHAR(20) NOT NULL DEFAULT 'MONTHLY',
                    base_salary FLOAT,
                    hourly_rate FLOAT,
                    id_number VARCHAR(20),
                    bank_account VARCHAR(50),
                    emergency_contact VARCHAR(150),
                    emergency_phone VARCHAR(30),
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                "CREATE INDEX IF NOT EXISTS ix_hr_records_technician_id ON hr_records (technician_id)",
                "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS elevator_id UUID REFERENCES elevators(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_contacts_elevator_id ON contacts (elevator_id)",
                # Service call sequential numbering (S + 5 digits)
                "CREATE SEQUENCE IF NOT EXISTS service_calls_call_number_seq",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS call_number BIGINT DEFAULT nextval('service_calls_call_number_seq')",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_service_calls_call_number ON service_calls (call_number)",
                # Backfill any calls that still have NULL call_number (created before migration)
                "UPDATE service_calls SET call_number = nextval('service_calls_call_number_seq') WHERE call_number IS NULL",
                # Maintenance times per year (2/4/6/12)
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS maintenance_times_per_year INTEGER DEFAULT 6",
                # Backfill: set times_per_year=6 where NULL, derive from existing interval_days
                """UPDATE elevators SET maintenance_times_per_year = CASE
                    WHEN maintenance_interval_days IS NOT NULL AND maintenance_interval_days <= 35 THEN 12
                    WHEN maintenance_interval_days IS NOT NULL AND maintenance_interval_days <= 70 THEN 6
                    WHEN maintenance_interval_days IS NOT NULL AND maintenance_interval_days <= 100 THEN 4
                    WHEN maintenance_interval_days IS NOT NULL THEN 2
                    ELSE 6
                END WHERE maintenance_times_per_year IS NULL""",
                # Derive next_service_date for elevators that have last_service_date but no next
                """UPDATE elevators SET next_service_date =
                    (last_service_date + (FLOOR(365.0 / COALESCE(maintenance_times_per_year, 6)) || ' days')::INTERVAL)::DATE
                    WHERE last_service_date IS NOT NULL AND next_service_date IS NULL""",
                # Admin Console: structured event log
                """CREATE TABLE IF NOT EXISTS admin_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    level VARCHAR(20) NOT NULL DEFAULT 'ERROR',
                    source VARCHAR(200),
                    message TEXT NOT NULL,
                    stack_trace TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                "CREATE INDEX IF NOT EXISTS ix_admin_logs_created_at ON admin_logs (created_at DESC)",
                "CREATE INDEX IF NOT EXISTS ix_admin_logs_level ON admin_logs (level)",
                # Projects module
                """CREATE TABLE IF NOT EXISTS projects (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(200) NOT NULL,
                    site VARCHAR(200),
                    status VARCHAR(30) NOT NULL DEFAULT 'PLANNING',
                    start_date DATE,
                    end_date DATE,
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                """CREATE TABLE IF NOT EXISTS project_tasks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name VARCHAR(200) NOT NULL,
                    assignee VARCHAR(100),
                    start_date DATE,
                    end_date DATE,
                    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
                    progress INTEGER NOT NULL DEFAULT 0,
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                "CREATE INDEX IF NOT EXISTS ix_project_tasks_project_id ON project_tasks (project_id)",
                # incoming_call_logs — columns added after initial table creation
                "ALTER TABLE incoming_call_logs ADD COLUMN IF NOT EXISTS call_type VARCHAR(200)",
                "ALTER TABLE incoming_call_logs ADD COLUMN IF NOT EXISTS call_time_raw VARCHAR(50)",
                # assignments — store Green API message ID to enable reply-linking
                "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS whatsapp_message_id VARCHAR(200)",
                # Warehouse / inventory location management
                """CREATE TABLE IF NOT EXISTS warehouses (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(100) NOT NULL,
                    warehouse_type VARCHAR(50) NOT NULL DEFAULT 'MAIN',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    address VARCHAR(255),
                    technician_id UUID REFERENCES technicians(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                "CREATE INDEX IF NOT EXISTS ix_warehouses_technician_id ON warehouses (technician_id)",
                """CREATE TABLE IF NOT EXISTS warehouse_stock (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    part_id UUID NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                    warehouse_id UUID NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_stock_part_warehouse UNIQUE (part_id, warehouse_id)
                )""",
                "CREATE INDEX IF NOT EXISTS ix_warehouse_stock_part_id ON warehouse_stock (part_id)",
                "CREATE INDEX IF NOT EXISTS ix_warehouse_stock_warehouse_id ON warehouse_stock (warehouse_id)",
                """CREATE TABLE IF NOT EXISTS inventory_transactions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    part_id UUID NOT NULL REFERENCES parts(id) ON DELETE RESTRICT,
                    source_warehouse_id UUID REFERENCES warehouses(id) ON DELETE SET NULL,
                    target_warehouse_id UUID REFERENCES warehouses(id) ON DELETE SET NULL,
                    transaction_type VARCHAR(50) NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price NUMERIC(12,2),
                    reference_number VARCHAR(100),
                    notes TEXT,
                    created_by UUID REFERENCES technicians(id) ON DELETE SET NULL,
                    service_call_id UUID REFERENCES service_calls(id) ON DELETE SET NULL,
                    date TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                "CREATE INDEX IF NOT EXISTS ix_inventory_transactions_part_id ON inventory_transactions (part_id)",
                "CREATE INDEX IF NOT EXISTS ix_inventory_transactions_date ON inventory_transactions (date DESC)",
                "CREATE INDEX IF NOT EXISTS ix_inventory_transactions_service_call_id ON inventory_transactions (service_call_id)",
                # Ensure main warehouse exists
                """INSERT INTO warehouses (id, name, warehouse_type, is_active)
                   SELECT gen_random_uuid(), 'מחסן ראשי', 'MAIN', TRUE
                   WHERE NOT EXISTS (SELECT 1 FROM warehouses WHERE warehouse_type = 'MAIN')""",
                # Auto-create VEHICLE warehouse for each technician that lacks one
                """INSERT INTO warehouses (id, name, warehouse_type, is_active, technician_id)
                   SELECT gen_random_uuid(), 'רכב - ' || t.name, 'VEHICLE', TRUE, t.id
                   FROM technicians t
                   WHERE NOT EXISTS (
                       SELECT 1 FROM warehouses w WHERE w.technician_id = t.id AND w.warehouse_type = 'VEHICLE'
                   ) AND t.id IS NOT NULL""",
                # Backfill warehouse_stock for main warehouse from parts.quantity
                """INSERT INTO warehouse_stock (id, part_id, warehouse_id, quantity)
                   SELECT gen_random_uuid(), p.id, w.id, p.quantity
                   FROM parts p
                   CROSS JOIN warehouses w
                   WHERE w.warehouse_type = 'MAIN'
                     AND p.quantity > 0
                     AND NOT EXISTS (
                         SELECT 1 FROM warehouse_stock ws
                         WHERE ws.part_id = p.id AND ws.warehouse_id = w.id
                     )""",
                # ── Part requests (approval workflow) ───────────────────────
                """CREATE TABLE IF NOT EXISTS part_requests (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    service_call_id UUID NOT NULL REFERENCES service_calls(id) ON DELETE CASCADE,
                    part_id UUID NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                    source_warehouse_id UUID REFERENCES warehouses(id) ON DELETE SET NULL,
                    requested_by UUID REFERENCES technicians(id) ON DELETE SET NULL,
                    approved_by UUID REFERENCES technicians(id) ON DELETE SET NULL,
                    return_warehouse_id UUID REFERENCES warehouses(id) ON DELETE SET NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    notes TEXT,
                    status VARCHAR(30) NOT NULL DEFAULT 'PENDING_APPROVAL',
                    approval_type VARCHAR(40) NOT NULL DEFAULT 'MANAGER_OVERRIDE',
                    service_type_snapshot VARCHAR(20),
                    approval_notes TEXT,
                    rejection_reason TEXT,
                    approved_at TIMESTAMPTZ,
                    faulty_part_returned BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                "CREATE INDEX IF NOT EXISTS ix_part_requests_service_call_id ON part_requests (service_call_id)",
                "CREATE INDEX IF NOT EXISTS ix_part_requests_status ON part_requests (status)",
                # ── ERP Extended Fields ──────────────────────────────────────
                # parts
                "ALTER TABLE parts ADD COLUMN IF NOT EXISTS is_inventory_managed BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE parts ADD COLUMN IF NOT EXISTS is_serial_managed BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE parts ADD COLUMN IF NOT EXISTS image_url TEXT",
                "ALTER TABLE parts ADD COLUMN IF NOT EXISTS foreign_description VARCHAR(500)",
                "ALTER TABLE parts ADD COLUMN IF NOT EXISTS product_family VARCHAR(100)",
                "ALTER TABLE parts ADD COLUMN IF NOT EXISTS erp_metadata JSONB",
                # customers
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS creation_date DATE",
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS fax VARCHAR(30)",
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS industry_type VARCHAR(100)",
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS territory VARCHAR(100)",
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS delivery_route VARCHAR(100)",
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS website VARCHAR(255)",
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS sales_target NUMERIC(14,2)",
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS employee_count INTEGER",
                "ALTER TABLE customers ADD COLUMN IF NOT EXISTS erp_metadata JSONB",
                # contracts
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS customer_type_ref VARCHAR(100)",
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contact_person VARCHAR(100)",
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS paid_until DATE",
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS renewal_years INTEGER",
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE SET NULL",
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS discount_percent NUMERIC(5,2)",
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS vat_percent NUMERIC(5,2) DEFAULT 18",
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS sales_rep_id UUID REFERENCES technicians(id) ON DELETE SET NULL",
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS erp_metadata JSONB",
                "CREATE INDEX IF NOT EXISTS ix_contracts_project_id ON contracts (project_id)",
                "CREATE INDEX IF NOT EXISTS ix_contracts_sales_rep_id ON contracts (sales_rep_id)",
                # service_calls
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS parent_call_id UUID REFERENCES service_calls(id) ON DELETE SET NULL",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS warranty_end_date DATE",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS customer_rma VARCHAR(50)",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS caller_name VARCHAR(150)",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS contact_phone_sms VARCHAR(30)",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS contact_email VARCHAR(100)",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS downtime_minutes INTEGER",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS total_price NUMERIC(12,2)",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS discount NUMERIC(12,2)",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS is_elevator_stopped BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS station_count INTEGER",
                "ALTER TABLE service_calls ADD COLUMN IF NOT EXISTS erp_metadata JSONB",
                "CREATE INDEX IF NOT EXISTS ix_service_calls_parent_call_id ON service_calls (parent_call_id)",
                # ── Consultants ──────────────────────────────────────────────
                """CREATE TABLE IF NOT EXISTS consultants (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(255) NOT NULL UNIQUE,
                    phone VARCHAR(30),
                    email VARCHAR(150),
                    address VARCHAR(255),
                    notes TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    consultant_contacts JSONB NOT NULL DEFAULT '[]',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""",
                "CREATE INDEX IF NOT EXISTS ix_consultants_name ON consultants (name)",
                # ── Elevator new fields ───────────────────────────────────────
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS responsible_technician_id UUID REFERENCES technicians(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_elevators_responsible_technician_id ON elevators (responsible_technician_id)",
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS consultant_id UUID REFERENCES consultants(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_elevators_consultant_id ON elevators (consultant_id)",
                "ALTER TABLE elevators ADD COLUMN IF NOT EXISTS lead_source VARCHAR(100)",
            ]:
                _conn.execute(_text(_col_sql))
        _conn.commit()
    # Backfill: ensure every elevator has a customer_id
    try:
        from app.database import SessionLocal
        from app.services.elevator_service import sync_all_elevator_customers
        import logging as _logging
        _db = SessionLocal()
        try:
            _synced = sync_all_elevator_customers(_db)
            if _synced:
                _logging.getLogger(__name__).info(f"Synced {_synced} elevators → customers")
        finally:
            _db.close()
    except Exception:
        pass
    # Attach DB log handler so Python WARNING+ logs are persisted to admin_logs
    try:
        from app.services.admin_log_service import DBLogHandler
        _db_handler = DBLogHandler()
        _db_handler.setLevel(logging.WARNING)
        logging.getLogger().addHandler(_db_handler)
    except Exception:
        pass
    from app.services.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Elevator Service API",
    description="מערכת ניהול שירות מעליות — 500 מעליות, עד 10 טכנאים",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SPA fallback middleware ───────────────────────────────────────────────────
# React uses history routing — on page refresh the browser sends a GET for the
# current path (e.g. /calls). Without this middleware, FastAPI would match its
# own /calls API route and return JSON, giving the user a blank/error screen.
# We detect browser navigations by their Accept header (starts with text/html)
# and serve index.html instead, letting the React Router handle the path.
_API_ONLY_PREFIXES = (
    "/auth", "/docs", "/redoc", "/openapi", "/health",
    "/uploads", "/assets", "/webhooks", "/analytics",
    "/schedule", "/buildings", "/contacts", "/app/", "/settings", "/admin",
    "/customers", "/quotes", "/contracts", "/invoices", "/inventory", "/leads", "/erp",
    "/reports", "/custom-fields", "/roles", "/hr", "/projects", "/search", "/consultants",
    "/part-requests",
)


@app.middleware("http")
async def spa_browser_fallback(request: Request, call_next):
    accept = request.headers.get("accept", "")
    path   = request.url.path
    if (
        request.method == "GET"
        and accept.startswith("text/html")
        and not any(path.startswith(p) for p in _API_ONLY_PREFIXES)
        and _FRONTEND_DIST.exists()
    ):
        file = _FRONTEND_DIST / path.lstrip("/")
        if file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
    return await call_next(request)


# Routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(elevators.router, prefix="/elevators", tags=["Elevators"])
app.include_router(service_calls.router, prefix="/calls", tags=["Service Calls"])
app.include_router(technicians.router, prefix="/technicians", tags=["Technicians"])
app.include_router(assignments.router, prefix="/calls", tags=["Assignments"])
app.include_router(maintenance.router, prefix="/maintenance", tags=["Maintenance"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(schedule.router, prefix="/schedule", tags=["Schedule"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
app.include_router(technician_app.router, prefix="/app", tags=["Technician App"])
app.include_router(inspections.router)
app.include_router(management_companies.router)
app.include_router(buildings.router)
app.include_router(contacts.router)
app.include_router(data_import.router)
app.include_router(admin_control.router)
app.include_router(customers.router)
app.include_router(quotes.router)
app.include_router(contracts.router)
app.include_router(invoices.router)
app.include_router(inventory.router)
app.include_router(leads.router)
app.include_router(erp_dashboard.router)
app.include_router(settings_router.router)
app.include_router(conversations.router)
app.include_router(reports_router.router)
app.include_router(custom_fields_router.router)
app.include_router(hr_router.router)
app.include_router(ai_router.router)
app.include_router(projects_router.router)
app.include_router(admin_console_router.router)
app.include_router(search_router.router)
app.include_router(consultants_router.router)
app.include_router(part_requests_router.router, prefix="/part-requests", tags=["Part Requests"])


@app.get("/health", tags=["Health"])
def health_check():
    """Public health check endpoint — no authentication required."""
    return {"status": "ok", "service": "elevator-service-api"}


# ── Serve React frontend (must be last) ──────────────────────────────────────
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        """Serve React app for all non-API routes."""
        file = _FRONTEND_DIST / full_path
        if file.exists() and file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
