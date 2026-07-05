"""Serviço reutilizável de inicialização de competências de custos do projeto.

Copia categorias de custo (mão de obra, veículos, sistemas, custos diversos) de uma
competência/cenário de ORIGEM para uma de DESTINO, substituindo por completo os
dados das categorias selecionadas no destino — numa única transação.

Não altera cálculos financeiros: apenas replica os campos já armazenados e reconcilia
os payables usando exatamente os mesmos métodos existentes do PayableSnapshotService
(mesmos efeitos colaterais que criar/editar/excluir cada item individualmente).

Arquitetura preparada para futuras evoluções (sem implementá-las agora):
- copiar de qualquer competência (source.competencia livre);
- copiar entre cenários (source.scenario != target.scenario);
- copiar entre projetos (source.project_id != target.project_id);
- copiar apenas uma categoria ou qualquer combinação.
O núcleo é `copy_categories(source, target, categories)`; o endpoint atual usa o
atalho `initialize_from_origin` com as 3 origens padrão.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scenario import Scenario
from app.models.project_operational import (
    ProjectLabor,
    ProjectOperationalFixed,
    ProjectSystemCost,
    ProjectVehicle,
)
from app.repositories.project_operational import (
    ProjectLaborRepository,
    ProjectOperationalFixedRepository,
    ProjectSystemCostRepository,
    ProjectVehicleRepository,
)
from app.services.payable_snapshot_service import PayableSnapshotService
from app.utils.date_utils import normalize_competencia, previous_competencia

logger = logging.getLogger(__name__)

# Limite alto para "listar tudo" da competência (cópia completa).
_COPY_LIMIT = 100_000


class CostCategory(str, enum.Enum):
    """Categorias de custo do projeto que podem ser inicializadas."""

    LABOR = "labor"  # Mão de obra
    VEHICLES = "vehicles"  # Veículos
    SYSTEMS = "systems"  # Sistemas
    MISC = "misc"  # Custos diversos (fixos operacionais)


# Ordem lógica de exibição + rótulo plural para o resumo/toast.
_CATEGORY_ORDER: list[CostCategory] = [
    CostCategory.LABOR,
    CostCategory.VEHICLES,
    CostCategory.SYSTEMS,
    CostCategory.MISC,
]
CATEGORY_LABELS: dict[CostCategory, str] = {
    CostCategory.LABOR: "colaboradores",
    CostCategory.VEHICLES: "veículos",
    CostCategory.SYSTEMS: "sistemas",
    CostCategory.MISC: "custos diversos",
}


class InitializationOrigin(str, enum.Enum):
    """Origem dos dados escolhida no modal (define fonte e cenário de destino)."""

    PREVIOUS_REALIZADO = "previous_realizado"  # Realizado da competência anterior → Realizado
    CURRENT_PREVISTO = "current_previsto"  # Previsto da competência atual → Realizado
    PREVIOUS_PREVISTO = "previous_previsto"  # Previsto da competência anterior → Previsto

    @property
    def target_scenario(self) -> Scenario:
        return Scenario.PREVISTO if self is InitializationOrigin.PREVIOUS_PREVISTO else Scenario.REALIZADO


@dataclass(frozen=True)
class CompetenciaRef:
    """Referência a um conjunto de dados: projeto + competência + cenário."""

    project_id: UUID
    competencia: date
    scenario: Scenario


@dataclass(frozen=True)
class CategoryCopyOutcome:
    category: CostCategory
    copied: int

    @property
    def label(self) -> str:
        return CATEGORY_LABELS[self.category]


@dataclass(frozen=True)
class InitializationOutcome:
    source: CompetenciaRef
    target: CompetenciaRef
    results: list[CategoryCopyOutcome]


class CompetenciaInitializationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.labors = ProjectLaborRepository(session)
        self.vehicles = ProjectVehicleRepository(session)
        self.systems = ProjectSystemCostRepository(session)
        self.fixed = ProjectOperationalFixedRepository(session)
        self.payables = PayableSnapshotService(session)

    # ---- API de alto nível (endpoint atual) --------------------------------

    async def initialize_from_origin(
        self,
        *,
        project_id: UUID,
        competencia: date,
        origin: InitializationOrigin,
        categories: list[CostCategory] | set[CostCategory],
    ) -> InitializationOutcome:
        """Inicializa a competência de destino a partir de uma das 3 origens padrão."""
        target_comp = normalize_competencia(competencia)
        source, target = self._resolve_refs(project_id, target_comp, origin)
        return await self.copy_categories(source=source, target=target, categories=categories)

    @staticmethod
    def _resolve_refs(
        project_id: UUID, target_comp: date, origin: InitializationOrigin
    ) -> tuple[CompetenciaRef, CompetenciaRef]:
        prev = previous_competencia(target_comp)
        if origin is InitializationOrigin.PREVIOUS_REALIZADO:
            src = CompetenciaRef(project_id, prev, Scenario.REALIZADO)
        elif origin is InitializationOrigin.CURRENT_PREVISTO:
            src = CompetenciaRef(project_id, target_comp, Scenario.PREVISTO)
        else:  # PREVIOUS_PREVISTO
            src = CompetenciaRef(project_id, prev, Scenario.PREVISTO)
        tgt = CompetenciaRef(project_id, target_comp, origin.target_scenario)
        return src, tgt

    # ---- Núcleo reutilizável -----------------------------------------------

    async def copy_categories(
        self,
        *,
        source: CompetenciaRef,
        target: CompetenciaRef,
        categories: list[CostCategory] | set[CostCategory],
    ) -> InitializationOutcome:
        """Copia (substituindo) as categorias selecionadas de `source` para `target`.

        Tudo numa única operação/transação: só faz commit ao final; se qualquer
        categoria falhar, nada é persistido.
        """
        selected = {CostCategory(c) for c in categories}
        cats = [c for c in _CATEGORY_ORDER if c in selected]
        results: list[CategoryCopyOutcome] = []
        try:
            for cat in cats:
                copied = await self._replace_category(cat, source, target)
                results.append(CategoryCopyOutcome(category=cat, copied=copied))
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            logger.warning(
                "Inicializar competência: falha de integridade source=%s target=%s: %s",
                source,
                target,
                e,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Não foi possível inicializar (conflito de dados). Atualize a tela e tente de novo.",
            ) from e
        return InitializationOutcome(source=source, target=target, results=results)

    async def _replace_category(
        self, category: CostCategory, source: CompetenciaRef, target: CompetenciaRef
    ) -> int:
        if category is CostCategory.LABOR:
            return await self._replace_labor(source, target)
        if category is CostCategory.VEHICLES:
            return await self._replace_vehicles(source, target)
        if category is CostCategory.SYSTEMS:
            return await self._replace_systems(source, target)
        return await self._replace_misc(source, target)

    # ---- Mão de obra (vínculo + snapshot de custos) ------------------------

    async def _replace_labor(self, source: CompetenciaRef, target: CompetenciaRef) -> int:
        tgt_rows = await self.labors.list_by_project(
            project_id=target.project_id, competencia=target.competencia, scenario=target.scenario, limit=_COPY_LIMIT
        )
        src_rows = await self.labors.list_by_project(
            project_id=source.project_id, competencia=source.competencia, scenario=source.scenario, limit=_COPY_LIMIT
        )
        affected_employees: set[UUID] = {r.employee_id for r in tgt_rows}
        for r in tgt_rows:
            await self.labors.delete(r)
        await self.session.flush()

        copied = 0
        added: set[UUID] = set()
        for pr in src_rows:
            if pr.employee_id in added:
                continue
            # Preserva a regra existente: soma de alocação do colaborador ≤ 100% no mês.
            used = await self.labors.sum_allocation_percentage_for_employee_competencia(
                employee_id=pr.employee_id, competencia=target.competencia, scenario=target.scenario
            )
            pct = float(pr.allocation_percentage)
            if used + pct > 100.0001:
                logger.warning(
                    "Inicializar competência: cópia de mão de obra omitida (>100%%) employee=%s project=%s comp=%s",
                    pr.employee_id,
                    target.project_id,
                    target.competencia,
                )
                continue
            self.session.add(
                ProjectLabor(
                    project_id=target.project_id,
                    competencia=target.competencia,
                    scenario=target.scenario,
                    employee_id=pr.employee_id,
                    allocation_percentage=pct,
                    cost_salary_base=pr.cost_salary_base,
                    cost_additional_costs=pr.cost_additional_costs,
                    cost_extra_hours_50=pr.cost_extra_hours_50,
                    cost_extra_hours_70=pr.cost_extra_hours_70,
                    cost_extra_hours_100=pr.cost_extra_hours_100,
                    cost_pj_hours_per_month=pr.cost_pj_hours_per_month,
                    cost_pj_additional_cost=pr.cost_pj_additional_cost,
                    cost_total_override=pr.cost_total_override,
                )
            )
            added.add(pr.employee_id)
            copied += 1
        await self.session.flush()

        # Reconcilia payables de colaborador (só REALIZADO) para removidos + adicionados.
        if target.scenario is Scenario.REALIZADO:
            for employee_id in affected_employees | added:
                await self.payables.sync_collaborator_payables_for_labor(
                    project_id=target.project_id,
                    employee_id=employee_id,
                    labor_competencia=target.competencia,
                    scenario=Scenario.REALIZADO,
                )
        return copied

    # ---- Veículos (alocação de frota; sem sync de payable, como no CRUD) ---

    async def _replace_vehicles(self, source: CompetenciaRef, target: CompetenciaRef) -> int:
        tgt_rows = await self.vehicles.list_by_project(
            project_id=target.project_id, competencia=target.competencia, scenario=target.scenario, limit=_COPY_LIMIT
        )
        src_rows = await self.vehicles.list_by_project(
            project_id=source.project_id, competencia=source.competencia, scenario=source.scenario, limit=_COPY_LIMIT
        )
        for r in tgt_rows:
            await self.vehicles.delete(r)
        await self.session.flush()
        copied = 0
        for sv in src_rows:
            self.session.add(
                ProjectVehicle(
                    project_id=target.project_id,
                    competencia=target.competencia,
                    scenario=target.scenario,
                    vehicle_id=sv.vehicle_id,
                    fuel_type=sv.fuel_type,
                    km_per_month=sv.km_per_month,
                    fuel_cost_realized=sv.fuel_cost_realized,
                    monthly_cost=sv.monthly_cost,
                )
            )
            copied += 1
        await self.session.flush()
        return copied

    # ---- Sistemas / Custos diversos (valor nomeado + sync de payable) ------

    async def _replace_systems(self, source: CompetenciaRef, target: CompetenciaRef) -> int:
        tgt_rows = await self.systems.list_by_project(
            project_id=target.project_id, competencia=target.competencia, scenario=target.scenario, limit=_COPY_LIMIT
        )
        src_rows = await self.systems.list_by_project(
            project_id=source.project_id, competencia=source.competencia, scenario=source.scenario, limit=_COPY_LIMIT
        )
        affected: set[UUID] = {r.id for r in tgt_rows}
        for r in tgt_rows:
            await self.systems.delete(r)
        await self.session.flush()
        copied = 0
        new_rows: list[ProjectSystemCost] = []
        for s in src_rows:
            row = ProjectSystemCost(
                project_id=target.project_id,
                competencia=target.competencia,
                scenario=target.scenario,
                name=s.name,
                value=s.value,
            )
            self.session.add(row)
            new_rows.append(row)
            copied += 1
        await self.session.flush()
        affected |= {r.id for r in new_rows}
        if target.scenario is Scenario.REALIZADO:
            for system_id in affected:
                await self.payables.sync_project_system_payables(
                    project_id=target.project_id,
                    system_id=system_id,
                    labor_competencia=target.competencia,
                    scenario=Scenario.REALIZADO,
                )
        return copied

    async def _replace_misc(self, source: CompetenciaRef, target: CompetenciaRef) -> int:
        tgt_rows = await self.fixed.list_by_project(
            project_id=target.project_id, competencia=target.competencia, scenario=target.scenario, limit=_COPY_LIMIT
        )
        src_rows = await self.fixed.list_by_project(
            project_id=source.project_id, competencia=source.competencia, scenario=source.scenario, limit=_COPY_LIMIT
        )
        affected: set[UUID] = {r.id for r in tgt_rows}
        for r in tgt_rows:
            await self.fixed.delete(r)
        await self.session.flush()
        copied = 0
        new_rows: list[ProjectOperationalFixed] = []
        for c in src_rows:
            row = ProjectOperationalFixed(
                project_id=target.project_id,
                competencia=target.competencia,
                scenario=target.scenario,
                name=c.name,
                value=c.value,
            )
            self.session.add(row)
            new_rows.append(row)
            copied += 1
        await self.session.flush()
        affected |= {r.id for r in new_rows}
        if target.scenario is Scenario.REALIZADO:
            for cost_id in affected:
                await self.payables.sync_project_misc_cost_payables(
                    project_id=target.project_id,
                    cost_id=cost_id,
                    labor_competencia=target.competencia,
                    scenario=Scenario.REALIZADO,
                )
        return copied
