from __future__ import annotations

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware import AuthStateMiddleware, ForwardedProtoMiddleware
from app.api.router import api_router
from app.core.bootstrap import seed_admin
from app.core.config import settings
from app.core.run_migrations import run_alembic_upgrade
from app.core.schema_guard import warn_if_scenario_schema_missing
from app.database.session import engine, get_db

logger = logging.getLogger(__name__)

_is_local = (settings.env or "").strip().lower() in ("local", "development", "dev", "test")
_cors_raw = (settings.cors_origins or "").strip()
_cors_kwargs: dict = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

if _is_local and not _cors_raw:
    # Local: aceita qualquer porta do localhost/127.0.0.1 (Vite pode mudar de porta).
    _cors_kwargs["allow_origin_regex"] = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    _cors_kwargs["allow_origins"] = []
else:
    try:
        _cors_kwargs["allow_origins"] = settings.resolved_cors_origins()
    except ValueError as e:
        raise RuntimeError(str(e)) from e

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    **_cors_kwargs,
)
app.add_middleware(AuthStateMiddleware)
# Por último = executa primeiro: corrige scheme antes de CORS/auth/redirect_slashes.
app.add_middleware(ForwardedProtoMiddleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
async def startup_event() -> None:
    # Cria permissions / user_permissions e demais revisions pendentes (produção Railway).
    run_alembic_upgrade()
    await warn_if_scenario_schema_missing(engine)
    await seed_admin()
    logger.info("Startup: migrations + seed_admin concluídos.")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)) -> dict:
    """Para load balancer / orquestrador: falha se o banco não responder."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
