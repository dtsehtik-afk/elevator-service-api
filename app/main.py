"""Application entry point — FastAPI app factory with middleware and routers."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.routers import elevators, service_calls, technicians, assignments, maintenance, analytics, schedule, webhooks, technician_app, conversations, inspections, management_companies
from app.auth.router import router as auth_router

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    from app.database import Base, engine
    import app.models  # register all models
    Base.metadata.create_all(bind=engine)  # creates any missing tables
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
app.include_router(conversations.router)
app.include_router(inspections.router)
app.include_router(management_companies.router)


@app.get("/health", tags=["Health"])
def health_check():
    """Public health check endpoint — no authentication required."""
    return {"status": "ok", "service": "elevator-service-api"}


# ── Serve React frontend (must be last) ──────────────────────────────────────
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        """Serve React app for all non-API routes."""
        file = _FRONTEND_DIST / full_path
        if file.exists() and file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
