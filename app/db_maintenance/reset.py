from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import asyncpg
from sqlalchemy.engine.url import make_url

from app.core.config import settings

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Colunas obrigatórias (alinhadas aos models atuais)
VEHICLES_REQUIRED = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "plate",
        "model",
        "description",
        "is_active",
        "vehicle_type",
        "monthly_cost",
        "driver_employee_id",
    }
)
PROJECT_LABORS_REQUIRED = frozenset(
    {"id", "created_at", "updated_at", "project_id", "competencia", "employee_id", "allocation_percentage"}
)


def _parse_target_url() -> tuple[str, str, str, int, str]:
    """
    Retorna (user, password, host, port, database) a partir de DATABASE_URL.
    Suporta postgresql+asyncpg.
    """
    raw = settings.database_url.strip()
    url = make_url(raw)
    backend = url.get_dialect().name
    if backend != "postgresql":
        raise RuntimeError(
            f"reset_db só suporta PostgreSQL (dialeto atual: {backend}). "
            f"Ajuste DATABASE_URL."
        )
    db = url.database
    if not db:
        raise RuntimeError("DATABASE_URL sem nome do banco de dados.")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", db):
        raise RuntimeError(f"Nome de banco inválido para reset seguro: {db!r}")
    user = url.username or "postgres"
    password = url.password or ""
    host = url.host or "localhost"
    port = int(url.port or 5432)
    return user, password, host, port, db


def _connect_kwargs(user: str, password: str, host: str, port: int, database: str) -> dict:
    """Evita montar URL manual (senhas com caracteres especiais)."""
    kw: dict = {
        "host": host,
        "port": port,
        "user": user,
        "database": database,
    }
    if password:
        kw["password"] = password
    return kw


async def terminate_connections_and_drop_create(
    user: str, password: str, host: str, port: int, target_db: str
) -> None:
    """Conecta em `postgres`, encerra sessões no banco alvo, DROP + CREATE."""
    logger.warning("Encerrando conexões e recriando o banco %r (irreversível).", target_db)
    conn = await asyncpg.connect(**_connect_kwargs(user, password, host, port, "postgres"))
    try:
        # PostgreSQL 13+: pg_terminate_backend em backends do banco alvo
        rows = await conn.fetch(
            "SELECT pid FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()",
            target_db,
        )
        for r in rows:
            await conn.execute("SELECT pg_terminate_backend($1)", r["pid"])
        # PG 13+: WITH (FORCE); versões antigas caem no DROP simples
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)')
        except asyncpg.PostgresError as e:
            logger.warning("DROP ... WITH (FORCE) não aplicado (%s); tentando DROP sem FORCE.", e)
            await conn.execute(f'DROP DATABASE IF EXISTS "{target_db}"')
        await conn.execute(f'CREATE DATABASE "{target_db}"')
    finally:
        await conn.close()
    logger.info("Banco %r recriado (vazio). Tabela alembic_version será recriada pelo upgrade.", target_db)


def run_alembic_upgrade_head() -> None:
    """Executa `alembic upgrade head` no diretório do projeto (stdout/stderr visíveis)."""
    logger.info("Executando: alembic upgrade head (cwd=%s)", REPO_ROOT)
    env = os.environ.copy()
    # Garante imports `app.*` a partir da raiz do repositório
    py_path = str(REPO_ROOT)
    env["PYTHONPATH"] = py_path + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade head falhou (código {proc.returncode}).")
    logger.info("Migrations aplicadas até HEAD com sucesso.")


async def validate_schema_after_migrations(
    user: str, password: str, host: str, port: int, target_db: str
) -> None:
    """Confere colunas e constraints críticas; falha com erro explícito se faltar algo."""
    logger.info("Validando schema no banco %r…", target_db)
    conn = await asyncpg.connect(**_connect_kwargs(user, password, host, port, target_db))
    try:
        async def columns(table: str) -> set[str]:
            r = await conn.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                """,
                table,
            )
            return {row["column_name"] for row in r}

        async def nullable(table: str, col: str) -> str | None:
            r = await conn.fetchrow(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1 AND column_name = $2
                """,
                table,
                col,
            )
            return r["is_nullable"] if r else None

        vcols = await columns("vehicles")
        missing_v = VEHICLES_REQUIRED - vcols
        if missing_v:
            raise RuntimeError(f"Tabela vehicles incompleta. Faltando colunas: {sorted(missing_v)}")

        lcols = await columns("project_labors")
        missing_l = PROJECT_LABORS_REQUIRED - lcols
        if missing_l:
            raise RuntimeError(f"Tabela project_labors incompleta. Faltando colunas: {sorted(missing_l)}")

        emp_null = await nullable("project_labors", "employee_id")
        if emp_null != "NO":
            raise RuntimeError(
                "project_labors.employee_id deve ser NOT NULL (encontrado: "
                f"{emp_null!r}). Corrija migrations ou models."
            )

        uq = await conn.fetchrow(
            """
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_project_labors_project_employee_competencia'
              AND contype = 'u'
            """
        )
        if not uq:
            raise RuntimeError(
                "Constraint UNIQUE uq_project_labors_project_employee_competencia ausente em project_labors."
            )

        plate_uq = await conn.fetchrow(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'vehicles' AND indexname = 'ix_vehicles_plate'
            """
        )
        if not plate_uq:
            raise RuntimeError("Índice único ix_vehicles_plate (placa) ausente na tabela vehicles.")

        ver = await conn.fetchrow("SELECT version_num FROM alembic_version LIMIT 1")
        if not ver:
            raise RuntimeError("Tabela alembic_version vazia — migrations não registraram revisão.")
        logger.info("alembic_version atual: %s", ver["version_num"])
    finally:
        await conn.close()
    logger.info("Schema validado: vehicles, project_labors e alembic_version OK.")


async def seed_admin_logged() -> None:
    from app.core.bootstrap import seed_admin

    logger.info("Executando seed_admin() (admin@admin.com se não houver admin RBAC)…")
    await seed_admin()
    logger.info("seed_admin() concluído.")


async def run_full_reset(*, skip_confirm: bool) -> None:
    user, password, host, port, target_db = _parse_target_url()
    if not skip_confirm:
        print(
            f"Isso vai APAGAR o banco PostgreSQL {target_db!r} em {host}:{port} e reaplicar todas as migrations.\n"
            "Digite o nome do banco exatamente para confirmar:",
            flush=True,
        )
        line = input().strip()
        if line != target_db:
            print("Confirmação não confere. Abortado.", flush=True)
            raise SystemExit(1)

    await terminate_connections_and_drop_create(user, password, host, port, target_db)
    run_alembic_upgrade_head()
    await validate_schema_after_migrations(user, password, host, port, target_db)
    await seed_admin_logged()
    logger.warning(
        "Após reset limpo, use login admin@admin.com / 123456 (altere em produção)."
    )
