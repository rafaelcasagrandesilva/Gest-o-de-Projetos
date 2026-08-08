from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

# Situações derivadas (nunca gravadas).
SituacaoLiquidacao = str  # "EM_ABERTO" | "PARCIALMENTE_LIQUIDADA" | "VENCIDA" | "LIQUIDADA"
FundingSource = str  # AdvanceFundingSource.value


class SettlementMovementRead(ORMModel):
    id: UUID
    batch_item_id: UUID
    event_id: UUID | None = None
    amount: float
    funding_source: FundingSource
    settled_at: date
    observation: str | None = None
    reversed_at: datetime | None = None
    reversal_reason: str | None = None
    created_at: datetime


class ObligationRead(BaseModel):
    """Obrigação (participação NF × operação) com totais e situação computados no backend."""

    batch_item_id: UUID
    batch_id: UUID
    invoice_id: UUID
    institution_id: UUID | None = None
    institution: str | None = None
    institution_profile: str | None = None
    sgc_number: int
    invoice_number: str | None = None
    client_name: str | None = None
    project_name: str | None = None
    # Totais explícitos — o frontend NUNCA recalcula.
    valor_total: float
    valor_liquidado: float
    valor_residual: float
    situacao: SituacaoLiquidacao
    vencimento: date | None = None
    dias_em_atraso: int = 0
    origens_resumo: str = ""
    movimentacoes: list[SettlementMovementRead] = Field(default_factory=list)


class SettlementMovementInput(BaseModel):
    funding_source: FundingSource
    amount: float = Field(..., gt=0)
    settled_at: date | None = None
    observation: str | None = None


class SettlementCreate(BaseModel):
    """Liquida uma obrigação com 1..N movimentações (parcial/multi-origem)."""

    batch_item_id: UUID
    movements: list[SettlementMovementInput] = Field(..., min_length=1)


# --- Liquidação em Massa / Evento de Liquidação ---------------------------------

class MassSettlementLine(BaseModel):
    """Uma NF (obrigação) e o valor a liquidar dela no evento em massa."""

    batch_item_id: UUID
    amount: float = Field(..., gt=0)


class MassSettlementCreate(BaseModel):
    """Cria UM Evento de Liquidação (pagamento) sobre N NFs, com origem única."""

    funding_source: FundingSource
    payment_date: date | None = None
    observation: str | None = None
    lines: list[MassSettlementLine] = Field(..., min_length=1)


class SettlementEventRead(BaseModel):
    """Evento de Liquidação (dados ESTRUTURADOS; descrição amigável fica no presenter)."""

    id: UUID
    number: int
    code: str
    creation_source: str  # MANUAL | MASS
    status: str  # ACTIVE | PARTIALLY_REVERSED | FULLY_REVERSED
    institution_id: UUID | None = None
    institution: str | None = None
    payment_date: date
    funding_source: FundingSource | None = None
    funding_source_label: str | None = None
    total_amount: float
    invoice_count: int
    nf_numbers: list[str] = Field(default_factory=list)
    created_by_name: str | None = None
    created_at: datetime


class SettlementEventMovementRead(BaseModel):
    id: UUID
    nf_number: str | None = None
    client_name: str | None = None
    amount: float
    funding_source: FundingSource
    funding_source_label: str
    observation: str | None = None
    reversed_at: datetime | None = None


class SettlementEventDetailRead(SettlementEventRead):
    movimentacoes: list[SettlementEventMovementRead] = Field(default_factory=list)


class SettlementEventCreatedRead(BaseModel):
    """Retorno da criação do evento em massa: o evento + obrigações afetadas atualizadas."""

    event: SettlementEventRead
    obligations: list[ObligationRead] = Field(default_factory=list)


class SettlementKpisRead(BaseModel):
    nfs_pendentes: int
    nfs_vencidas: int
    valor_total_vencido: float
    total_liquidado: float
    saldo_repasse: float


class OrigemDistribuicao(BaseModel):
    funding_source: FundingSource
    label: str
    total: float
    pct: float


class ManagementSummaryRead(BaseModel):
    """Indicadores gerenciais — todos computados no backend."""

    valor_ainda_antecipado: float
    valor_vencido: float
    valor_a_vencer_30d: float
    tempo_medio_liquidacao_dias: float | None = None
    liquidado_repasse: float
    liquidado_outras_origens: float
    total_liquidado: float
    distribuicao_origens: list[OrigemDistribuicao] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    date: date
    tipo: str  # ANTECIPADA | VENCEU | LIQUIDACAO
    label: str
    amount: float | None = None
    origem: str | None = None
    estornada: bool = False
    evento_number: int | None = None  # nº do Evento de Liquidação (→ "LQ-…" no frontend)


class TimelineRead(BaseModel):
    batch_item_id: UUID
    situacao: SituacaoLiquidacao
    events: list[TimelineEvent] = Field(default_factory=list)
