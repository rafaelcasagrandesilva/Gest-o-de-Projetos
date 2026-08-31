"""Schemas do Workspace Jurídico.

Todos os campos monetários são `float | None`: `None` significa "omitido por Dados sensíveis"
(`redact_for("legal_case", ...)`), nunca zero. O frontend renderiza "—" nesse caso.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.legal import (
    LegalCaseStatus,
    LegalCaseType,
    LegalChangeAction,
    LegalEntityType,
)
from app.schemas.common import ORMModel


# ---------------------------------------------------------------------------
# Processo
# ---------------------------------------------------------------------------


class LegalCaseBase(BaseModel):
    case_number: str = Field(min_length=1, max_length=64)
    jusbrasil_url: str | None = None
    status: LegalCaseStatus = LegalCaseStatus.EM_ANDAMENTO
    case_type: LegalCaseType = LegalCaseType.TRABALHISTA
    nature: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, max_length=2)
    court: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=255)
    project: str | None = Field(default=None, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    claimant_name: str | None = Field(default=None, max_length=255)
    defendant_name: str | None = Field(default=None, max_length=255)
    amount_claimed: float | None = None
    amount_considered: float | None = None
    amount_agreed: float | None = None
    amount_paid: float | None = None
    amount_pending: float | None = None
    agreement_terms: str | None = None
    last_movement: str | None = None
    last_movement_date: date | None = None
    hearing_date: date | None = None
    distribution_date: date | None = None
    notes: str | None = None


class LegalCaseCreate(LegalCaseBase):
    person_id: UUID | None = None


class LegalCaseUpdate(BaseModel):
    """PATCH parcial — só os campos enviados são alterados."""

    model_config = ConfigDict(extra="forbid")

    case_number: str | None = Field(default=None, min_length=1, max_length=64)
    jusbrasil_url: str | None = None
    person_id: UUID | None = None
    status: LegalCaseStatus | None = None
    case_type: LegalCaseType | None = None
    nature: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, max_length=2)
    court: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=255)
    project: str | None = Field(default=None, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    claimant_name: str | None = Field(default=None, max_length=255)
    defendant_name: str | None = Field(default=None, max_length=255)
    amount_claimed: float | None = None
    amount_considered: float | None = None
    amount_agreed: float | None = None
    amount_paid: float | None = None
    amount_pending: float | None = None
    agreement_terms: str | None = None
    last_movement: str | None = None
    last_movement_date: date | None = None
    hearing_date: date | None = None
    distribution_date: date | None = None
    notes: str | None = None


class LegalCaseRead(ORMModel, LegalCaseBase):
    id: UUID
    person_id: UUID | None = None
    is_active: bool = True
    # Desnormalizados na resposta (evitam N+1 no frontend): a tabela de Processos mostra
    # nome e CPF da pessoa sem precisar buscar o cadastro.
    person_name: str | None = None
    person_cpf: str | None = None


# ---------------------------------------------------------------------------
# Ex-colaborador
# ---------------------------------------------------------------------------


class LegalPersonBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    cpf: str | None = Field(default=None, max_length=20)
    company: str | None = Field(default=None, max_length=255)
    project: str | None = Field(default=None, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=120)
    admission_date: date | None = None
    termination_date: date | None = None
    severance_amount: float | None = None
    fgts_balance: float | None = None
    notes: str | None = None
    is_active: bool = True


class LegalPersonCreate(LegalPersonBase):
    pass


class LegalPersonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    cpf: str | None = Field(default=None, max_length=20)
    company: str | None = Field(default=None, max_length=255)
    project: str | None = Field(default=None, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=120)
    admission_date: date | None = None
    termination_date: date | None = None
    severance_amount: float | None = None
    fgts_balance: float | None = None
    notes: str | None = None
    is_active: bool | None = None


class LegalPersonRead(ORMModel, LegalPersonBase):
    """Pessoa + agregados DERIVADOS dos seus processos (nunca desnormalizados no banco)."""

    id: UUID
    case_count: int = 0
    total_claimed: float | None = None
    total_considered: float | None = None
    total_agreed: float | None = None
    total_paid: float | None = None
    total_pending: float | None = None


class LegalPersonDetail(LegalPersonRead):
    """Detalhe (modal do ex-colaborador): inclui os processos relacionados."""

    cases: list[LegalCaseRead] = []


# ---------------------------------------------------------------------------
# Indicadores da tela de Processos (KPIs + gráficos), sempre sobre os MESMOS filtros da lista
# ---------------------------------------------------------------------------


class LegalKpis(BaseModel):
    case_count: int = 0
    person_count: int = 0
    total_claimed: float | None = None
    total_considered: float | None = None
    total_agreed: float | None = None
    total_paid: float | None = None
    total_pending: float | None = None


class LegalBucket(BaseModel):
    """Uma barra do gráfico: rótulo + valor somado + quantidade de processos."""

    key: str
    label: str
    value: float | None = None
    count: int = 0


class LegalFacets(BaseModel):
    """Domínios para montar os filtros — derivados do acervo COMPLETO, não do filtrado.

    Assim as opções não somem quando o usuário restringe a seleção (comportamento do Painel de
    Passivo, onde os chips são fixos).
    """

    statuses: list[str] = []
    types: list[str] = []
    ufs: list[str] = []
    companies: list[str] = []
    projects: list[str] = []
    clients: list[str] = []


class LegalOverview(BaseModel):
    """Resposta única dos indicadores: KPIs + séries dos gráficos + domínios dos filtros."""

    kpis: LegalKpis
    by_status: list[LegalBucket] = []
    by_type: list[LegalBucket] = []
    by_uf: list[LegalBucket] = []
    by_company: list[LegalBucket] = []
    by_project: list[LegalBucket] = []
    facets: LegalFacets


# ---------------------------------------------------------------------------
# Administração (Fase 2): catálogos de Empresas/Projetos e histórico de alterações
# ---------------------------------------------------------------------------


class LegalCompanyBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    cnpj: str | None = Field(default=None, max_length=24)
    notes: str | None = None
    is_active: bool = True


class LegalCompanyCreate(LegalCompanyBase):
    pass


class LegalCompanyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    cnpj: str | None = Field(default=None, max_length=24)
    notes: str | None = None


class LegalCompanyRead(ORMModel, LegalCompanyBase):
    id: UUID
    # Quantos processos usam este nome hoje — o admin vê o impacto antes de desativar/renomear.
    case_count: int = 0


class LegalProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    is_active: bool = True


class LegalProjectCreate(LegalProjectBase):
    pass


class LegalProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class LegalProjectRead(ORMModel, LegalProjectBase):
    id: UUID
    case_count: int = 0


class LegalChangeLogRead(ORMModel):
    """Uma alteração manual. `old_value`/`new_value` de campos monetários são omitidos
    (None) para quem não tem `legal.sensitive` — o histórico não pode ser uma porta lateral
    para os valores do passivo."""

    id: UUID
    created_at: datetime
    entity_type: LegalEntityType
    entity_id: UUID
    action: LegalChangeAction
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    changed_by_email: str | None = None


# ---------------------------------------------------------------------------
# Sprint 0 — operação: agenda, timeline e Central de Trabalho
# ---------------------------------------------------------------------------


class LegalEventBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    event_type: str = "OUTRO"
    scheduled_for: datetime | None = None
    due_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    modality: str | None = Field(default=None, max_length=16)
    notes: str | None = None
    case_id: UUID | None = None
    responsible_user_id: UUID | None = None


class LegalEventCreate(LegalEventBase):
    pass


class LegalEventRead(LegalEventBase):
    id: UUID
    status: str
    outcome: str | None = None
    rescheduled_to_id: UUID | None = None
    created_at: datetime
    # Contexto do processo, para a linha da agenda não exigir uma segunda consulta.
    case_number: str | None = None
    claimant: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LegalEventConclude(BaseModel):
    outcome: str | None = None


class LegalEventReschedule(BaseModel):
    new_datetime: datetime
    reason: str | None = None


class LegalTimelineEntryRead(BaseModel):
    id: UUID
    occurred_at: datetime
    entry_type: str
    title: str
    description: str | None = None
    source: str
    is_milestone: bool
    ref_type: str | None = None
    ref_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class LegalNoteCreate(BaseModel):
    """Observação da equipe: vira FATO datado, não campo de texto sobrescrito (B7)."""

    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    occurred_at: datetime | None = None


class LegalExecutiveSummary(BaseModel):
    em_andamento: int = 0
    acordos: int = 0
    valor_acordos: float = 0
    pendente: float = 0
    encerrados: int = 0
