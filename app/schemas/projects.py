from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from app.schemas.common import UUIDTimestampRead

ProjectDocumentCategory = Literal[
    "CONTRATO", "ADITIVO", "CRONOGRAMA", "ART", "MEMORIAL", "LICENCA", "OUTRO"
]


def _add_months(start: date, months: int) -> date:
    """Soma `months` meses a uma data (ajustando o dia ao último dia do mês, se preciso)."""
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _parse_months(value: object) -> int | None:
    """Extrai o nº de meses de um texto (ex.: '12', '12 meses'). None se não houver dígitos."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return int(digits) if digits else None


class ProjectContractAdditiveRead(UUIDTimestampRead):
    project_id: UUID
    additive_date: date | None = None
    additive_value: float | None = None
    additive_duration: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def additive_end_date(self) -> date | None:
        """Data final derivada do aditivo: data do aditivo + prazo adicional (meses)."""
        months = _parse_months(self.additive_duration)
        if self.additive_date is None or months is None:
            return None
        return _add_months(self.additive_date, months)


class ProjectContractAdditiveCreate(BaseModel):
    additive_date: date | None = None
    additive_value: float | None = Field(default=None, ge=0)
    additive_duration: str | None = Field(default=None, max_length=120)


class ProjectContractAdditiveUpdate(BaseModel):
    additive_date: date | None = None
    additive_value: float | None = Field(default=None, ge=0)
    additive_duration: str | None = Field(default=None, max_length=120)


class ProjectDocumentRead(UUIDTimestampRead):
    project_id: UUID
    category: ProjectDocumentCategory
    title: str
    original_filename: str
    uploaded_by: UUID | None = None
    uploaded_by_name: str | None = None
    uploaded_at: datetime
    download_url: str | None = None


class ProjectRead(UUIDTimestampRead):
    name: str
    code: str | None = None
    description: str | None = None
    cost_center: str | None = None
    # Dados contratuais (cadastrais).
    contract_number: str | None = None
    contract_value: float | None = None
    contract_start_date: date | None = None
    # Prazo total em meses.
    contract_duration: int | None = None
    buyer_name: str | None = None
    buyer_phone: str | None = None
    buyer_email: str | None = None
    manager_name: str | None = None
    manager_phone: str | None = None
    manager_email: str | None = None
    is_active: bool = True
    closed_at: datetime | None = None
    deleted_at: datetime | None = None
    # Soma dos prazos adicionais (meses) de todos os aditivos — injetada pelo router.
    # Base do cálculo da "Vigência atual" (derivada; não armazenada no banco).
    additive_months_total: int = 0
    # Consumo do contrato (derivado; injetado pelo router). `invoiced_total` conta SOMENTE NF
    # faturada e não cancelada — pré-faturada fica de fora por regra do negócio.
    # Opcionais porque são valores financeiros: sem Dados Sensíveis, a redação os anula.
    additive_value_total: float | None = 0
    invoiced_total: float | None = 0

    # Os três campos abaixo são DERIVADOS dos crus acima. A redação de Dados Sensíveis zera
    # apenas campos declarados — um campo calculado não é alcançado por ela. Por isso cada um
    # verifica se a base foi redigida (`None`) e, nesse caso, também devolve `None`: sem essa
    # checagem, quem não tem permissão veria "0%" em vez de "—".

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contract_total_value(self) -> float | None:
        """Valor do contrato somado aos aditivos — a base do consumo."""
        if self.contract_value is None or self.additive_value_total is None:
            return None
        return float(self.contract_value) + float(self.additive_value_total)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contract_balance(self) -> float | None:
        """Saldo ainda não faturado. Negativo significa contrato estourado."""
        total = self.contract_total_value
        if total is None or self.invoiced_total is None:
            return None
        return total - float(self.invoiced_total)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contract_consumed_pct(self) -> float | None:
        """Percentual do contrato já faturado. `None` quando não há valor de contrato — a tela
        mostra "não informado" em vez de um número inventado (M13)."""
        total = self.contract_total_value
        if not total or self.invoiced_total is None:
            return None
        return round(float(self.invoiced_total) / total * 100, 1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contract_end_date(self) -> date | None:
        """Data final ORIGINAL derivada: início + prazo (meses). Sem aditivos."""
        if self.contract_start_date is None or self.contract_duration is None:
            return None
        return _add_months(self.contract_start_date, int(self.contract_duration))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def current_validity_date(self) -> date | None:
        """Vigência atual derivada: início + prazo original + Σ prazos dos aditivos (meses)."""
        if self.contract_start_date is None or self.contract_duration is None:
            return None
        return _add_months(
            self.contract_start_date, int(self.contract_duration) + int(self.additive_months_total or 0)
        )


class ProjectDetailRead(ProjectRead):
    """Detalhe do projeto com os aditivos contratuais (usado no modal Detalhes)."""

    additives: list[ProjectContractAdditiveRead] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    cost_center: str | None = Field(default=None, max_length=255)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    cost_center: str | None = Field(default=None, max_length=255)
    # Dados contratuais (todos opcionais; edição pelo modal Detalhes).
    contract_number: str | None = Field(default=None, max_length=120)
    contract_value: float | None = Field(default=None, ge=0)
    contract_start_date: date | None = None
    contract_duration: int | None = Field(default=None, ge=0)
    buyer_name: str | None = Field(default=None, max_length=255)
    buyer_phone: str | None = Field(default=None, max_length=50)
    buyer_email: str | None = Field(default=None, max_length=255)
    manager_name: str | None = Field(default=None, max_length=255)
    manager_phone: str | None = Field(default=None, max_length=50)
    manager_email: str | None = Field(default=None, max_length=255)
