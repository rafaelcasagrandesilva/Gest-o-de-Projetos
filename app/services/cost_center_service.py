"""Serviço central de Centros de Custo — fonte ÚNICA para os combos de cadastro.

Todo lugar do sistema que oferece um Centro de Custo para escolha (cadastro/edição de Colaboradores,
Veículos e Projetos) deve consumir `CostCenterService.list_available_cost_centers()`. Não deve mais
existir cada tela montando sua própria lista.

Composição da lista (nova arquitetura):
  1. Centros Administrativos fixos (`ADMIN_COST_CENTERS`) — existem sempre.
  2. Centros Operacionais = `projects.cost_center` (DISTINCT) dos projetos ATIVOS
     (`is_active = true AND closed_at IS NULL AND deleted_at IS NULL`).

Usa a coluna `projects.cost_center` (e NÃO o nome do projeto): Centro de Custo e nome do projeto são
conceitos distintos — isso permite, no futuro, vários projetos pertencerem ao mesmo Centro de Custo.

Projetos encerrados/apagados NÃO entram na lista para novos cadastros. A compatibilidade com um
registro já vinculado a um Centro de Custo hoje encerrado é tratada no frontend (fallback por-registro
que reexibe o valor gravado rotulado como "(encerrado)"), sem reintroduzi-lo na lista global.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants.cost_centers import ADMIN_COST_CENTERS
from app.models.project import Project


class CostCenterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _active_project_cost_centers(self) -> list[str]:
        """`projects.cost_center` (DISTINCT) apenas de projetos ativos (não encerrados, não apagados)."""
        rows = (
            await self.session.execute(
                select(Project.cost_center)
                .where(
                    Project.cost_center.is_not(None),
                    Project.is_active.is_(True),
                    Project.closed_at.is_(None),
                    Project.deleted_at.is_(None),
                )
                .distinct()
            )
        ).scalars().all()
        return [str(c).strip() for c in rows if c and str(c).strip()]

    async def list_available_cost_centers(self) -> list[str]:
        """Lista oficial de Centros de Custo disponíveis para novos cadastros.

        = Administrativos fixos (ordem canônica) ∪ Centros de projetos ativos (alfabético pt-BR).
        Deduplicado case-insensitive: se um projeto ativo usa um nome que coincide com um centro
        administrativo, o administrativo prevalece (não duplica).
        """
        seen_lower = {cc.lower() for cc in ADMIN_COST_CENTERS}
        operational: dict[str, str] = {}
        for cc in await self._active_project_cost_centers():
            key = cc.lower()
            if key in seen_lower or key in operational:
                continue
            operational[key] = cc
        ops_sorted = sorted(operational.values(), key=lambda s: s.lower())
        return [*ADMIN_COST_CENTERS, *ops_sorted]
