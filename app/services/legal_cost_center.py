"""Vínculo projeto do Jurídico → centro de custo do SGC (`legal_projects.cost_center_ref`).

Os nomes de projeto do Jurídico vêm da planilha ("Energisa - Censo de IP e Uso Mútuo - MT") e não
casam com os do SGC ("Censo de IP e UM - MT"); por isso o vínculo é cadastrado, nunca deduzido.
O ref segue o mesmo formato do Endividamento: código sistêmico ou UUID de projeto — e aqui um
projeto ENCERRADO é válido, porque a dívida de um desligado pertence ao contrato em que ele
trabalhou, mesmo que o contrato já tenha acabado.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import LegalPerson, LegalProject
from app.models.project import Project
from app.services.company_finance_cost_center import CC_SYSTEM_LABELS


def _as_uuid(ref: str) -> UUID | None:
    try:
        return UUID(ref)
    except ValueError:
        return None


async def validate_cost_center_ref(db: AsyncSession, ref: str | None) -> str | None:
    """Normaliza o ref (vazio → None) e recusa o que não for sistêmico nem projeto existente."""
    ref = (ref or "").strip()
    if not ref:
        return None
    if ref in CC_SYSTEM_LABELS:
        return ref
    project_id = _as_uuid(ref)
    project = await db.get(Project, project_id) if project_id else None
    if project is None or project.deleted_at is not None:
        raise ValueError("Centro de custo inválido: escolha Administrativo, Financeiro, Almoxarifado, RH ou um projeto.")
    return ref


async def cost_center_labels(db: AsyncSession, refs: Iterable[str | None]) -> dict[str, str]:
    """ref → rótulo exibido. Projeto encerrado leva "(encerrado)" para não parecer um ativo."""
    labels: dict[str, str] = {}
    project_ids: list[UUID] = []
    for ref in {r for r in refs if r}:
        if ref in CC_SYSTEM_LABELS:
            labels[ref] = CC_SYSTEM_LABELS[ref]
        elif (pid := _as_uuid(ref)) is not None:
            project_ids.append(pid)
    if project_ids:
        rows = await db.execute(select(Project).where(Project.id.in_(project_ids)))
        for project in rows.scalars():
            closed = not project.is_active or project.closed_at is not None
            labels[str(project.id)] = f"{project.name} (encerrado)" if closed else project.name
    return labels


async def cost_center_by_project_name(db: AsyncSession, names: Iterable[str | None]) -> dict[str, str]:
    """Nome do projeto do Jurídico (sem espaços nas pontas) → ref vinculado no cadastro."""
    keys = {n.strip() for n in names if n and n.strip()}
    if not keys:
        return {}
    rows = await db.execute(
        select(func.btrim(LegalProject.name), LegalProject.cost_center_ref).where(
            func.btrim(LegalProject.name).in_(keys), LegalProject.cost_center_ref.is_not(None)
        )
    )
    return {name: ref for name, ref in rows.all()}


async def person_cost_center_project_id(db: AsyncSession, legal_person_id: UUID | None) -> UUID | None:
    """Projeto do SGC vinculado ao projeto do desligado — o único encerrado aceito na dívida dele."""
    if legal_person_id is None:
        return None
    person = await db.get(LegalPerson, legal_person_id)
    if person is None:
        return None
    ref = (await cost_center_by_project_name(db, [person.project])).get((person.project or "").strip())
    return _as_uuid(ref) if ref else None
