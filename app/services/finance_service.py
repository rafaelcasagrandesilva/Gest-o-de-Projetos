from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.financial_service import FinancialService
from app.services.payable_service import PayableService
from app.services.payable_snapshot_service import PayableSnapshotService
from app.services.receivable_service import ReceivableService
from app.utils.date_utils import normalize_competencia


@dataclass(frozen=True)
class ConsolidatedCostRow:
    cost_center: str
    category: str
    total: float


class FinanceService:
    """
    Serviço financeiro (consolidação) – não duplica dados.

    - Colaboradores/veículos/custos fixos: usa `FinancialService.calcular_operacional_estruturado` (já existente).
    - Payables (avulsos): soma por conta contábil.
    - Receita: usa NFs simplificadas (receivable_invoices) via `ReceivableService`.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.financial = FinancialService(db)
        self.payables = PayableService(db)
        self.payable_snapshots = PayableSnapshotService(db)
        self.receivables = ReceivableService(db)

    async def get_or_create_payables_snapshot(
        self,
        *,
        month: date,
        accessible_project_ids: set[UUID] | None,
        sees_all_projects: bool,
        force_regenerate: bool = False,
    ):
        comp = normalize_competencia(month)
        rows = await self.payable_snapshots.get_or_create_for_month(
            payment_month=comp,
            accessible_project_ids=accessible_project_ids,
            sees_all_projects=sees_all_projects,
            force_regenerate=force_regenerate,
        )
        return rows

    async def get_consolidated_costs(
        self,
        *,
        competence: date,
        project_id: UUID | None = None,
    ) -> list[dict]:
        comp = normalize_competencia(competence)

        # 1) Custos automáticos do operacional (sem duplicar dados)
        parts = await self.financial.calcular_operacional_estruturado(
            project_id=project_id, competencia=comp
        )

        # Mapeamento mínimo para o plano de contas inicial (sem DE/PARA manual).
        # Conforme o plano evoluir, esse mapa pode ser refinado sem mudar dados persistidos.
        auto_map: list[tuple[str, float]] = [
            ("SALARIO_BASE", float(parts.get("labor_cost", 0.0) or 0.0)),
            ("COMBUSTIVEL", float(parts.get("vehicle_cost", 0.0) or 0.0)),
            ("SOFTWARES", float(parts.get("system_cost", 0.0) or 0.0)),
            ("BENEFICIOS", float(parts.get("fixed_operational_cost", 0.0) or 0.0)),
        ]

        cost_center = "GLOBAL" if project_id is None else "PROJETO"
        acc: dict[tuple[str, str], float] = {}
        for code, total in auto_map:
            if total <= 0:
                continue
            acc[(cost_center, code)] = acc.get((cost_center, code), 0.0) + float(total)

        # 2) Payables (avulsos): soma por conta
        pays = await self.payables.list_payables(
            competence=comp,
            status=None,
            chart_account_id=None,
            project_id=project_id,
            supplier=None,
        )
        for p in pays:
            cc = (p.cost_center or "").strip() or cost_center
            code = p.chart_account.code if p.chart_account else "AVULSOS"
            acc[(cc, code)] = acc.get((cc, code), 0.0) + float(p.amount or 0.0)

        out = [
            ConsolidatedCostRow(cost_center=k[0], category=k[1], total=round(v, 2)) for k, v in acc.items()
        ]
        out.sort(key=lambda r: (r.cost_center, r.category))
        return [r.__dict__ for r in out]

