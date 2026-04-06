from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import AuthStateMiddleware, ForwardedProtoMiddleware
from app.api.router import api_router
from app.core.bootstrap import seed_admin
from app.core.config import settings
from app.core.run_migrations import run_alembic_upgrade
from app.core.schema_guard import warn_if_scenario_schema_missing
from app.database.session import engine

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
