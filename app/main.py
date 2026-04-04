from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import AuthStateMiddleware
from app.api.router import api_router
from app.core.bootstrap import seed_admin
from app.core.config import settings
from app.core.schema_guard import warn_if_scenario_schema_missing
from app.database.session import engine

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://artistic-connection-production-21ce.up.railway.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthStateMiddleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
async def startup_event() -> None:
    await warn_if_scenario_schema_missing(engine)
    await seed_admin()
    logger.info("Startup: seed_admin concluído.")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
