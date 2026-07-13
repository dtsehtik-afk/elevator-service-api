from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import engine, Base
from app.models import AdminUser, Tenant, TenantModule  # noqa: register models
from app.auth.router import router as auth_router
from app.routers.tenants import router as tenants_router
from app.routers.stats import router as stats_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Incremental migrations for existing SQLite/PostgreSQL databases
    from sqlalchemy import text as _text
    with engine.connect() as conn:
        for _sql in [
            "ALTER TABLE tenants ADD COLUMN industry VARCHAR(50)",
            "ALTER TABLE admin_users ADD COLUMN totp_secret VARCHAR(64)",
            "ALTER TABLE admin_users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE",
            """CREATE TABLE IF NOT EXISTS admin_login_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT NOT NULL,
                ip_address VARCHAR(50) NOT NULL,
                user_agent VARCHAR(500),
                success INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
        ]:
            try:
                conn.execute(_text(_sql))
                conn.commit()
            except Exception:
                pass
    yield


app = FastAPI(title="Lift Agent Admin", version="1.0.0", lifespan=lifespan)

_settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(tenants_router)
app.include_router(stats_router)


@app.get("/health")
def health():
    return {"ok": True}
