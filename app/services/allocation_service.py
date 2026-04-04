from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.costs import CorporateCost, CostAllocation
from app.core.scenario import Scenario, scenario_pg_rhs
from app.models.financial import Revenue
from app.models.project import Project


class AllocationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def calcular_rateio_de_custos(
        self, *, corporate_cost_id: UUID, competencia: date, strategy: str = "by_revenue"
    ) -> list[CostAllocation]:
        corp = await self.session.get(CorporateCost, corporate_cost_id)
        if not corp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custo corporativo não encontrado.")
        if corp.competencia != competencia:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Competência divergente do custo.")

        projects = list((await self.session.execute(select(Project))).scalars().all())
        if not projects:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum projeto encontrado para rateio.")

        weights: dict[UUID, float] = {}
        if strategy == "by_revenue":
            stmt = (
                select(Revenue.project_id, func.coalesce(func.sum(Revenue.amount), 0))
                .where(
                    Revenue.competencia == competencia,
                    Revenue.scenario == scenario_pg_rhs(Scenario.REALIZADO),
                )
                .group_by(Revenue.project_id)
            )
            rows = (await self.session.execute(stmt)).all()
            weights = {pid: float(total) for pid, total in rows}
            total_weight = sum(weights.get(p.id, 0.0) for p in projects)
            if total_weight <= 0:
                strategy = "equal"

        if strategy == "equal":
            total_weight = float(len(projects))
            weights = {p.id: 1.0 for p in projects}

        amount_total = float(corp.amount_real)
        allocations: list[CostAllocation] = []
        for p in projects:
            w = weights.get(p.id, 0.0)
            allocated = 0.0 if total_weight == 0 else (amount_total * (w / total_weight))
            allocations.append(
                CostAllocation(
                    corporate_cost_id=corp.id,
                    project_id=p.id,
                    competencia=competencia,
                    allocated_amount_real=allocated,
                    allocated_amount_calculated=0,
                )
            )

        for a in allocations:
            self.session.add(a)
        await self.session.commit()
        for a in allocations:
            await self.session.refresh(a)
        return allocations

