from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission, user_has_permission
from app.api.sensitive import EMPLOYEE_SENSITIVE_FIELDS, redact
from app.core.permission_codes import COST_CENTER_REFERENCE, EMPLOYEES_LIST, EMPLOYEES_REFERENCE, EMPLOYEES_SENSITIVE
from app.database.session import get_db
from app.models.user import User
from app.schemas.employees import EmployeeRead
from app.services.employees_service import EmployeesService, default_cost_reference


router = APIRouter()


@router.get("", response_model=list[EmployeeRead], dependencies=[Depends(require_permission(EMPLOYEES_LIST))])
async def list_collaborators(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(default=None, description="Busca por nome (ILIKE em full_name)."),
    project_id: UUID | None = Query(
        default=None,
        description="Filtra por Centro de Custo do projeto (Mão de Obra). Omitido = todos.",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    competencia: date | None = Query(default=None, description="Competência para custo (opcional)."),
    user: User = Depends(get_current_user),
) -> list[EmployeeRead]:
    comp = competencia or default_cost_reference()
    rows = await EmployeesService(db).list_employees_read_for_project(
        offset=offset, limit=limit, competencia=comp, search=search, project_id=project_id
    )
    include = user_has_permission(user, EMPLOYEES_SENSITIVE)
    return [redact(r, EMPLOYEE_SENSITIVE_FIELDS, include) for r in rows]


@router.get(
    "/search",
    response_model=list[dict],
    dependencies=[Depends(require_permission(EMPLOYEES_REFERENCE))],
)
async def search_collaborators(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, max_length=255),
    project_id: UUID | None = Query(
        default=None,
        description="Filtra por Centro de Custo do projeto. Omitido = todos (compatível).",
    ),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[dict]:
    """
    Endpoint leve de REFERÊNCIA para selects/autocomplete (Etapa 2).
    Exige apenas `employees.reference` — quem tem `employees.view` continua passando (o legado
    implica reference no grafo). Retorna EXCLUSIVAMENTE {id, name}: nunca salário, custo, encargos
    ou qualquer dado financeiro. Com `project_id`, filtra pelo Centro de Custo do projeto.
    """
    term = (q or "").strip()
    if not term:
        return []
    rows = await EmployeesService(db).list_employees_for_project(
        offset=0, limit=limit, search=term, project_id=project_id
    )
    return [{"id": str(r.id), "name": r.full_name} for r in rows if getattr(r, "full_name", None)]


@router.get(
    "/cost-centers",
    response_model=list[str],
    dependencies=[Depends(require_permission(COST_CENTER_REFERENCE))],
)
async def list_cost_centers(db: AsyncSession = Depends(get_db)) -> list[str]:
    """Centros de Custo disponíveis para os selects de cadastro.

    Fonte ÚNICA (nova arquitetura): delega a `CostCenterService.list_available_cost_centers()`,
    que compõe os Centros Administrativos fixos com os Centros de Custo dos projetos ATIVOS
    (`projects.cost_center`, filtrando encerrados/apagados). Projetos encerrados NÃO aparecem para
    novos cadastros — a compatibilidade de um valor legado já gravado é tratada no frontend.
    """
    from app.services.cost_center_service import CostCenterService

    return await CostCenterService(db).list_available_cost_centers()

