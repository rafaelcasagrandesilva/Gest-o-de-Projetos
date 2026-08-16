from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings
from app.database.base import Base

# Import models so Alembic "sees" them.
import app.models  # noqa: F401  pylint: disable=unused-import


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return settings.database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Uma TRANSAÇÃO POR MIGRATION (e não uma única para toda a subida). Sem isso, um banco novo
    # não consegue chegar ao head: o PostgreSQL recusa usar um valor de enum criado por
    # `ALTER TYPE ... ADD VALUE` na mesma transação em que ele foi criado, e há migrations que
    # criam o valor (0079) e outras, adiante, que o utilizam (0106). Com o commit por revisão,
    # cada uma enxerga o que a anterior criou — e uma falha no meio deixa o banco na última
    # migration bem-sucedida, em vez de desfazer tudo.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable: AsyncEngine = create_async_engine(get_url(), poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

