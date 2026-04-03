from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

TipoFinanceiro = Literal["endividamento", "custo_fixo"]


def _money(v: object) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


class PagamentoMes(BaseModel):
    mes: str = Field(..., description="YYYY-MM")
    valor: float = Field(..., ge=0)

    @field_validator("mes")
    @classmethod
    def mes_format(cls, v: str) -> str:
        parts = v.strip().split("-")
        if len(parts) != 2:
            raise ValueError("mes deve ser YYYY-MM")
        y, m = int(parts[0]), int(parts[1])
        if not (1 <= m <= 12):
            raise ValueError("mês inválido")
        date(y, m, 1)
        return f"{y:04d}-{m:02d}"


class CompanyFinancialItemCreate(BaseModel):
    tipo: TipoFinanceiro
    nome: str = Field(..., min_length=1, max_length=255)
    valor_referencia: float = Field(..., ge=0)


class CompanyFinancialItemUpdate(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=255)
    valor_referencia: float | None = Field(None, ge=0)


class CompanyFinancialItemRead(BaseModel):
    id: UUID
    tipo: str
    nome: str
    valor_referencia: float
    pagamentos: list[PagamentoMes]
    total_pago: float
    pago_mes: float = 0
    restante: float | None = None
    progresso: float
    status: str | None = None
    progresso_mes: float | None = None

    model_config = {"from_attributes": True}


class PagamentosReplace(BaseModel):
    pagamentos: list[PagamentoMes] = Field(default_factory=list)


class KpiEndividamentoRead(BaseModel):
    total_endividamento: float
    total_pago_mes: float
    saldo_restante: float
    quantidade_itens: int


class KpiCustosFixosRead(BaseModel):
    total_esperado_mes: float
    total_pago_mes: float
    quantidade_itens: int


class ChartPoint(BaseModel):
    mes: str
    pagamentos_mes: float
    saldo_restante_total: float | None = None


class ChartSeriesRead(BaseModel):
    points: list[ChartPoint]
