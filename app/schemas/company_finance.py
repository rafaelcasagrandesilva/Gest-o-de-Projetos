from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

TipoFinanceiro = Literal["endividamento", "custo_fixo"]
RenegotiationType = Literal["UNIQUE", "INSTALLMENTS"]
CompanyFinancialItemType = Literal["MANUAL", "COLABORADOR_MATRIZ"]


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
    category: str | None = Field(None, max_length=120)
    cost_center: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=4000)
    recurrence: str | None = Field(None, max_length=32)
    item_type: CompanyFinancialItemType = "MANUAL"
    employee_id: UUID | None = None
    percentual: float | None = Field(default=None, ge=0, le=100)

    has_legal_process: bool = False
    has_renegotiation: bool = False
    renegotiated_amount: float | None = Field(None, ge=0)
    renegotiation_type: RenegotiationType | None = None
    installment_count: int | None = Field(None, ge=1)
    installment_value: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_renegotiation(self) -> "CompanyFinancialItemCreate":
        if self.has_renegotiation:
            if self.renegotiated_amount is None:
                raise ValueError("renegotiated_amount é obrigatório quando has_renegotiation=true")
            if self.renegotiation_type is None:
                raise ValueError("renegotiation_type é obrigatório quando has_renegotiation=true")
            if self.renegotiation_type == "INSTALLMENTS":
                if self.installment_count is None:
                    raise ValueError("installment_count é obrigatório quando renegotiation_type=INSTALLMENTS")
                if self.installment_value is None:
                    raise ValueError("installment_value é obrigatório quando renegotiation_type=INSTALLMENTS")
                total_calc = round(float(self.installment_count) * float(self.installment_value), 2)
                if round(float(self.renegotiated_amount), 2) != total_calc:
                    raise ValueError("renegotiated_amount deve ser igual a installment_count * installment_value")
        return self

    @model_validator(mode="after")
    def validate_matrix_collaborator(self) -> "CompanyFinancialItemCreate":
        if self.tipo != "custo_fixo":
            return self
        if self.item_type == "COLABORADOR_MATRIZ":
            if self.employee_id is None:
                raise ValueError("employee_id é obrigatório para item COLABORADOR_MATRIZ.")
            if self.percentual is None:
                raise ValueError("percentual é obrigatório para item COLABORADOR_MATRIZ.")
        else:
            self.employee_id = None
            self.percentual = None
        return self


class CompanyFinancialItemUpdate(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=255)
    valor_referencia: float | None = Field(None, ge=0)
    category: str | None = Field(None, max_length=120)
    cost_center: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=4000)
    recurrence: str | None = Field(None, max_length=32)
    item_type: CompanyFinancialItemType | None = None
    employee_id: UUID | None = None
    percentual: float | None = Field(default=None, ge=0, le=100)

    has_legal_process: bool | None = None
    has_renegotiation: bool | None = None
    renegotiated_amount: float | None = Field(None, ge=0)
    renegotiation_type: RenegotiationType | None = None
    installment_count: int | None = Field(None, ge=1)
    installment_value: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_renegotiation(self) -> "CompanyFinancialItemUpdate":
        touch = any(
            v is not None
            for v in (
                self.has_renegotiation,
                self.renegotiated_amount,
                self.renegotiation_type,
                self.installment_count,
                self.installment_value,
            )
        )
        if not touch:
            return self

        has = bool(self.has_renegotiation) if self.has_renegotiation is not None else None
        if has is False:
            return self

        if has is None and (
            self.renegotiated_amount is not None
            or self.renegotiation_type is not None
            or self.installment_count is not None
            or self.installment_value is not None
        ):
            has = True

        if has:
            if self.renegotiated_amount is None:
                raise ValueError("renegotiated_amount é obrigatório quando has_renegotiation=true")
            if self.renegotiation_type is None:
                raise ValueError("renegotiation_type é obrigatório quando has_renegotiation=true")
            if self.renegotiation_type == "INSTALLMENTS":
                if self.installment_count is None:
                    raise ValueError("installment_count é obrigatório quando renegotiation_type=INSTALLMENTS")
                if self.installment_value is None:
                    raise ValueError("installment_value é obrigatório quando renegotiation_type=INSTALLMENTS")
                total_calc = round(float(self.installment_count) * float(self.installment_value), 2)
                if round(float(self.renegotiated_amount), 2) != total_calc:
                    raise ValueError("renegotiated_amount deve ser igual a installment_count * installment_value")
        return self

    @model_validator(mode="after")
    def validate_matrix_collaborator(self) -> "CompanyFinancialItemUpdate":
        # Validação parcial: só se o payload tocar no assunto.
        touch = any(v is not None for v in (self.item_type, self.employee_id, self.percentual))
        if not touch:
            return self
        eff_type = self.item_type or ("COLABORADOR_MATRIZ" if self.employee_id is not None else None)
        if eff_type == "COLABORADOR_MATRIZ":
            if self.employee_id is None:
                raise ValueError("employee_id é obrigatório para item COLABORADOR_MATRIZ.")
            if self.percentual is None:
                raise ValueError("percentual é obrigatório para item COLABORADOR_MATRIZ.")
        return self


class CompanyFinancialItemRead(BaseModel):
    id: UUID
    tipo: str
    item_type: CompanyFinancialItemType | None = None
    employee_id: UUID | None = None
    employee_name: str | None = None
    employee_employment_type: str | None = None
    percentual: float | None = None
    nome: str
    valor_referencia: float
    category: str | None = None
    cost_center: str | None = None
    description: str | None = None
    recurrence: str | None = None
    has_legal_process: bool = False
    has_renegotiation: bool = False
    renegotiated_amount: float | None = None
    renegotiation_type: RenegotiationType | None = None
    installment_count: int | None = None
    installment_value: float | None = None
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
