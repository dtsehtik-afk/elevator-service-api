"""Control plane — FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
import app.models  # register models


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Start background monitor
    from app.services.monitor import start_monitor, stop_monitor
    start_monitor()
    yield
    stop_monitor()


settings = get_settings()

app = FastAPI(
    title="Lift-Agent Control Plane",
    description="SaaS control plane — tenant registry, deploy, billing, monitoring",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from app.routers.auth_router import router as auth_router
from app.routers.tenants import router as tenants_router
from app.routers.modules import router as modules_router
from app.routers.deploy import router as deploy_router
from app.routers.billing import router as billing_router
from app.routers.monitoring import router as monitoring_router, overview_router

app.include_router(auth_router)
app.include_router(tenants_router)
app.include_router(modules_router)
app.include_router(deploy_router)
app.include_router(billing_router)
app.include_router(monitoring_router)
app.include_router(overview_router)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "lift-agent-control-plane"}
