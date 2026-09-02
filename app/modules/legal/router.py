"""Endpoints do Workspace Jurídico.

Autorização no padrão do sistema, com **um recurso por MENU**: `legal_cases.*` (Processos),
`legal_persons.*` (Desligados), `legal_companies.*`/`legal_projects.*` (catálogos da
Administração), `legal_dashboard.read` e `legal_reports.*` — sempre somados ao gate do workspace
(`workspace.legal.access`). Poder editar Processos NÃO concede nada sobre Desligados.

Valores monetários passam por `redact_for(...)`: sem `legal_cases.sensitive` /
`legal_persons.sensitive` o backend NÃO envia os valores (não é ocultação no frontend).

Listas e indicadores compartilham exatamente o mesmo objeto de filtros (`CaseFilters`), então os
cards e gráficos nunca divergem da tabela.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.api.sensitive import redact_for, sensitive_include
from app.core.permission_codes import (
    LEGAL_CASES_CREATE,
    LEGAL_CASES_DELETE,
    LEGAL_CASES_LIST,
    LEGAL_CASES_READ,
    LEGAL_CASES_UPDATE,
    LEGAL_COMPANIES_CREATE,
    LEGAL_COMPANIES_DELETE,
    LEGAL_COMPANIES_LIST,
    LEGAL_COMPANIES_UPDATE,
    LEGAL_DASHBOARD_READ,
    LEGAL_IMPORTS_CREATE,
    LEGAL_IMPORTS_LIST,
    LEGAL_PERSONS_CREATE,
    LEGAL_PERSONS_DELETE,
    LEGAL_PERSONS_LIST,
    LEGAL_PERSONS_READ,
    LEGAL_PERSONS_REFERENCE,
    LEGAL_PERSONS_UPDATE,
    LEGAL_PROJECTS_CREATE,
    LEGAL_PROJECTS_DELETE,
    LEGAL_PROJECTS_LIST,
    LEGAL_PROJECTS_UPDATE,
    WORKSPACE_LEGAL_ACCESS,
)
from app.database.session import get_db
from app.models.legal import LegalCase, LegalChangeLog, LegalImportRun, LegalPerson
from app.models.user import User
from app.schemas.legal import (
    LegalCaseCreate,
    LegalCaseRead,
    LegalCaseUpdate,
    LegalChangeLogRead,
    LegalCompanyCreate,
    LegalCompanyRead,
    LegalCompanyUpdate,
    LegalFacets,
    LegalOverview,
    LegalPersonCreate,
    LegalPersonDetail,
    LegalPersonRead,
    LegalPersonUpdate,
    LegalProjectCreate,
    LegalProjectRead,
    LegalProjectUpdate,
)
from app.schemas.legal import (
    LegalEventConclude,
    LegalEventCreate,
    LegalEventRead,
    LegalEventReschedule,
    LegalExecutiveSummary,
    LegalNoteCreate,
    LegalTimelineEntryRead,
)
from app.schemas.legal_import import LegalImportReport, LegalImportRunRead
from app.services.legal_import_parser import (
    LegalImportSourceError,
    ParsedSources,
    build_payload,
)
from app.services.legal_import_service import LegalImportService
from app.services.legal_operation_service import (
    LegalEventService,
    LegalTimelineService,
    LegalWorkService,
)
from app.models.legal_operation import LegalTimelineEntryType
from app.services.legal_service import MONEY_FIELDS, CaseFilters, LegalService, PersonFilters

router = APIRouter()

# Cada MENU tem seus próprios verbos — poder editar Processos não concede nada sobre Desligados
# nem sobre os catálogos. `require_permission(a, b)` é ANY-OF.
_workspace = [Depends(require_permission(WORKSPACE_LEGAL_ACCESS))]

# Processos
_cases_list = [Depends(require_permission(LEGAL_CASES_LIST))]
_cases_read = [Depends(require_permission(LEGAL_CASES_READ))]
_cases_create = [Depends(require_permission(LEGAL_CASES_CREATE))]
_cases_update = [Depends(require_permission(LEGAL_CASES_UPDATE))]
_cases_delete = [Depends(require_permission(LEGAL_CASES_DELETE))]
# Restaurar aceita update OU delete: quem pode desativar precisa poder DESFAZER. Exigir só
# `update` criaria uma porta de mão única para o perfil que tem apenas `delete`.
_cases_restore = [Depends(require_permission(LEGAL_CASES_UPDATE, LEGAL_CASES_DELETE))]
# O resumo alimenta a tela de Processos E o Dashboard executivo: qualquer um dos dois abre.
_overview = [Depends(require_permission(LEGAL_CASES_LIST, LEGAL_DASHBOARD_READ))]

# Desligados
_persons_list = [Depends(require_permission(LEGAL_PERSONS_LIST))]
_persons_read = [Depends(require_permission(LEGAL_PERSONS_READ))]
_persons_create = [Depends(require_permission(LEGAL_PERSONS_CREATE))]
_persons_update = [Depends(require_permission(LEGAL_PERSONS_UPDATE))]
_persons_delete = [Depends(require_permission(LEGAL_PERSONS_DELETE))]
_persons_restore = [Depends(require_permission(LEGAL_PERSONS_UPDATE, LEGAL_PERSONS_DELETE))]

# Catálogos (Administração). Listar é liberado a quem enxerga Processos/Desligados também: são o
# vocabulário dos filtros dessas telas — sem isso os combos ficariam vazios.
_companies_list = [
    Depends(require_permission(LEGAL_COMPANIES_LIST, LEGAL_CASES_LIST, LEGAL_PERSONS_LIST))
]
_companies_create = [Depends(require_permission(LEGAL_COMPANIES_CREATE))]
_companies_update = [Depends(require_permission(LEGAL_COMPANIES_UPDATE))]
_companies_delete = [Depends(require_permission(LEGAL_COMPANIES_DELETE))]
_companies_restore = [Depends(require_permission(LEGAL_COMPANIES_UPDATE, LEGAL_COMPANIES_DELETE))]
_projects_list = [
    Depends(require_permission(LEGAL_PROJECTS_LIST, LEGAL_CASES_LIST, LEGAL_PERSONS_LIST))
]
_projects_create = [Depends(require_permission(LEGAL_PROJECTS_CREATE))]
_projects_update = [Depends(require_permission(LEGAL_PROJECTS_UPDATE))]
_projects_delete = [Depends(require_permission(LEGAL_PROJECTS_DELETE))]
_projects_restore = [Depends(require_permission(LEGAL_PROJECTS_UPDATE, LEGAL_PROJECTS_DELETE))]

# Importação da planilha oficial. Pré-visualizar e confirmar exigem a MESMA permissão: a
# pré-visualização já revela o conteúdo do arquivo, então não faria sentido liberá-la a mais gente.
_imports_run = [Depends(require_permission(LEGAL_IMPORTS_CREATE))]
# Ver o histórico é menos que executar: quem só acompanha as cargas não precisa poder importar.
_imports_list = [Depends(require_permission(LEGAL_IMPORTS_LIST, LEGAL_IMPORTS_CREATE))]

# Histórico: quem lê qualquer uma das entidades pode ver o log (os valores seguem redigidos).
_history = [
    Depends(
        require_permission(
            LEGAL_CASES_READ, LEGAL_PERSONS_READ, LEGAL_COMPANIES_LIST, LEGAL_PROJECTS_LIST
        )
    )
]


def _case_read(case: LegalCase) -> LegalCaseRead:
    """Monta o schema desnormalizando nome/CPF da pessoa (evita N+1 no frontend)."""
    model = LegalCaseRead.model_validate(case)
    person = case.person
    return model.model_copy(
        update={
            "person_name": person.full_name if person else None,
            "person_cpf": person.cpf if person else None,
        }
    )


def _person_read(person: LegalPerson, totals: dict) -> LegalPersonRead:
    return LegalPersonRead.model_validate(person).model_copy(update=totals)


def _change_log_read(entry: LegalChangeLog, *, money_by_entity: dict[str, bool]) -> LegalChangeLogRead:
    """O histórico não pode virar porta lateral para os valores.

    Quando o campo alterado é monetário e o usuário não tem o `sensitive` **do recurso daquele
    registro** (Processos ou Desligados, decidido por `entity_type`), o antes/depois é omitido — o
    registro da alteração continua visível, só o valor some.
    """
    model = LegalChangeLogRead.model_validate(entry)
    if (entry.field or "") not in MONEY_FIELDS:
        return model
    entity = getattr(entry.entity_type, "value", entry.entity_type)
    if money_by_entity.get(str(entity), False):
        return model
    return model.model_copy(update={"old_value": None, "new_value": None})


def _case_filters(
    status_: list[str] | None,
    type_: list[str] | None,
    uf: list[str] | None,
    company: list[str] | None,
    project: list[str] | None,
    client: list[str] | None,
    person_id: UUID | None,
    value_min: float | None,
    value_max: float | None,
    q: str | None,
    basis: str,
    include_inactive: bool = False,
) -> CaseFilters:
    return CaseFilters(
        statuses=status_ or [],
        types=type_ or [],
        ufs=uf or [],
        companies=company or [],
        projects=project or [],
        clients=client or [],
        person_id=person_id,
        value_min=value_min,
        value_max=value_max,
        q=q,
        basis=basis,
        include_inactive=include_inactive,
    )


# ---------------------------------------------------------------------------
# Processos
# ---------------------------------------------------------------------------


@router.get("/cases", response_model=list[LegalCaseRead], dependencies=_cases_list + _workspace)
async def list_cases(
    status_: list[str] | None = Query(default=None, alias="status"),
    type_: list[str] | None = Query(default=None, alias="type"),
    uf: list[str] | None = Query(default=None),
    company: list[str] | None = Query(default=None),
    project: list[str] | None = Query(default=None),
    client: list[str] | None = Query(default=None),
    person_id: UUID | None = Query(default=None),
    value_min: float | None = Query(default=None),
    value_max: float | None = Query(default=None),
    q: str | None = Query(default=None),
    basis: str = Query(default="considered", pattern="^(considered|claimed)$"),
    include_inactive: bool = Query(
        default=False, description="Administração: inclui processos desativados"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LegalCaseRead]:
    filters = _case_filters(
        status_, type_, uf, company, project, client, person_id, value_min, value_max, q, basis,
        include_inactive,
    )
    rows = await LegalService(db).list_cases(filters)
    return [redact_for("legal_case", _case_read(row), user) for row in rows]


@router.get("/cases/overview", response_model=LegalOverview, dependencies=_overview + _workspace)
async def cases_overview(
    status_: list[str] | None = Query(default=None, alias="status"),
    type_: list[str] | None = Query(default=None, alias="type"),
    uf: list[str] | None = Query(default=None),
    company: list[str] | None = Query(default=None),
    project: list[str] | None = Query(default=None),
    client: list[str] | None = Query(default=None),
    person_id: UUID | None = Query(default=None),
    value_min: float | None = Query(default=None),
    value_max: float | None = Query(default=None),
    q: str | None = Query(default=None),
    basis: str = Query(default="considered", pattern="^(considered|claimed)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalOverview:
    filters = _case_filters(
        status_, type_, uf, company, project, client, person_id, value_min, value_max, q, basis
    )
    return redact_for("legal_overview", await LegalService(db).overview(filters), user)


@router.get("/cases/{case_id}", response_model=LegalCaseRead, dependencies=_cases_read + _workspace)
async def get_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCaseRead:
    row = await LegalService(db).get_case(case_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processo não encontrado.")
    return redact_for("legal_case", _case_read(row), user)


@router.post(
    "/cases",
    response_model=LegalCaseRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_cases_create + _workspace,
)
async def create_case(
    payload: LegalCaseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCaseRead:
    try:
        row = await LegalService(db).create_case(payload.model_dump(), actor=user)
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um processo com este número.",
        ) from e
    return redact_for("legal_case", _case_read(row), user)


@router.patch("/cases/{case_id}", response_model=LegalCaseRead, dependencies=_cases_update + _workspace)
async def update_case(
    case_id: UUID,
    payload: LegalCaseUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCaseRead:
    try:
        row = await LegalService(db).update_case(
            case_id, payload.model_dump(exclude_unset=True), actor=user
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um processo com este número.",
        ) from e
    return redact_for("legal_case", _case_read(row), user)


@router.post(
    "/cases/{case_id}/deactivate", response_model=LegalCaseRead, dependencies=_cases_delete + _workspace
)
async def deactivate_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCaseRead:
    """Baixa LÓGICA: o processo sai das telas analíticas e dos indicadores, mas é preservado."""
    try:
        row = await LegalService(db).set_case_active(case_id, active=False, actor=user)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return redact_for("legal_case", _case_read(row), user)


@router.post(
    "/cases/{case_id}/restore", response_model=LegalCaseRead, dependencies=_cases_restore + _workspace
)
async def restore_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCaseRead:
    try:
        row = await LegalService(db).set_case_active(case_id, active=True, actor=user)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return redact_for("legal_case", _case_read(row), user)


# ---------------------------------------------------------------------------
# Ex-colaboradores
# ---------------------------------------------------------------------------


@router.get("/persons", response_model=list[LegalPersonRead], dependencies=_persons_list + _workspace)
async def list_persons(
    company: list[str] | None = Query(default=None),
    project: list[str] | None = Query(default=None),
    client: list[str] | None = Query(default=None),
    has_cases: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    include_inactive: bool = Query(
        default=False, description="Administração: inclui pessoas desativadas"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LegalPersonRead]:
    filters = PersonFilters(
        companies=company or [],
        projects=project or [],
        clients=client or [],
        has_cases=has_cases,
        q=q,
        include_inactive=include_inactive,
    )
    rows = await LegalService(db).list_persons(filters)
    return [redact_for("legal_person", _person_read(p, t), user) for p, t in rows]


@router.get("/persons/facets", response_model=LegalFacets, dependencies=_persons_list + _workspace)
async def persons_facets(db: AsyncSession = Depends(get_db)) -> LegalFacets:
    return await LegalService(db).person_facets()


@router.get(
    "/persons/search",
    response_model=list[dict],
    dependencies=[Depends(require_permission(LEGAL_PERSONS_REFERENCE))],
)
async def search_persons(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[dict]:
    """Endpoint leve de REFERÊNCIA de ex-colaboradores, para selects de OUTROS módulos.

    Existe para o Endividamento (Financeiro) poder vincular um passivo à pessoa certa sem exigir
    acesso ao workspace Jurídico: pede apenas `legal_persons.reference`, e NÃO o combo
    `legal_persons.list` + acesso ao workspace que a listagem completa exige.

    Devolve o MÍNIMO para identificar alguém num combo — nunca CPF, valor de rescisão, FGTS ou
    dado de processo. `company` e `termination_date` entram porque homônimo é comum numa lista de
    159 pessoas, e sem eles não há como saber qual é qual.

    Declarado antes de `/persons/{person_id}`: fosse depois, "search" seria lido como um id.
    """
    term = (q or "").strip()
    if not term:
        return []
    rows = await LegalService(db).search_persons_reference(term=term, limit=limit)
    return [
        {
            "id": str(r.id),
            "name": r.full_name,
            "company": r.company,
            "termination_date": r.termination_date.isoformat() if r.termination_date else None,
        }
        for r in rows
        if getattr(r, "full_name", None)
    ]


@router.get(
    "/persons/{person_id}", response_model=LegalPersonDetail, dependencies=_persons_read + _workspace
)
async def get_person(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalPersonDetail:
    found = await LegalService(db).get_person(person_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada.")
    person, totals = found
    # DOIS gates independentes nesta resposta: os dados da pessoa (rescisão/FGTS/totais) dependem
    # de `legal_persons.sensitive`; os processos da ficha, de `legal_cases.sensitive`. Por isso
    # cada nível é redigido com o SEU recurso, em vez de usar `nested` — que propagaria a decisão
    # do pai e deixaria quem tem só o sensitive de Desligados enxergar valor de processo.
    detail = LegalPersonDetail.model_validate(person).model_copy(
        update={
            **totals,
            "cases": [redact_for("legal_case", _case_read(c), user) for c in (person.cases or [])],
        }
    )
    return redact_for("legal_person", detail, user)


@router.post(
    "/persons",
    response_model=LegalPersonRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_persons_create + _workspace,
)
async def create_person(
    payload: LegalPersonCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalPersonRead:
    try:
        row = await LegalService(db).create_person(payload.model_dump(), actor=user)
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe um cadastro com este CPF."
        ) from e
    empty = {
        "case_count": 0,
        "total_claimed": 0.0,
        "total_considered": 0.0,
        "total_agreed": 0.0,
        "total_paid": 0.0,
        "total_pending": 0.0,
    }
    return redact_for("legal_person", _person_read(row, empty), user)


@router.patch(
    "/persons/{person_id}", response_model=LegalPersonRead, dependencies=_persons_update + _workspace
)
async def update_person(
    person_id: UUID,
    payload: LegalPersonUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalPersonRead:
    svc = LegalService(db)
    try:
        await svc.update_person(person_id, payload.model_dump(exclude_unset=True), actor=user)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe um cadastro com este CPF."
        ) from e
    found = await svc.get_person(person_id)
    assert found is not None  # acabou de ser atualizado
    person, totals = found
    return redact_for("legal_person", _person_read(person, totals), user)


async def _person_response(svc: LegalService, person_id: UUID, user: User) -> LegalPersonRead:
    found = await svc.get_person(person_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada.")
    person, totals = found
    return redact_for("legal_person", _person_read(person, totals), user)


@router.post(
    "/persons/{person_id}/deactivate",
    response_model=LegalPersonRead,
    dependencies=_persons_delete + _workspace,
)
async def deactivate_person(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalPersonRead:
    """Baixa LÓGICA. Os processos vinculados continuam ativos e no passivo, de propósito."""
    svc = LegalService(db)
    try:
        await svc.set_person_active(person_id, active=False, actor=user)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return await _person_response(svc, person_id, user)


@router.post(
    "/persons/{person_id}/restore",
    response_model=LegalPersonRead,
    dependencies=_persons_restore + _workspace,
)
async def restore_person(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalPersonRead:
    svc = LegalService(db)
    try:
        await svc.set_person_active(person_id, active=True, actor=user)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return await _person_response(svc, person_id, user)


# ---------------------------------------------------------------------------
# Administração — catálogos de Empresas e Projetos (vocabulário dos filtros)
# ---------------------------------------------------------------------------


@router.get("/companies", response_model=list[LegalCompanyRead], dependencies=_companies_list + _workspace)
async def list_companies(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[LegalCompanyRead]:
    rows = await LegalService(db).list_companies(include_inactive=include_inactive)
    return [
        LegalCompanyRead.model_validate(row).model_copy(update={"case_count": count})
        for row, count in rows
    ]


@router.post(
    "/companies",
    response_model=LegalCompanyRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_companies_create + _workspace,
)
async def create_company(
    payload: LegalCompanyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCompanyRead:
    try:
        row = await LegalService(db).create_catalog("companies", payload.model_dump(), actor=user)
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe uma empresa com este nome."
        ) from e
    return LegalCompanyRead.model_validate(row)


@router.patch(
    "/companies/{company_id}", response_model=LegalCompanyRead, dependencies=_companies_update + _workspace
)
async def update_company(
    company_id: UUID,
    payload: LegalCompanyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCompanyRead:
    try:
        row = await LegalService(db).update_catalog(
            "companies", company_id, payload.model_dump(exclude_unset=True), actor=user
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe uma empresa com este nome."
        ) from e
    return LegalCompanyRead.model_validate(row)


@router.post(
    "/companies/{company_id}/deactivate",
    response_model=LegalCompanyRead,
    dependencies=_companies_delete + _workspace,
)
async def deactivate_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCompanyRead:
    return await _set_catalog(db, "companies", company_id, False, user, LegalCompanyRead)


@router.post(
    "/companies/{company_id}/restore",
    response_model=LegalCompanyRead,
    dependencies=_companies_restore + _workspace,
)
async def restore_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalCompanyRead:
    return await _set_catalog(db, "companies", company_id, True, user, LegalCompanyRead)


@router.get("/projects", response_model=list[LegalProjectRead], dependencies=_projects_list + _workspace)
async def list_projects(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[LegalProjectRead]:
    rows = await LegalService(db).list_projects(include_inactive=include_inactive)
    return [
        LegalProjectRead.model_validate(row).model_copy(update={"case_count": count})
        for row, count in rows
    ]


@router.post(
    "/projects",
    response_model=LegalProjectRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_projects_create + _workspace,
)
async def create_project(
    payload: LegalProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalProjectRead:
    try:
        row = await LegalService(db).create_catalog("projects", payload.model_dump(), actor=user)
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe um projeto com este nome."
        ) from e
    return LegalProjectRead.model_validate(row)


@router.patch(
    "/projects/{project_id}", response_model=LegalProjectRead, dependencies=_projects_update + _workspace
)
async def update_project(
    project_id: UUID,
    payload: LegalProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalProjectRead:
    try:
        row = await LegalService(db).update_catalog(
            "projects", project_id, payload.model_dump(exclude_unset=True), actor=user
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe um projeto com este nome."
        ) from e
    return LegalProjectRead.model_validate(row)


@router.post(
    "/projects/{project_id}/deactivate",
    response_model=LegalProjectRead,
    dependencies=_projects_delete + _workspace,
)
async def deactivate_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalProjectRead:
    return await _set_catalog(db, "projects", project_id, False, user, LegalProjectRead)


@router.post(
    "/projects/{project_id}/restore",
    response_model=LegalProjectRead,
    dependencies=_projects_restore + _workspace,
)
async def restore_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalProjectRead:
    return await _set_catalog(db, "projects", project_id, True, user, LegalProjectRead)


async def _set_catalog(db: AsyncSession, kind: str, row_id: UUID, active: bool, user: User, schema):
    try:
        row = await LegalService(db).set_catalog_active(kind, row_id, active=active, actor=user)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return schema.model_validate(row)


# ---------------------------------------------------------------------------
# Administração — histórico de alterações
# ---------------------------------------------------------------------------


@router.get(
    "/change-logs", response_model=list[LegalChangeLogRead], dependencies=_history + _workspace
)
async def list_change_logs(
    entity_type: str | None = Query(default=None, description="PERSON | CASE | COMPANY | PROJECT"),
    entity_id: UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LegalChangeLogRead]:
    rows = await LegalService(db).list_change_logs(
        entity_type=entity_type, entity_id=entity_id, limit=limit
    )
    # Um gate por recurso: quem só tem "sensitive" de Processos não lê valores de Desligados.
    money_by_entity = {
        "CASE": sensitive_include("legal_case", user),
        "PERSON": sensitive_include("legal_person", user),
        "COMPANY": True,  # catálogos não têm campo monetário
        "PROJECT": True,
    }
    return [_change_log_read(row, money_by_entity=money_by_entity) for row in rows]


# ---------------------------------------------------------------------------
# Administração — importação da planilha oficial
# ---------------------------------------------------------------------------

MAX_IMPORT_BYTES = 10 * 1024 * 1024


async def _read_source_files(
    spreadsheet: UploadFile, panel: UploadFile | None
) -> ParsedSources:
    """Lê os arquivos enviados e aplica a transformação oficial do módulo.

    A planilha é obrigatória; o Painel de Passivo é opcional — sem ele a importação funciona,
    mas não traz valores da causa, valor considerado nem link do JusBrasil (e, por isso mesmo,
    **preserva** os que já estiverem gravados em vez de apagá-los).
    """
    name = (spreadsheet.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie a planilha oficial do Jurídico no formato .xlsx.",
        )
    content = await spreadsheet.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Planilha vazia.")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Planilha muito grande (máximo 10 MB).",
        )

    panel_content: bytes | None = None
    if panel is not None and (panel.filename or ""):
        panel_content = await panel.read()
        if len(panel_content) > MAX_IMPORT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Painel de Passivo muito grande (máximo 10 MB).",
            )
        if not panel_content:
            panel_content = None

    try:
        return build_payload(
            spreadsheet=content,
            panel=panel_content,
            spreadsheet_name=spreadsheet.filename or "planilha.xlsx",
            panel_name=(panel.filename if panel_content else None),
        )
    except LegalImportSourceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/imports",
    response_model=list[LegalImportRunRead],
    dependencies=_imports_list + _workspace,
)
async def list_legal_imports(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[LegalImportRunRead]:
    """Histórico das importações confirmadas (trilha de auditoria), da mais recente para a antiga."""
    rows = (
        (
            await db.execute(
                select(LegalImportRun).order_by(LegalImportRun.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [LegalImportRunRead.model_validate(row) for row in rows]


@router.post(
    "/imports/preview",
    response_model=LegalImportReport,
    dependencies=_imports_run + _workspace,
)
async def preview_legal_import(
    spreadsheet: UploadFile = File(..., description="Planilha oficial (.xlsx)"),
    panel: UploadFile | None = File(default=None, description="painel_passivo.html (opcional)"),
    db: AsyncSession = Depends(get_db),
) -> LegalImportReport:
    """Simula a importação e devolve o que seria criado/atualizado. NÃO grava nada."""
    parsed = await _read_source_files(spreadsheet, panel)
    report = await LegalImportService(db).preview(parsed)
    # Garantia explícita de que a conferência é somente-leitura, mesmo que algo tenha sido
    # carregado na sessão durante o cálculo.
    await db.rollback()
    return report


@router.post(
    "/imports/confirm",
    response_model=LegalImportReport,
    dependencies=_imports_run + _workspace,
)
async def confirm_legal_import(
    request: Request,
    spreadsheet: UploadFile = File(..., description="Planilha oficial (.xlsx)"),
    panel: UploadFile | None = File(default=None, description="painel_passivo.html (opcional)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LegalImportReport:
    """Executa a importação. Os mesmos arquivos da pré-visualização produzem o mesmo resultado."""
    parsed = await _read_source_files(spreadsheet, panel)
    return await LegalImportService(db).apply(parsed, actor=user, request=request)


# ---------------------------------------------------------------------------
# Sprint 0 — Central de Trabalho, Agenda e Timeline
#
# Permissões: reaproveitam os recursos JÁ existentes do módulo (`legal_cases.*`). A
# especificação prevê recursos próprios (`legal_events`, `legal_timeline`) na Fase 1; trocar o
# gate depois é uma linha, e evita mexer agora em permissões semeadas nos perfis.
# ---------------------------------------------------------------------------


@router.get("/work-center", dependencies=_cases_list + _workspace)
async def work_center(db: AsyncSession = Depends(get_db)) -> dict:
    """Central de Trabalho: o que exige ação hoje, o que vem na semana e o que não tem dono."""
    return await LegalWorkService(db).work_center()


@router.get("/summary", response_model=LegalExecutiveSummary, dependencies=_overview + _workspace)
async def executive_summary(db: AsyncSession = Depends(get_db)) -> LegalExecutiveSummary:
    return LegalExecutiveSummary(**await LegalWorkService(db).executive_summary())


@router.get("/events", response_model=list[LegalEventRead], dependencies=_cases_list + _workspace)
async def list_events(
    start: datetime = Query(..., description="Início da janela (inclusive)"),
    end: datetime = Query(..., description="Fim da janela (inclusive)"),
    case_id: UUID | None = Query(default=None, description="Recorta os compromissos de um processo."),
    db: AsyncSession = Depends(get_db),
) -> list[LegalEventRead]:
    events = await LegalEventService(db).list_between(start=start, end=end, case_id=case_id)
    return await _events_with_case_context(db, events)


@router.post(
    "/events", response_model=LegalEventRead, status_code=201, dependencies=_cases_update + _workspace
)
async def create_event(
    payload: LegalEventCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> LegalEventRead:
    event = await LegalEventService(db).create(payload.model_dump(), actor_id=actor.id)
    await db.commit()
    await db.refresh(event)
    return (await _events_with_case_context(db, [event]))[0]


@router.post(
    "/events/{event_id}/conclude",
    response_model=LegalEventRead,
    dependencies=_cases_update + _workspace,
)
async def conclude_event(
    event_id: UUID,
    payload: LegalEventConclude,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> LegalEventRead:
    event = await LegalEventService(db).conclude(event_id, outcome=payload.outcome, actor_id=actor.id)
    if event is None:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")
    await db.commit()
    await db.refresh(event)
    return (await _events_with_case_context(db, [event]))[0]


@router.post(
    "/events/{event_id}/reschedule",
    response_model=LegalEventRead,
    dependencies=_cases_update + _workspace,
)
async def reschedule_event(
    event_id: UUID,
    payload: LegalEventReschedule,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> LegalEventRead:
    """Adiar preserva o histórico: o evento antigo fica ADIADO e aponta o novo."""
    novo = await LegalEventService(db).reschedule(
        event_id, new_datetime=payload.new_datetime, reason=payload.reason, actor_id=actor.id
    )
    if novo is None:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")
    await db.commit()
    await db.refresh(novo)
    return (await _events_with_case_context(db, [novo]))[0]


@router.get(
    "/cases/{case_id}/timeline",
    response_model=list[LegalTimelineEntryRead],
    dependencies=_cases_read + _workspace,
)
async def case_timeline(case_id: UUID, db: AsyncSession = Depends(get_db)) -> list[LegalTimelineEntryRead]:
    rows = await LegalTimelineService(db).list_for_case(case_id)
    return [LegalTimelineEntryRead.model_validate(r) for r in rows]


@router.post(
    "/cases/{case_id}/timeline",
    response_model=LegalTimelineEntryRead,
    status_code=201,
    dependencies=_cases_update + _workspace,
)
async def add_case_note(
    case_id: UUID,
    payload: LegalNoteCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> LegalTimelineEntryRead:
    """Observação da equipe vira FATO datado — nunca um campo que alguém sobrescreve."""
    entry = await LegalTimelineService(db).record(
        case_id=case_id,
        entry_type=LegalTimelineEntryType.NOTA,
        title=payload.title,
        description=payload.description,
        occurred_at=payload.occurred_at,
        created_by_id=actor.id,
    )
    await db.commit()
    await db.refresh(entry)
    return LegalTimelineEntryRead.model_validate(entry)


async def _events_with_case_context(db: AsyncSession, events: list) -> list[LegalEventRead]:
    """Anexa número do processo e reclamante para a linha da agenda ser autoexplicativa."""
    ids = {e.case_id for e in events if e.case_id}
    contexto: dict = {}
    if ids:
        rows = await db.execute(
            select(LegalCase.id, LegalCase.case_number, LegalCase.claimant_name).where(LegalCase.id.in_(ids))
        )
        contexto = {cid: (numero, reclamante) for cid, numero, reclamante in rows.all()}
    out = []
    for e in events:
        read = LegalEventRead.model_validate(e)
        numero, reclamante = contexto.get(e.case_id, (None, None))
        out.append(read.model_copy(update={"case_number": numero, "claimant": reclamante}))
    return out
