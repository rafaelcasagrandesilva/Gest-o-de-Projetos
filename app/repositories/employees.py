from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeAllocation
from app.repositories.base import Repository


class EmployeeRepository(Repository[Employee]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Employee)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        cost_center: str | None = None,
        competence: date | None = None,
        strict_cost_center: bool = False,
    ) -> list[Employee]:
        stmt = select(Employee)
        if search is not None:
            q = str(search).strip()
            if q:
                stmt = stmt.where(Employee.full_name.ilike(f"%{q}%"))
        # Filtro por Centro de Custo. Dois modos:
        #   padrão  (seletor de Mão de Obra) — do MESMO centro OU com alocação ativa nele OU
        #           compartilhados (can_allocate_other_cost_centers) OU sem centro definido;
        #   estrito (relação de colaboradores) — só quem é do centro ou tem alocação ativa nele.
        #
        # TEMPORAL: com `competence`, o centro do colaborador é resolvido POR COMPETÊNCIA a
        # partir do histórico (subquery correlata — 1 query, sem N+1, paginação no banco).
        # Sem `competence`, cai no cache `employees.cost_center` (compatibilidade).
        cc = (cost_center or "").strip()
        if cc:
            from app.services.cost_center_history_service import (
                employee_effective_cost_center_subquery,
            )

            eff_cc = (
                employee_effective_cost_center_subquery(competence)
                if competence is not None
                else Employee.cost_center
            )
            # A ALOCAÇÃO passa a determinar onde o colaborador atua: quem tem alocação ATIVA
            # naquele Centro de Custo aparece, mesmo que o seu centro PRINCIPAL seja outro. Sem
            # isto, o multi-contrato ficaria bloqueado no próprio seletor. O flag legado
            # `can_allocate_other_cost_centers` continua valendo para quem já o tinha marcado.
            from app.models.employee_assignment import AssignmentStatus, EmployeeAssignment

            tem_alocacao_no_centro = (
                select(EmployeeAssignment.id)
                .where(
                    EmployeeAssignment.employee_id == Employee.id,
                    EmployeeAssignment.status == AssignmentStatus.ATIVA,
                    func.lower(EmployeeAssignment.cost_center) == cc.lower(),
                )
                .exists()
            )
            # ESTRITO (listagem/relação de colaboradores): pertence ao centro ou tem alocação
            # ativa nele. Fora ficam os "elegíveis por conveniência" — quem pode atuar em outros
            # centros e quem ainda não tem centro definido —, que só fazem sentido em um SELETOR
            # de alocação, não numa relação de quem é do projeto.
            pertence = or_(func.lower(eff_cc) == cc.lower(), tem_alocacao_no_centro)
            stmt = stmt.where(
                pertence
                if strict_cost_center
                else or_(
                    pertence,
                    Employee.can_allocate_other_cost_centers.is_(True),
                    eff_cc.is_(None),
                )
            )
        stmt = stmt.order_by(Employee.full_name.asc()).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_active_ordered(self, *, limit: int = 10_000) -> list[Employee]:
        stmt = (
            select(Employee)
            .where(Employee.is_active)
            .order_by(Employee.full_name.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())


# `EmployeeAllocationRepository` foi removido na limpeza da RC (endpoints legados retirados,
# 0 linhas na tabela). A tabela `employee_allocations` permanece no banco.
