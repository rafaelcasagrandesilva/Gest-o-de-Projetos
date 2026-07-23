from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.permission_codes import COST_CENTER_REFERENCE
from app.database.session import get_db
from app.repositories.projects import ProjectRepository

router = APIRouter()


class CostCenterRefItem(BaseModel):
    """Item MÍNIMO de referência de Centro de Custo para seletores.

    `ref` é o identificador gravável (id do projeto que atua como Centro de Custo); `label` é o nome
    exibido. NUNCA inclui dados financeiros (contrato, valores, comprador, etc.).
    """

    ref: str
    label: str


@router.get(
    "/reference",
    response_model=list[CostCenterRefItem],
    dependencies=[Depends(require_permission(COST_CENTER_REFERENCE))],
)
async def list_cost_center_references(db: AsyncSession = Depends(get_db)) -> list[CostCenterRefItem]:
    """Seletores de Centro de Custo (Etapa 2).

    Exige apenas `cost_center.reference` — não `projects.view`. Retorna os projetos ATIVOS como
    opções de Centro de Custo, com APENAS {ref, label} (id + nome). Os Centros Administrativos fixos
    (Administrativo, Financeiro, RH, Almoxarifado) são constantes do frontend e não vêm daqui.
    Nunca expõe contrato, valores ou qualquer campo financeiro do projeto.
    """
    projects = await ProjectRepository(db).list_active()
    return [CostCenterRefItem(ref=str(p.id), label=p.name) for p in projects]
