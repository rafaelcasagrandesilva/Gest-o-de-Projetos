from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission, user_has_any_permission
from app.core.permission_codes import (
    COMPANY_FINANCE_READ,
    COMPANY_FINANCE_UPDATE,
    PROJECTS_READ,
    PROJECTS_UPDATE,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.payment_variable_component import (
    PaymentVariableComponentCreate,
    PaymentVariableComponentRead,
    PaymentVariableComponentUpdate,
    VariableComponentReplace,
)
from app.services.payment_variable_component_service import PaymentVariableComponentService

router = APIRouter()

# Leitura/edição exige a permissão do CONTEXTO (isolamento de módulos): Projeto usa
# projects.*; Custo Fixo usa company_finance.*. O gate do endpoint aceita qualquer um dos
# dois; o handler refina pelo contexto do lançamento.
_READ_ANY = [Depends(require_permission(PROJECTS_READ, COMPANY_FINANCE_READ))]
_EDIT_ANY = [Depends(require_permission(PROJECTS_UPDATE, COMPANY_FINANCE_UPDATE))]


def _require_project_ctx(user: User) -> None:
    if not user_has_any_permission(user, PROJECTS_UPDATE):
        raise HTTPException(status_code=403, detail="Sem permissão para editar componentes de projeto.")


def _require_fixed_ctx(user: User) -> None:
    if not user_has_any_permission(user, COMPANY_FINANCE_UPDATE):
        raise HTTPException(status_code=403, detail="Sem permissão para editar componentes de custo fixo.")


@router.get("", response_model=list[PaymentVariableComponentRead], dependencies=_READ_ANY)
async def list_variable_components(
    project_labor_id: UUID | None = Query(default=None),
    company_financial_item_id: UUID | None = Query(default=None),
    competencia: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentVariableComponentRead]:
    svc = PaymentVariableComponentService(db)
    if project_labor_id is not None:
        rows = await svc.list_for_project_labor(project_labor_id)
    elif company_financial_item_id is not None and competencia is not None:
        rows = await svc.list_for_company_item(company_financial_item_id, competencia)
    else:
        raise HTTPException(
            status_code=400,
            detail="Informe project_labor_id OU (company_financial_item_id + competencia).",
        )
    return [PaymentVariableComponentRead.model_validate(r) for r in rows]


@router.post("", response_model=PaymentVariableComponentRead, dependencies=_EDIT_ANY)
async def create_variable_component(
    payload: PaymentVariableComponentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaymentVariableComponentRead:
    if payload.project_labor_id is not None:
        _require_project_ctx(user)
    else:
        _require_fixed_ctx(user)
    svc = PaymentVariableComponentService(db)
    row = await svc.create(payload.model_dump())
    await db.commit()  # transação única: componente + snapshot
    return PaymentVariableComponentRead.model_validate(row)


@router.patch("/{component_id}", response_model=PaymentVariableComponentRead, dependencies=_EDIT_ANY)
async def update_variable_component(
    component_id: UUID,
    payload: PaymentVariableComponentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaymentVariableComponentRead:
    svc = PaymentVariableComponentService(db)
    current = await svc.get(component_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Componente não encontrado.")
    if current.project_labor_id is not None:
        _require_project_ctx(user)
    else:
        _require_fixed_ctx(user)
    row = await svc.update(component_id, payload.model_dump(exclude_unset=True))
    await db.commit()
    return PaymentVariableComponentRead.model_validate(row)


@router.put(
    "/project-labor/{labor_id}",
    response_model=list[PaymentVariableComponentRead],
    dependencies=_EDIT_ANY,
)
async def replace_project_labor_components(
    labor_id: UUID,
    payload: VariableComponentReplace,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PaymentVariableComponentRead]:
    """Salva o conjunto completo de componentes do vínculo em UMA operação (transação única)."""
    _require_project_ctx(user)
    svc = PaymentVariableComponentService(db)
    rows = await svc.replace_for_project_labor(labor_id, [i.model_dump() for i in payload.items])
    await db.commit()
    return [PaymentVariableComponentRead.model_validate(r) for r in rows]


@router.put(
    "/company-item/{item_id}",
    response_model=list[PaymentVariableComponentRead],
    dependencies=_EDIT_ANY,
)
async def replace_company_item_components(
    item_id: UUID,
    payload: VariableComponentReplace,
    competencia: date = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PaymentVariableComponentRead]:
    """Salva o conjunto de componentes do item de Custo Fixo na competência (transação única)."""
    _require_fixed_ctx(user)
    svc = PaymentVariableComponentService(db)
    rows = await svc.replace_for_company_item(
        item_id, competencia, [i.model_dump() for i in payload.items]
    )
    await db.commit()
    return [PaymentVariableComponentRead.model_validate(r) for r in rows]


@router.delete("/{component_id}", status_code=204, dependencies=_EDIT_ANY)
async def delete_variable_component(
    component_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    svc = PaymentVariableComponentService(db)
    current = await svc.get(component_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Componente não encontrado.")
    if current.project_labor_id is not None:
        _require_project_ctx(user)
    else:
        _require_fixed_ctx(user)
    await svc.delete(component_id)
    await db.commit()
