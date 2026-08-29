from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission, user_has_permission
from app.api.sensitive import EMPLOYEE_SENSITIVE_FIELDS, redact
from app.core.permission_codes import (
    EMPLOYEES_CREATE,
    EMPLOYEES_DELETE,
    EMPLOYEES_LIST,
    EMPLOYEES_READ,
    EMPLOYEES_SENSITIVE,
    EMPLOYEES_UPDATE,
)
from app.core.scenario import DEFAULT_SCENARIO, Scenario, coerce_scenario
from app.database.session import get_db
from app.models.company_staff_cost import CompanyStaffCost
from app.models.user import User
from app.repositories.company_staff_cost import CompanyStaffCostRepository
from app.schemas.employee_monthly_payroll import (
    EmployeeMonthlyPayrollRead,
    EmployeeMonthlyPayrollUpsert,
)
from app.schemas.employees import (
    CLTCostPreviewRequest,
    CLTCostPreviewResponse,
    CompanyStaffCostCreate,
    CompanyStaffCostRead,
    CompanyStaffCostUpdate,
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
    PayrollResponse,
)
from app.schemas.employee_assignment import (
    EmployeeAssignmentCancel,
    EmployeeAssignmentClose,
    EmployeeAssignmentCreate,
    EmployeeAssignmentRead,
    EmployeeAssignmentUpdate,
)
from app.services.employee_assignment_service import EmployeeAssignmentService
from app.services.employee_cost_service import calculate_clt_cost_fields
from app.services.employee_monthly_payroll_service import EmployeeMonthlyPayrollService
from app.services.employees_service import EmployeesService, default_cost_reference
from app.services.payroll_service import PayrollService
from app.services.settings_service import SettingsService
from app.utils.date_utils import get_business_days, normalize_competencia


# Modelo de verbos: listagem → employees.list; leitura do módulo (detalhe/cadastro não-financeiro)
# → employees.read; mutações → create/update/delete. FINANCEIRO (folha/custos/holerite) exige
# employees.sensitive — VISUALIZAR sozinho NUNCA expõe salários/custos (spec Colaboradores).
_list = [Depends(require_permission(EMPLOYEES_LIST))]
_read = [Depends(require_permission(EMPLOYEES_READ))]
_sensitive = [Depends(require_permission(EMPLOYEES_SENSITIVE))]

router = APIRouter()


@router.post("/preview-clt-cost", response_model=CLTCostPreviewResponse, dependencies=_read)
async def preview_clt_cost(
    payload: CLTCostPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> CLTCostPreviewResponse:
    settings = await SettingsService(db).get_or_create()
    add = float(payload.additional_costs or 0)
    total = calculate_clt_cost_fields(
        salary_base=payload.salary_base,
        has_periculosidade=payload.has_periculosidade,
        has_adicional_dirigida=payload.has_adicional_dirigida,
        extra_hours_50=payload.extra_hours_50,
        extra_hours_70=payload.extra_hours_70,
        extra_hours_100=payload.extra_hours_100,
        additional_costs=add,
        vr_value=float(settings.vr_value),
        clt_charges_rate=float(settings.clt_charges_rate or 0),
        year=payload.year,
        month=payload.month,
    )
    bd = get_business_days(payload.year, payload.month)
    return CLTCostPreviewResponse(
        total_cost=total,
        business_days=bd,
        reference_month=date(payload.year, payload.month, 1),
    )


def _scenario_str(sv: Scenario | str) -> str:
    return sv.value if isinstance(sv, Scenario) else str(sv)


def _staff_row_to_read(row: CompanyStaffCost) -> CompanyStaffCostRead:
    emp = getattr(row, "employee", None)
    return CompanyStaffCostRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        employee_id=row.employee_id,
        competencia=normalize_competencia(row.competencia),
        scenario=_scenario_str(row.scenario),
        valor=float(row.valor),
        employee_full_name=emp.full_name if emp else None,
    )


@router.get("/payroll", response_model=PayrollResponse, dependencies=_sensitive)
async def get_payroll(
    competencia: date = Query(..., description="Primeiro dia do mês"),
    scenario_param: str | None = Query(
        default=None, alias="scenario", description="PREVISTO ou REALIZADO; omitir = REALIZADO"
    ),
    project_id: UUID | None = Query(default=None, description="Filtrar alocações a um projeto (custos adm. mantidos)"),
    db: AsyncSession = Depends(get_db),
) -> PayrollResponse:
    sc = coerce_scenario(scenario_param)
    return await PayrollService(db).build_payroll(
        competencia=competencia, scenario=sc, project_id=project_id
    )


@router.get("/staff-costs", response_model=list[CompanyStaffCostRead], dependencies=_sensitive)
async def list_staff_costs(
    competencia: date = Query(..., description="Primeiro dia do mês"),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyStaffCostRead]:
    sc = coerce_scenario(scenario_param)
    rows = await CompanyStaffCostRepository(db).list_by_competencia_scenario(
        competencia=competencia, scenario=sc
    )
    return [_staff_row_to_read(r) for r in rows]


@router.post("/staff-costs", response_model=CompanyStaffCostRead, dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))])
async def create_staff_cost(
    payload: CompanyStaffCostCreate,
    db: AsyncSession = Depends(get_db),
) -> CompanyStaffCostRead:
    sc = coerce_scenario(payload.scenario or DEFAULT_SCENARIO)
    comp = normalize_competencia(payload.competencia)
    row = CompanyStaffCost(
        employee_id=payload.employee_id,
        competencia=comp,
        scenario=sc,
        valor=float(payload.valor),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe custo administrativo para este colaborador, mês e cenário.",
        ) from None
    await db.refresh(row)
    loaded = await CompanyStaffCostRepository(db).get_with_employee(row.id)
    if not loaded:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao carregar registro.")
    return _staff_row_to_read(loaded)


@router.patch(
    "/staff-costs/{cost_id}",
    response_model=CompanyStaffCostRead,
    dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))],
)
async def update_staff_cost(
    cost_id: UUID,
    payload: CompanyStaffCostUpdate,
    db: AsyncSession = Depends(get_db),
) -> CompanyStaffCostRead:
    repo = CompanyStaffCostRepository(db)
    row = await repo.get_with_employee(cost_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    row.valor = float(payload.valor)
    await db.commit()
    await db.refresh(row)
    loaded = await repo.get_with_employee(cost_id)
    assert loaded is not None
    return _staff_row_to_read(loaded)


@router.delete("/staff-costs/{cost_id}", status_code=204, dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))])
async def delete_staff_cost(
    cost_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = CompanyStaffCostRepository(db)
    row = await repo.get(cost_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await repo.delete(row)
    await db.commit()


@router.get("", response_model=list[EmployeeRead], dependencies=_list)
async def list_employees(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(default=None, description="Busca por nome (ILIKE em full_name)."),
    project_id: UUID | None = Query(
        default=None,
        description="Filtra por Centro de Custo do projeto (Mão de Obra). Omitido = todos.",
    ),
    cost_center: str | None = Query(
        default=None,
        description=(
            "Filtra diretamente por Centro de Custo (a relação de colaboradores usa este, não "
            "project_id: há centros administrativos que não são projeto). Tem precedência sobre "
            "project_id quando ambos vierem."
        ),
    ),
    strict_cost_center: bool = Query(
        default=False,
        description=(
            "Com project_id: traz SÓ quem é do Centro de Custo do projeto ou tem alocação ativa "
            "nele. Sem isto (padrão do seletor de Mão de Obra), também vêm os compartilhados e os "
            "que ainda não têm centro definido."
        ),
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    competencia: date | None = Query(
        default=None,
        description="Primeiro dia do mês de competência para recalcular custo CLT na resposta.",
    ),
    user: User = Depends(get_current_user),
) -> list[EmployeeRead]:
    comp = competencia or default_cost_reference()
    svc = EmployeesService(db)
    cc = (cost_center or "").strip() if isinstance(cost_center, str) else ""
    if cc:
        # Centro de Custo explícito: não passa pela resolução via projeto.
        rows = await svc.list_employees_as_read(
            offset=offset,
            limit=limit,
            competencia=comp,
            search=search,
            cost_center=cc,
            strict_cost_center=strict_cost_center is True,
        )
        include = user_has_permission(user, EMPLOYEES_SENSITIVE)
        return [redact(r, EMPLOYEE_SENSITIVE_FIELDS, include) for r in rows]
    # Filtro de Mão de Obra por Centro de Custo do projeto — lógica ÚNICA no serviço
    # (mesma usada por /hr/employees e /collaborators), sem regra duplicada aqui.
    rows = await svc.list_employees_read_for_project(
        offset=offset,
        limit=limit,
        competencia=comp,
        search=search,
        project_id=project_id,
        # `is True` de propósito: chamadas DIRETAS ao handler (testes) não passam pelo FastAPI,
        # e aí o valor que chega é o próprio objeto `Query` — truthy. Comparar por identidade
        # mantém o modo permissivo (o do seletor de Mão de Obra) como default de verdade.
        strict_cost_center=strict_cost_center is True,
    )
    include = user_has_permission(user, EMPLOYEES_SENSITIVE)
    return [redact(r, EMPLOYEE_SENSITIVE_FIELDS, include) for r in rows]


@router.post("", response_model=EmployeeRead, dependencies=[Depends(require_permission(EMPLOYEES_CREATE))])
async def create_employee(
    payload: EmployeeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeRead:
    svc = EmployeesService(db)
    row = await svc.create_employee(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    comp = payload.cost_reference_competencia or default_cost_reference()
    read = await svc.employee_to_read(row, competencia=comp)
    # Criar NÃO concede ver: sem employees.sensitive, os valores recém-cadastrados voltam omitidos.
    include = user_has_permission(actor, EMPLOYEES_SENSITIVE)
    return redact(read, EMPLOYEE_SENSITIVE_FIELDS, include)


@router.patch("/{employee_id}", response_model=EmployeeRead, dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))])
async def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> EmployeeRead:
    svc = EmployeesService(db)
    raw = payload.model_dump(exclude_unset=True)
    row = await svc.update_employee(
        actor_user_id=actor.id,
        employee_id=employee_id,
        data=raw,
        actor=actor,
        request=request,
    )
    if "cost_reference_competencia" in raw:
        comp = raw["cost_reference_competencia"] or default_cost_reference()
    else:
        comp = default_cost_reference()
    read = await svc.employee_to_read(row, competencia=comp)
    # Editar NÃO concede ver: sem employees.sensitive, os valores salvos voltam omitidos (spec Caso 4).
    include = user_has_permission(actor, EMPLOYEES_SENSITIVE)
    return redact(read, EMPLOYEE_SENSITIVE_FIELDS, include)


@router.get(
    "/{employee_id}/monthly-payroll/{competence}",
    response_model=EmployeeMonthlyPayrollRead,
    dependencies=_sensitive,
)
async def get_monthly_payroll(
    employee_id: UUID,
    competence: str,
    db: AsyncSession = Depends(get_db),
) -> EmployeeMonthlyPayrollRead:
    row = await EmployeeMonthlyPayrollService(db).get(
        employee_id=employee_id, competence_month=competence
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Não há folha real cadastrada para esta competência.",
        )
    return EmployeeMonthlyPayrollRead.model_validate(row)


@router.post(
    "/{employee_id}/monthly-payroll/{competence}",
    response_model=EmployeeMonthlyPayrollRead,
    dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))],
)
async def upsert_monthly_payroll_post(
    employee_id: UUID,
    competence: str,
    payload: EmployeeMonthlyPayrollUpsert,
    db: AsyncSession = Depends(get_db),
) -> EmployeeMonthlyPayrollRead:
    return await EmployeeMonthlyPayrollService(db).upsert(
        employee_id=employee_id, competence_month=competence, payload=payload
    )


@router.put(
    "/{employee_id}/monthly-payroll/{competence}",
    response_model=EmployeeMonthlyPayrollRead,
    dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))],
)
async def upsert_monthly_payroll_put(
    employee_id: UUID,
    competence: str,
    payload: EmployeeMonthlyPayrollUpsert,
    db: AsyncSession = Depends(get_db),
) -> EmployeeMonthlyPayrollRead:
    return await EmployeeMonthlyPayrollService(db).upsert(
        employee_id=employee_id, competence_month=competence, payload=payload
    )


@router.delete("/{employee_id}", status_code=204, dependencies=[Depends(require_permission(EMPLOYEES_DELETE))])
async def delete_employee(
    employee_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    await EmployeesService(db).delete_employee(
        actor_user_id=actor.id, employee_id=employee_id, actor=actor, request=request
    )


# ---------------------------------------------------------------------------
# Alocações contratuais (1 colaborador → N contratos com remuneração própria)
#
# Tudo vive DENTRO do cadastro do colaborador — a tela não abre outro lugar. Usa os verbos do
# próprio módulo (`employees.*`), porque a Alocação é parte do cadastro da pessoa; os valores
# passam por `employees.sensitive`, como o resto da ficha.
# ---------------------------------------------------------------------------

ASSIGNMENT_SENSITIVE_FIELDS: tuple[str, ...] = ("salary_base", "allowance")


def _assignment_read(row, *, include_sensitive: bool) -> EmployeeAssignmentRead:
    model = EmployeeAssignmentRead.model_validate(row).model_copy(
        update={"project_name": row.project.name if row.project else None}
    )
    return redact(model, ASSIGNMENT_SENSITIVE_FIELDS, include_sensitive)


@router.get(
    "/{employee_id}/assignments",
    response_model=list[EmployeeAssignmentRead],
    dependencies=_read,
)
async def list_employee_assignments(
    employee_id: UUID,
    include_closed: bool = Query(default=True, description="Inclui alocações encerradas (histórico)"),
    include_cancelled: bool = Query(
        default=False, description="Inclui alocações canceladas (fora da tela por padrão)"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EmployeeAssignmentRead]:
    rows = await EmployeeAssignmentService(db).list_for_employee(
        employee_id, include_closed=include_closed, include_cancelled=include_cancelled
    )
    inc = user_has_permission(user, EMPLOYEES_SENSITIVE)
    return [_assignment_read(r, include_sensitive=inc) for r in rows]


@router.post(
    "/{employee_id}/assignments",
    response_model=EmployeeAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))],
)
async def create_employee_assignment(
    employee_id: UUID,
    payload: EmployeeAssignmentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmployeeAssignmentRead:
    row = await EmployeeAssignmentService(db).create(
        employee_id=employee_id, data=payload.model_dump(exclude_unset=True),
        actor=user, request=request,
    )
    return _assignment_read(row, include_sensitive=user_has_permission(user, EMPLOYEES_SENSITIVE))


@router.patch(
    "/{employee_id}/assignments/{assignment_id}",
    response_model=EmployeeAssignmentRead,
    dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))],
)
async def update_employee_assignment(
    employee_id: UUID,
    assignment_id: UUID,
    payload: EmployeeAssignmentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmployeeAssignmentRead:
    try:
        row = await EmployeeAssignmentService(db).update(
            assignment_id, payload.model_dump(exclude_unset=True), actor=user, request=request
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _assignment_read(row, include_sensitive=user_has_permission(user, EMPLOYEES_SENSITIVE))


@router.post(
    "/{employee_id}/assignments/{assignment_id}/close",
    response_model=EmployeeAssignmentRead,
    dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))],
)
async def close_employee_assignment(
    employee_id: UUID,
    assignment_id: UUID,
    payload: EmployeeAssignmentClose,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmployeeAssignmentRead:
    """Encerrar a alocação — NUNCA apaga. O histórico de atuação precisa ser reconstruível."""
    try:
        row = await EmployeeAssignmentService(db).close(
            assignment_id, end_date=payload.end_date, actor=user, request=request
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _assignment_read(row, include_sensitive=user_has_permission(user, EMPLOYEES_SENSITIVE))


@router.post(
    "/{employee_id}/assignments/{assignment_id}/cancel",
    response_model=EmployeeAssignmentRead,
    dependencies=[Depends(require_permission(EMPLOYEES_DELETE))],
)
async def cancel_employee_assignment(
    employee_id: UUID,
    assignment_id: UUID,
    payload: EmployeeAssignmentCancel,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmployeeAssignmentRead:
    """Cancelar = criada por ENGANO. Recusado (409) se já houver qualquer efeito financeiro —
    nesse caso a orientação é ENCERRAR, preservando a rastreabilidade."""
    try:
        row = await EmployeeAssignmentService(db).cancel(
            assignment_id, reason=payload.reason, actor=user, request=request
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _assignment_read(row, include_sensitive=user_has_permission(user, EMPLOYEES_SENSITIVE))


@router.post(
    "/{employee_id}/assignments/{assignment_id}/reopen",
    response_model=EmployeeAssignmentRead,
    dependencies=[Depends(require_permission(EMPLOYEES_UPDATE))],
)
async def reopen_employee_assignment(
    employee_id: UUID,
    assignment_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmployeeAssignmentRead:
    try:
        row = await EmployeeAssignmentService(db).reopen(
            assignment_id, actor=user, request=request
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _assignment_read(row, include_sensitive=user_has_permission(user, EMPLOYEES_SENSITIVE))
