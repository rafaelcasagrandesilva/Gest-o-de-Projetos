from __future__ import annotations

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware import AuthStateMiddleware, ForwardedProtoMiddleware, MemoryReclaimMiddleware
from app.api.router import api_router
from app.core.bootstrap import seed_admin
from app.core.config import settings
from app.core.run_migrations import run_alembic_upgrade
from app.core.schema_guard import warn_if_scenario_schema_missing
from app.database.session import engine, get_db
from app.utils.memory import current_rss_bytes, memory_trim_available
from app.utils.storage import log_storage_dirs, salvage_legacy_uploads

logger = logging.getLogger(__name__)

_is_local = (settings.env or "").strip().lower() in ("local", "development", "dev", "test")
_cors_raw = (settings.cors_origins or "").strip()
_cors_kwargs: dict = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    # Expõe o nome do arquivo dos downloads (relatórios) para o JS ler o nome amigável.
    "expose_headers": ["Content-Disposition"],
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
# Devolve ao SO a memória de uma requisição que cresceu muito (exportação, importação):
# reservada e ociosa ela é cobrada por minuto do mesmo jeito. Só age acima do limiar.
app.add_middleware(MemoryReclaimMiddleware, min_growth_mb=settings.memory_trim_min_growth_mb)
# Por último = executa primeiro: corrige scheme antes de CORS/auth/redirect_slashes.
app.add_middleware(ForwardedProtoMiddleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
async def startup_event() -> None:
    # Cria permissions / user_permissions e demais revisions pendentes (produção Railway).
    run_alembic_upgrade()
    await warn_if_scenario_schema_missing(engine)
    await seed_admin()
    log_storage_dirs()
    salvage_legacy_uploads()
    # Deixa registrado no log se a devolução de memória está ativa neste ambiente — é como
    # se confere, sem adivinhação, que o mecanismo existe onde o custo é cobrado.
    rss = current_rss_bytes()
    logger.info(
        "Startup: migrations + seed_admin concluídos. Devolução de memória ao SO: %s (limiar %d MB)%s",
        "ativa" if memory_trim_available() else "indisponível neste sistema",
        settings.memory_trim_min_growth_mb,
        f", memória residente inicial {rss / 1024 / 1024:.0f} MB" if rss else "",
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)) -> dict:
    """Para load balancer / orquestrador: falha se o banco não responder."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
