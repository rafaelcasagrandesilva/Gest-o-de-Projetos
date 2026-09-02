"""Serviço do Workspace Jurídico — filtros, agregados e CRUD.

Princípio central: **um único conjunto de filtros** (`CaseFilters`) alimenta a lista, os KPIs e os
gráficos. Não existe caminho em que um card mostre um recorte e a tabela outro — é o que faz os
indicadores "reagirem aos filtros" sem divergir. Todos os agregados são calculados no banco, em
tempo real; nada é materializado.

"Valor considerado" (`amount_considered`) é a base padrão: quando dois processos repetem o mesmo
valor (mesma origem contabilizada duas vezes), o duplicado entra como 0 e não infla o passivo.
`basis` permite somar por "valor da causa" — mesma semântica do Painel de Passivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import ColumnElement, Select, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import (
    LegalCase,
    LegalCaseStatus,
    LegalCaseType,
    LegalChangeAction,
    LegalChangeLog,
    LegalCompany,
    LegalEntityType,
    LegalPerson,
    LegalProject,
)
from app.schemas.legal import (
    LegalBucket,
    LegalFacets,
    LegalKpis,
    LegalOverview,
)

# Base de valor dos gráficos e da faixa de valor.
BASIS_CONSIDERED = "considered"
BASIS_CLAIMED = "claimed"

# Rótulos pt-BR do domínio — fonte ÚNICA (API e frontend consomem o mesmo texto).
STATUS_LABELS: dict[str, str] = {
    LegalCaseStatus.EM_ANDAMENTO.value: "Em andamento",
    LegalCaseStatus.COM_DECISAO.value: "Com decisão/sentença",
    LegalCaseStatus.SUSPENSO.value: "Suspenso/Sobrestado",
    LegalCaseStatus.ACORDO.value: "Acordo",
    LegalCaseStatus.ACORDO_FINALIZADO.value: "Acordo finalizado",
    LegalCaseStatus.ENCERRADO.value: "Encerrado/Arquivado",
    LegalCaseStatus.SEM_PROCESSO.value: "Sem processo cadastrado",
}

TYPE_LABELS: dict[str, str] = {
    LegalCaseType.TRABALHISTA.value: "Trabalhista",
    LegalCaseType.CIVEL.value: "Cível",
    LegalCaseType.TRIBUTARIO.value: "Tributário",
    LegalCaseType.OUTRO.value: "Outro",
}

# Ordem canônica dos status (ciclo de vida do processo) — usada nos chips e no gráfico.
STATUS_ORDER: tuple[str, ...] = (
    LegalCaseStatus.EM_ANDAMENTO.value,
    LegalCaseStatus.COM_DECISAO.value,
    LegalCaseStatus.ACORDO.value,
    LegalCaseStatus.ACORDO_FINALIZADO.value,
    LegalCaseStatus.SUSPENSO.value,
    LegalCaseStatus.ENCERRADO.value,
    LegalCaseStatus.SEM_PROCESSO.value,
)


def _f(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)  # type: ignore[arg-type]


# Campos monetários do histórico: `old_value`/`new_value` de uma alteração nestes campos são
# valores do passivo e só saem para quem tem `legal.sensitive`.
MONEY_FIELDS: frozenset[str] = frozenset(
    {
        "amount_claimed",
        "amount_considered",
        "amount_agreed",
        "amount_paid",
        "amount_pending",
        "agreement_terms",
        "severance_amount",
        "fgts_balance",
    }
)


@dataclass
class CaseFilters:
    """Filtros da tela de Processos. Listas vazias = "não filtra por este eixo"."""

    statuses: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    ufs: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    clients: list[str] = field(default_factory=list)
    person_id: UUID | None = None
    value_min: float | None = None
    value_max: float | None = None
    q: str | None = None
    basis: str = BASIS_CONSIDERED
    # Processo desativado sai das telas analíticas E dos indicadores. Só a Administração pede
    # `include_inactive=True` — daí o default False preservar exatamente os números da Fase 1.
    include_inactive: bool = False

    def basis_column(self) -> ColumnElement:
        return (
            LegalCase.amount_claimed
            if self.basis == BASIS_CLAIMED
            else LegalCase.amount_considered
        )


@dataclass
class PersonFilters:
    companies: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    clients: list[str] = field(default_factory=list)
    # None = todos; True = só com processo; False = só sem processo.
    has_cases: bool | None = None
    q: str | None = None
    include_inactive: bool = False


def _as_text(value: object) -> str | None:
    """Serializa um valor de campo para o histórico (texto simples e legível).

    Enum ANTES de str: os enums do módulo herdam de `str`, e `str(LegalCaseStatus.ACORDO)`
    devolveria "LegalCaseStatus.ACORDO" em vez de "ACORDO".
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


class LegalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- Histórico de alterações -----------------------------------------------------------

    def _log(
        self,
        *,
        entity_type: LegalEntityType,
        entity_id: UUID,
        action: LegalChangeAction,
        actor=None,
        field_name: str | None = None,
        old: object = None,
        new: object = None,
    ) -> None:
        """Enfileira UM registro de histórico (o commit é do chamador)."""
        self.session.add(
            LegalChangeLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                field=field_name,
                old_value=_as_text(old),
                new_value=_as_text(new),
                changed_by_id=getattr(actor, "id", None),
                changed_by_email=getattr(actor, "email", None),
            )
        )

    def _log_diff(
        self, *, entity_type: LegalEntityType, row, data: dict, actor=None
    ) -> dict:
        """Compara os campos enviados com o estado atual e registra UM log por campo alterado.

        Devolve só o que realmente mudou — o chamador aplica esse subconjunto, então um PATCH que
        não altera nada não gera histórico nem toca `updated_at`.
        """
        changed: dict = {}
        for key, new_value in data.items():
            if not hasattr(row, key):
                continue
            old_value = getattr(row, key)
            if _as_text(old_value) == _as_text(new_value):
                continue
            changed[key] = new_value
            self._log(
                entity_type=entity_type,
                entity_id=row.id,
                action=LegalChangeAction.UPDATE,
                actor=actor,
                field_name=key,
                old=old_value,
                new=new_value,
            )
        return changed

    async def list_change_logs(
        self, *, entity_type: str | None = None, entity_id: UUID | None = None, limit: int = 200
    ) -> list[LegalChangeLog]:
        stmt = select(LegalChangeLog)
        if entity_type:
            stmt = stmt.where(LegalChangeLog.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(LegalChangeLog.entity_id == entity_id)
        stmt = stmt.order_by(LegalChangeLog.created_at.desc()).limit(min(max(limit, 1), 500))
        return list((await self.session.execute(stmt)).scalars().all())

    # -- Processos ------------------------------------------------------------------------

    @staticmethod
    def _case_conditions(filters: CaseFilters) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if not filters.include_inactive:
            conditions.append(LegalCase.is_active.is_(True))
        if filters.statuses:
            conditions.append(LegalCase.status.in_(filters.statuses))
        if filters.types:
            conditions.append(LegalCase.case_type.in_(filters.types))
        if filters.ufs:
            conditions.append(LegalCase.uf.in_(filters.ufs))
        if filters.companies:
            conditions.append(LegalCase.company.in_(filters.companies))
        if filters.projects:
            conditions.append(LegalCase.project.in_(filters.projects))
        if filters.clients:
            conditions.append(LegalCase.client.in_(filters.clients))
        if filters.person_id is not None:
            conditions.append(LegalCase.person_id == filters.person_id)

        basis = filters.basis_column()
        # Processo sem valor conhecido é tratado como 0 na faixa (não some ao filtrar por mínimo 0).
        if filters.value_min is not None:
            conditions.append(func.coalesce(basis, 0) >= filters.value_min)
        if filters.value_max is not None:
            conditions.append(func.coalesce(basis, 0) <= filters.value_max)

        if filters.q and filters.q.strip():
            term = f"%{filters.q.strip()}%"
            conditions.append(
                or_(
                    LegalCase.case_number.ilike(term),
                    LegalCase.claimant_name.ilike(term),
                    LegalCase.defendant_name.ilike(term),
                    LegalCase.company.ilike(term),
                    LegalCase.project.ilike(term),
                    LegalCase.client.ilike(term),
                    LegalCase.court.ilike(term),
                    LegalCase.person.has(LegalPerson.full_name.ilike(term)),
                    LegalCase.person.has(LegalPerson.cpf.ilike(term)),
                )
            )
        return conditions

    def _filtered_cases(self, filters: CaseFilters) -> Select:
        stmt = select(LegalCase)
        for condition in self._case_conditions(filters):
            stmt = stmt.where(condition)
        return stmt

    async def list_cases(self, filters: CaseFilters) -> list[LegalCase]:
        stmt = self._filtered_cases(filters).order_by(
            func.coalesce(filters.basis_column(), 0).desc(), LegalCase.case_number
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def get_case(self, case_id: UUID) -> LegalCase | None:
        return await self.session.get(LegalCase, case_id)

    async def create_case(self, data: dict, *, actor=None) -> LegalCase:
        row = LegalCase(**data)
        self.session.add(row)
        await self.session.flush()
        self._log(
            entity_type=LegalEntityType.CASE,
            entity_id=row.id,
            action=LegalChangeAction.CREATE,
            actor=actor,
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_case(self, case_id: UUID, data: dict, *, actor=None) -> LegalCase:
        row = await self.get_case(case_id)
        if row is None:
            raise LookupError("Processo não encontrado.")
        changed = self._log_diff(
            entity_type=LegalEntityType.CASE, row=row, data=data, actor=actor
        )
        for key, value in changed.items():
            setattr(row, key, value)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_case_active(self, case_id: UUID, *, active: bool, actor=None) -> LegalCase:
        """Baixa LÓGICA — nunca DELETE físico (o histórico do processo é preservado)."""
        row = await self.get_case(case_id)
        if row is None:
            raise LookupError("Processo não encontrado.")
        if bool(row.is_active) != active:
            row.is_active = active
            self._log(
                entity_type=LegalEntityType.CASE,
                entity_id=row.id,
                action=LegalChangeAction.RESTORE if active else LegalChangeAction.DEACTIVATE,
                actor=actor,
            )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    # -- Indicadores (mesmos filtros da lista) --------------------------------------------

    async def _bucket(
        self, filters: CaseFilters, column: ColumnElement, labels: dict[str, str] | None
    ) -> list[LegalBucket]:
        basis = filters.basis_column()
        stmt = select(
            column.label("key"),
            func.coalesce(func.sum(func.coalesce(basis, 0)), 0).label("value"),
            func.count().label("count"),
        )
        for condition in self._case_conditions(filters):
            stmt = stmt.where(condition)
        stmt = stmt.group_by(column).order_by(func.sum(func.coalesce(basis, 0)).desc())

        buckets: list[LegalBucket] = []
        for key, value, count in (await self.session.execute(stmt)).all():
            raw = getattr(key, "value", key)  # Enum nativo → string
            raw = "" if raw is None else str(raw)
            buckets.append(
                LegalBucket(
                    key=raw,
                    label=(labels or {}).get(raw) or raw or "—",
                    value=_f(value) or 0.0,
                    count=int(count or 0),
                )
            )
        if labels is STATUS_LABELS:
            order = {code: i for i, code in enumerate(STATUS_ORDER)}
            buckets.sort(key=lambda b: order.get(b.key, len(order)))
        return buckets

    async def _kpis(self, filters: CaseFilters) -> LegalKpis:
        stmt = select(
            func.count().label("case_count"),
            func.count(distinct(LegalCase.person_id)).label("person_count"),
            func.coalesce(func.sum(func.coalesce(LegalCase.amount_claimed, 0)), 0),
            func.coalesce(func.sum(func.coalesce(LegalCase.amount_considered, 0)), 0),
            func.coalesce(func.sum(func.coalesce(LegalCase.amount_agreed, 0)), 0),
            func.coalesce(func.sum(func.coalesce(LegalCase.amount_paid, 0)), 0),
            func.coalesce(func.sum(func.coalesce(LegalCase.amount_pending, 0)), 0),
        )
        for condition in self._case_conditions(filters):
            stmt = stmt.where(condition)
        row = (await self.session.execute(stmt)).one()
        return LegalKpis(
            case_count=int(row[0] or 0),
            person_count=int(row[1] or 0),
            total_claimed=_f(row[2]) or 0.0,
            total_considered=_f(row[3]) or 0.0,
            total_agreed=_f(row[4]) or 0.0,
            total_paid=_f(row[5]) or 0.0,
            total_pending=_f(row[6]) or 0.0,
        )

    async def _catalog_names(self, model) -> list[str]:
        stmt = select(model.name).where(model.is_active.is_(True)).order_by(model.name)
        return [str(v) for (v,) in (await self.session.execute(stmt)).all() if str(v).strip()]

    async def _facets(self) -> LegalFacets:
        """Domínios dos filtros a partir do acervo COMPLETO (opções não somem ao filtrar).

        Empresa/Projeto = catálogo ATIVO (Administração) ∪ valores JÁ em uso nos processos. A união
        é o que permite cadastrar uma empresa nova e vê-la no filtro antes do primeiro processo,
        sem que um valor legado — ainda não cadastrado — desapareça da tela.
        """

        async def values_of(column: ColumnElement) -> list[str]:
            stmt = select(distinct(column)).where(column.isnot(None)).order_by(column)
            return [str(v) for (v,) in (await self.session.execute(stmt)).all() if str(v).strip()]

        async def merged(column: ColumnElement, model) -> list[str]:
            return sorted(set(await values_of(column)) | set(await self._catalog_names(model)))

        used_statuses = {
            str(getattr(v, "value", v))
            for (v,) in (await self.session.execute(select(distinct(LegalCase.status)))).all()
        }
        used_types = {
            str(getattr(v, "value", v))
            for (v,) in (await self.session.execute(select(distinct(LegalCase.case_type)))).all()
        }
        return LegalFacets(
            statuses=[s for s in STATUS_ORDER if s in used_statuses],
            types=[t for t in TYPE_LABELS if t in used_types],
            ufs=await values_of(LegalCase.uf),
            companies=await merged(LegalCase.company, LegalCompany),
            projects=await merged(LegalCase.project, LegalProject),
            clients=await values_of(LegalCase.client),
        )

    async def overview(self, filters: CaseFilters) -> LegalOverview:
        return LegalOverview(
            kpis=await self._kpis(filters),
            by_status=await self._bucket(filters, LegalCase.status, STATUS_LABELS),
            by_type=await self._bucket(filters, LegalCase.case_type, TYPE_LABELS),
            by_uf=await self._bucket(filters, LegalCase.uf, None),
            by_company=await self._bucket(filters, LegalCase.company, None),
            by_project=await self._bucket(filters, LegalCase.project, None),
            facets=await self._facets(),
        )

    # -- Ex-colaboradores -----------------------------------------------------------------

    @staticmethod
    def _person_aggregates() -> Select:
        """Subquery com os agregados de processos por pessoa (quantidade e somas)."""
        return (
            select(
                LegalCase.person_id.label("person_id"),
                func.count().label("case_count"),
                func.coalesce(func.sum(func.coalesce(LegalCase.amount_claimed, 0)), 0).label("claimed"),
                func.coalesce(func.sum(func.coalesce(LegalCase.amount_considered, 0)), 0).label("considered"),
                func.coalesce(func.sum(func.coalesce(LegalCase.amount_agreed, 0)), 0).label("agreed"),
                func.coalesce(func.sum(func.coalesce(LegalCase.amount_paid, 0)), 0).label("paid"),
                func.coalesce(func.sum(func.coalesce(LegalCase.amount_pending, 0)), 0).label("pending"),
            )
            .where(LegalCase.person_id.isnot(None))
            .group_by(LegalCase.person_id)
            .subquery()
        )

    async def search_persons_reference(self, *, term: str, limit: int = 20) -> list[LegalPerson]:
        """Busca enxuta por nome, para combos de outros módulos (ver `/persons/search`).

        Só pessoas ATIVAS no cadastro: uma pessoa desativada foi removida da relação de
        desligados e não deve reaparecer como opção num vínculo novo.
        """
        stmt = (
            select(LegalPerson)
            .where(LegalPerson.is_active.is_(True), LegalPerson.full_name.ilike(f"%{term}%"))
            .order_by(LegalPerson.full_name)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_persons(self, filters: PersonFilters) -> list[tuple[LegalPerson, dict]]:
        """Pessoas + agregados derivados dos seus processos (0 quando não tem processo)."""
        agg = self._person_aggregates()
        stmt = select(
            LegalPerson,
            func.coalesce(agg.c.case_count, 0),
            func.coalesce(agg.c.claimed, 0),
            func.coalesce(agg.c.considered, 0),
            func.coalesce(agg.c.agreed, 0),
            func.coalesce(agg.c.paid, 0),
            func.coalesce(agg.c.pending, 0),
        ).outerjoin(agg, agg.c.person_id == LegalPerson.id)

        if not filters.include_inactive:
            stmt = stmt.where(LegalPerson.is_active.is_(True))
        if filters.companies:
            stmt = stmt.where(LegalPerson.company.in_(filters.companies))
        if filters.projects:
            stmt = stmt.where(LegalPerson.project.in_(filters.projects))
        if filters.clients:
            stmt = stmt.where(LegalPerson.client.in_(filters.clients))
        if filters.has_cases is True:
            stmt = stmt.where(func.coalesce(agg.c.case_count, 0) > 0)
        elif filters.has_cases is False:
            stmt = stmt.where(func.coalesce(agg.c.case_count, 0) == 0)
        if filters.q and filters.q.strip():
            term = f"%{filters.q.strip()}%"
            stmt = stmt.where(
                or_(
                    LegalPerson.full_name.ilike(term),
                    LegalPerson.cpf.ilike(term),
                    LegalPerson.company.ilike(term),
                    LegalPerson.project.ilike(term),
                    LegalPerson.client.ilike(term),
                )
            )

        stmt = stmt.order_by(LegalPerson.full_name)
        rows = (await self.session.execute(stmt)).unique().all()
        return [
            (
                person,
                {
                    "case_count": int(count or 0),
                    "total_claimed": _f(claimed) or 0.0,
                    "total_considered": _f(considered) or 0.0,
                    "total_agreed": _f(agreed) or 0.0,
                    "total_paid": _f(paid) or 0.0,
                    "total_pending": _f(pending) or 0.0,
                },
            )
            for person, count, claimed, considered, agreed, paid, pending in rows
        ]

    async def person_facets(self) -> LegalFacets:
        """Domínios dos filtros da tela de Ex-colaboradores (acervo completo de pessoas)."""

        async def values_of(column: ColumnElement) -> list[str]:
            stmt = select(distinct(column)).where(column.isnot(None)).order_by(column)
            return [str(v) for (v,) in (await self.session.execute(stmt)).all() if str(v).strip()]

        return LegalFacets(
            companies=sorted(
                set(await values_of(LegalPerson.company))
                | set(await self._catalog_names(LegalCompany))
            ),
            projects=sorted(
                set(await values_of(LegalPerson.project))
                | set(await self._catalog_names(LegalProject))
            ),
            clients=await values_of(LegalPerson.client),
        )

    async def get_person(self, person_id: UUID) -> tuple[LegalPerson, dict] | None:
        person = await self.session.get(LegalPerson, person_id)
        if person is None:
            return None
        cases = person.cases or []
        totals = {
            "case_count": len(cases),
            "total_claimed": sum(_f(c.amount_claimed) or 0.0 for c in cases),
            "total_considered": sum(_f(c.amount_considered) or 0.0 for c in cases),
            "total_agreed": sum(_f(c.amount_agreed) or 0.0 for c in cases),
            "total_paid": sum(_f(c.amount_paid) or 0.0 for c in cases),
            "total_pending": sum(_f(c.amount_pending) or 0.0 for c in cases),
        }
        return person, totals

    async def create_person(self, data: dict, *, actor=None) -> LegalPerson:
        row = LegalPerson(**data)
        self.session.add(row)
        await self.session.flush()
        self._log(
            entity_type=LegalEntityType.PERSON,
            entity_id=row.id,
            action=LegalChangeAction.CREATE,
            actor=actor,
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_person(self, person_id: UUID, data: dict, *, actor=None) -> LegalPerson:
        row = await self.session.get(LegalPerson, person_id)
        if row is None:
            raise LookupError("Pessoa não encontrada.")
        changed = self._log_diff(
            entity_type=LegalEntityType.PERSON, row=row, data=data, actor=actor
        )
        for key, value in changed.items():
            setattr(row, key, value)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_person_active(self, person_id: UUID, *, active: bool, actor=None) -> LegalPerson:
        """Baixa LÓGICA. Os processos vinculados NÃO são desativados junto — desativar uma pessoa
        cadastrada por engano não pode fazer processos reais sumirem do passivo."""
        row = await self.session.get(LegalPerson, person_id)
        if row is None:
            raise LookupError("Pessoa não encontrada.")
        if bool(row.is_active) != active:
            row.is_active = active
            self._log(
                entity_type=LegalEntityType.PERSON,
                entity_id=row.id,
                action=LegalChangeAction.RESTORE if active else LegalChangeAction.DEACTIVATE,
                actor=actor,
            )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    # -- Catálogos (Empresas / Projetos) — vocabulário dos filtros -------------------------

    async def _usage_by_name(self, column: ColumnElement) -> dict[str, int]:
        """Quantos processos ATIVOS usam cada valor de texto (impacto de desativar/renomear)."""
        stmt = (
            select(column, func.count())
            .where(column.isnot(None), LegalCase.is_active.is_(True))
            .group_by(column)
        )
        return {str(name): int(count) for name, count in (await self.session.execute(stmt)).all()}

    async def list_companies(
        self, *, include_inactive: bool = False
    ) -> list[tuple[LegalCompany, int]]:
        stmt = select(LegalCompany)
        if not include_inactive:
            stmt = stmt.where(LegalCompany.is_active.is_(True))
        rows = (await self.session.execute(stmt.order_by(LegalCompany.name))).scalars().all()
        usage = await self._usage_by_name(LegalCase.company)
        return [(row, usage.get(row.name, 0)) for row in rows]

    async def list_projects(
        self, *, include_inactive: bool = False
    ) -> list[tuple[LegalProject, int]]:
        stmt = select(LegalProject)
        if not include_inactive:
            stmt = stmt.where(LegalProject.is_active.is_(True))
        rows = (await self.session.execute(stmt.order_by(LegalProject.name))).scalars().all()
        usage = await self._usage_by_name(LegalCase.project)
        return [(row, usage.get(row.name, 0)) for row in rows]

    async def create_catalog(self, kind: str, data: dict, *, actor=None):
        model, entity = self._catalog(kind)
        row = model(**data)
        self.session.add(row)
        await self.session.flush()
        self._log(
            entity_type=entity, entity_id=row.id, action=LegalChangeAction.CREATE, actor=actor
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_catalog(self, kind: str, row_id: UUID, data: dict, *, actor=None):
        model, entity = self._catalog(kind)
        row = await self.session.get(model, row_id)
        if row is None:
            raise LookupError("Registro não encontrado.")
        changed = self._log_diff(entity_type=entity, row=row, data=data, actor=actor)
        for key, value in changed.items():
            setattr(row, key, value)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_catalog_active(self, kind: str, row_id: UUID, *, active: bool, actor=None):
        model, entity = self._catalog(kind)
        row = await self.session.get(model, row_id)
        if row is None:
            raise LookupError("Registro não encontrado.")
        if bool(row.is_active) != active:
            row.is_active = active
            self._log(
                entity_type=entity,
                entity_id=row.id,
                action=LegalChangeAction.RESTORE if active else LegalChangeAction.DEACTIVATE,
                actor=actor,
            )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    @staticmethod
    def _catalog(kind: str):
        if kind == "companies":
            return LegalCompany, LegalEntityType.COMPANY
        if kind == "projects":
            return LegalProject, LegalEntityType.PROJECT
        raise LookupError(f"Catálogo desconhecido: {kind}")
