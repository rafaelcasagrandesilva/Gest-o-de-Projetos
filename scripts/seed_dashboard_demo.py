"""Seed de DEMONSTRAÇÃO para o dashboard operacional (dados fictícios).

Cria 4 projetos com receita e custo operacional (PREVISTO e REALIZADO) na
competência 2026-06, com o custo realizado acima do previsto para evidenciar
o card "Custo total" em vermelho. Idempotente: limpa os projetos demo antes.

Uso: python -m scripts.seed_dashboard_demo
"""

from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import delete, select

from app.core.scenario import Scenario
from app.database.session import AsyncSessionLocal
from app.models.financial import Revenue
from app.models.project import Project
from app.models.project_operational import ProjectOperationalFixed

COMPETENCIA = date(2026, 6, 1)

# nome, receita_prev, receita_real, custo_op_prev, custo_op_real
DEMO = [
    ("Fiscalização AT", 500_000, 520_000, 300_000, 350_000),
    ("Treinamentos", 300_000, 310_000, 180_000, 175_000),
    ("Projetos Executivos", 200_000, 210_000, 120_000, 130_000),
    ("Laudos", 100_000, 90_000, 60_000, 65_000),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        names = [d[0] for d in DEMO]
        existing = (
            (await db.execute(select(Project).where(Project.name.in_(names)))).scalars().all()
        )
        for proj in existing:
            await db.execute(delete(Revenue).where(Revenue.project_id == proj.id))
            await db.execute(
                delete(ProjectOperationalFixed).where(
                    ProjectOperationalFixed.project_id == proj.id
                )
            )
            await db.delete(proj)
        await db.flush()

        for name, rev_prev, rev_real, cost_prev, cost_real in DEMO:
            proj = Project(name=name, is_active=True)
            db.add(proj)
            await db.flush()
            db.add_all(
                [
                    Revenue(
                        project_id=proj.id,
                        competencia=COMPETENCIA,
                        scenario=Scenario.PREVISTO,
                        amount=rev_prev,
                        description="Receita demo",
                        status="recebido",
                    ),
                    Revenue(
                        project_id=proj.id,
                        competencia=COMPETENCIA,
                        scenario=Scenario.REALIZADO,
                        amount=rev_real,
                        description="Receita demo",
                        status="recebido",
                    ),
                    ProjectOperationalFixed(
                        project_id=proj.id,
                        competencia=COMPETENCIA,
                        scenario=Scenario.PREVISTO,
                        name="Custo operacional demo",
                        value=cost_prev,
                    ),
                    ProjectOperationalFixed(
                        project_id=proj.id,
                        competencia=COMPETENCIA,
                        scenario=Scenario.REALIZADO,
                        name="Custo operacional demo",
                        value=cost_real,
                    ),
                ]
            )
        await db.commit()
    print(f"Seed concluído: {len(DEMO)} projetos demo em {COMPETENCIA:%m/%Y}.")


if __name__ == "__main__":
    asyncio.run(main())
