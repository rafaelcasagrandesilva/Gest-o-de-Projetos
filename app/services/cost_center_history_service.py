"""Centro de Custo temporal — resolução por competência (fonte da verdade = histórico).

Um resolvedor genérico reutilizado por colaboradores e veículos (evita regra duplicada).
As regras de negócio resolvem o centro POR COMPETÊNCIA; os campos `*.cost_center` são só
cache do centro vigente. Nunca se edita uma linha FECHADA de histórico — sempre fecha a
linha aberta anterior e abre uma nova.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_center_history import EmployeeCostCenterHistory, VehicleCostCenterHistory
from app.models.employee import Employee
from app.models.fleet import Vehicle
from app.utils.date_utils import normalize_competencia


def month_bounds(competence: date) -> tuple[date, date]:
    """Primeiro e último dia da competência (para cobrir o mês inteiro)."""
    c = normalize_competencia(competence)
    last = calendar.monthrange(c.year, c.month)[1]
    return date(c.year, c.month, 1), date(c.year, c.month, last)


def effective_cost_center_subquery(*, history_model, fk_col, parent_id_col, competence: date):
    """Scalar subquery CORRELATO: Centro de Custo vigente na competência p/ a entidade pai.

    Reutilizado nos filtros (colaboradores/veículos) — resolve o centro por competência em
    UMA única query (sem N+1), preservando paginação no banco.
    """
    comp_start, comp_end = month_bounds(competence)
    return (
        select(history_model.cost_center)
        .where(
            fk_col == parent_id_col,
            history_model.start_date <= comp_end,
            or_(history_model.end_date.is_(None), history_model.end_date >= comp_start),
        )
        .order_by(history_model.start_date.desc())
        .limit(1)
        .correlate_except(history_model)
        .scalar_subquery()
    )


class _CostCenterHistoryService:
    """Base genérica. Subclasses definem o model de histórico, a FK e o model da entidade."""

    history_model: type
    fk_attr: str
    entity_model: type

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _fk(self):
        return getattr(self.history_model, self.fk_attr)

    def _covers(self, comp_start: date, comp_end: date):
        return and_(
            self.history_model.start_date <= comp_end,
            or_(self.history_model.end_date.is_(None), self.history_model.end_date >= comp_start),
        )

    async def get_cost_center(self, entity_id: UUID, competence: date) -> str | None:
        """Centro de Custo vigente na competência (linha mais recente que cobre o mês)."""
        comp_start, comp_end = month_bounds(competence)
        return (
            await self.session.execute(
                select(self.history_model.cost_center)
                .where(self._fk() == entity_id, self._covers(comp_start, comp_end))
                .order_by(self.history_model.start_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def resolve_map(self, entity_ids, competence: date) -> dict[UUID, str | None]:
        """Centro vigente na competência para MUITAS entidades — 1 query (sem N+1)."""
        ids = list({i for i in entity_ids if i is not None})
        if not ids:
            return {}
        comp_start, comp_end = month_bounds(competence)
        rows = (
            await self.session.execute(
                select(self._fk(), self.history_model.cost_center, self.history_model.start_date)
                .where(self._fk().in_(ids), self._covers(comp_start, comp_end))
                .order_by(self._fk(), self.history_model.start_date.desc())
            )
        ).all()
        out: dict[UUID, str | None] = {}
        for fk, cc, _sd in rows:  # ordenado por start_date desc → 1ª ocorrência = mais recente
            if fk not in out:
                out[fk] = cc
        return out

    async def _open_row(self, entity_id: UUID):
        """Linha atualmente ABERTA (end_date IS NULL) da entidade — deve haver no máximo uma."""
        return (
            await self.session.execute(
                select(self.history_model)
                .where(self._fk() == entity_id, self.history_model.end_date.is_(None))
                .order_by(self.history_model.start_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def ensure_initial_history(self, entity) -> None:
        """Cria a linha inicial (desde 1900) se a entidade ainda não tiver histórico."""
        has = (
            await self.session.execute(
                select(self.history_model.id).where(self._fk() == entity.id).limit(1)
            )
        ).scalar_one_or_none()
        if has is None:
            self.session.add(
                self.history_model(
                    **{self.fk_attr: entity.id},
                    cost_center=(getattr(entity, "cost_center", None) or None),
                    start_date=date(1900, 1, 1),
                    end_date=None,
                )
            )
            await self.session.flush()

    async def change_cost_center(self, entity, new_cost_center: str | None, effective_date: date) -> None:
        """Fecha a linha aberta anterior e abre a nova (nunca edita histórico FECHADO).

        `effective_date` é normalizado para o 1º dia da competência. No-op se o centro
        vigente naquela competência já for o novo valor. Atualiza o cache `entity.cost_center`
        com o centro vigente HOJE.
        """
        await self.ensure_initial_history(entity)
        eff = normalize_competencia(effective_date)
        new_cc = (str(new_cost_center).strip() if new_cost_center else None) or None

        current = await self.get_cost_center(entity.id, eff)
        if (current or None) == new_cc:
            entity.cost_center = await self.get_cost_center(entity.id, date.today())
            return

        open_row = await self._open_row(entity.id)
        if open_row is not None and open_row.start_date < eff:
            # Fecha a vigente no fim da competência anterior e abre a nova.
            open_row.end_date = eff - timedelta(days=1)
            self.session.add(
                self.history_model(
                    **{self.fk_attr: entity.id}, cost_center=new_cc, start_date=eff, end_date=None
                )
            )
        elif open_row is not None:
            # Efetivo <= início da linha aberta atual: corrige o valor da própria linha aberta
            # (período ainda não fechado — não reescreve NENHUMA linha já fechada).
            open_row.cost_center = new_cc
            open_row.start_date = min(open_row.start_date, eff)
        else:
            # Sem linha aberta (todas fechadas) — abre a nova.
            self.session.add(
                self.history_model(
                    **{self.fk_attr: entity.id}, cost_center=new_cc, start_date=eff, end_date=None
                )
            )

        await self.session.flush()
        entity.cost_center = await self.get_cost_center(entity.id, date.today())


class EmployeeCostCenterService(_CostCenterHistoryService):
    history_model = EmployeeCostCenterHistory
    fk_attr = "employee_id"
    entity_model = Employee


class VehicleCostCenterService(_CostCenterHistoryService):
    history_model = VehicleCostCenterHistory
    fk_attr = "vehicle_id"
    entity_model = Vehicle


def employee_effective_cost_center_subquery(competence: date):
    """Subquery correlata do centro vigente do colaborador (usada no filtro de Mão de Obra)."""
    return effective_cost_center_subquery(
        history_model=EmployeeCostCenterHistory,
        fk_col=EmployeeCostCenterHistory.employee_id,
        parent_id_col=Employee.id,
        competence=competence,
    )


def vehicle_effective_cost_center_subquery(competence: date):
    """Subquery correlata do centro vigente do veículo (usada no filtro da aba Veículos)."""
    return effective_cost_center_subquery(
        history_model=VehicleCostCenterHistory,
        fk_col=VehicleCostCenterHistory.vehicle_id,
        parent_id_col=Vehicle.id,
        competence=competence,
    )
