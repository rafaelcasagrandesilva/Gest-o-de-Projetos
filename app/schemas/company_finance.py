from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

TipoFinanceiro = Literal["endividamento", "custo_fixo"]
RenegotiationType = Literal["UNIQUE", "INSTALLMENTS"]
CompanyFinancialItemType = Literal["MANUAL", "COLABORADOR_MATRIZ"]
CompanyFinancialCostCenterSystem = Literal["ADMINISTRATIVO", "FINANCEIRO"]


def _money(v: object) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


class PagamentoMes(BaseModel):
    mes: str = Field(..., description="YYYY-MM")
    valor: float | None = Field(default=None, ge=0)  # Optional para redação (grade mensal)
    # Quantidade de LANÇAMENTOS que compõem o valor do mês (soma). 1 no caso comum; >1 quando
    # a competência tem múltiplos lançamentos (detalhe no modal). Somente leitura.
    count: int | None = None

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
    # Nome opcional: em Endividamento é composto automaticamente pelo serviço a partir de
    # colaborador + descrição. Em Custo Fixo continua obrigatório (validado abaixo).
    nome: str | None = Field(None, max_length=255)
    # Descrição própria do item (identificador da dívida em Endividamento).
    item_description: str | None = Field(None, max_length=255)
    valor_referencia: float = Field(..., ge=0)
    category: str | None = Field(None, max_length=120)
    cost_center_ref: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ADMINISTRATIVO, FINANCEIRO ou UUID do projeto ativo.",
    )
    description: str | None = Field(None, max_length=4000)
    recurrence: str | None = Field(None, max_length=32)
    item_type: CompanyFinancialItemType = "MANUAL"
    employee_id: UUID | None = None
    legal_person_id: UUID | None = None
    percentual: float | None = Field(default=None, ge=0, le=100)
    is_monthly_required: bool = False
    # Ciclo de vida — início obrigatório em novos cadastros; encerramento opcional.
    is_active: bool = True
    start_date: date = Field(..., description="Data de início do custo/endividamento.")
    end_date: date | None = None

    has_legal_process: bool = False
    has_renegotiation: bool = False
    renegotiated_amount: float | None = Field(None, ge=0)
    renegotiation_type: RenegotiationType | None = None
    installment_count: int | None = Field(None, ge=1)
    installment_value: float | None = Field(None, gt=0)
    renegotiation_agreement_date: date | None = None
    renegotiation_first_payment_date: date | None = None
    renegotiation_due_day: int | None = Field(None, ge=1, le=31)
    # Modo 2: Cronograma Financeiro Personalizado. Quando true, o cronograma (lançamentos) é a
    # fonte oficial da dívida; NÃO exige parcelas iguais (installment_count/value). O fechamento
    # (Σ cronograma == renegociado) é validado ao gravar o cronograma, não aqui.
    uses_custom_schedule: bool = False

    @model_validator(mode="after")
    def validate_renegotiation(self) -> "CompanyFinancialItemCreate":
        if self.has_renegotiation:
            if self.renegotiated_amount is None:
                raise ValueError("renegotiated_amount é obrigatório quando has_renegotiation=true")
            # Renegociação válida exige valor > 0 (0 não faz sentido financeiro; base da dívida).
            if float(self.renegotiated_amount) <= 0:
                raise ValueError("renegotiated_amount deve ser maior que zero quando has_renegotiation=true")
            if self.renegotiation_type is None:
                raise ValueError("renegotiation_type é obrigatório quando has_renegotiation=true")
            # Modo 2 (cronograma): relaxa a igualdade de parcelas fixas — o cronograma pode ter
            # valores distintos por parcela; o fechamento é validado ao gravar o cronograma.
            if self.renegotiation_type == "INSTALLMENTS" and not self.uses_custom_schedule:
                if self.installment_count is None:
                    raise ValueError("installment_count é obrigatório quando renegotiation_type=INSTALLMENTS")
                if self.installment_value is None:
                    raise ValueError("installment_value é obrigatório quando renegotiation_type=INSTALLMENTS")
                total_calc = round(float(self.installment_count) * float(self.installment_value), 2)
                if round(float(self.renegotiated_amount), 2) != total_calc:
                    raise ValueError("renegotiated_amount deve ser igual a installment_count * installment_value")
        elif self.uses_custom_schedule:
            raise ValueError("uses_custom_schedule exige has_renegotiation=true")
        return self

    @model_validator(mode="after")
    def validate_matrix_collaborator(self) -> "CompanyFinancialItemCreate":
        if self.tipo != "custo_fixo":
            return self
        if not (self.nome and self.nome.strip()):
            raise ValueError("nome é obrigatório.")
        if self.item_type == "COLABORADOR_MATRIZ":
            if self.employee_id is None:
                raise ValueError("employee_id é obrigatório para item COLABORADOR_MATRIZ.")
            if self.percentual is None:
                raise ValueError("percentual é obrigatório para item COLABORADOR_MATRIZ.")
        else:
            self.employee_id = None
            self.percentual = None
        self.legal_person_id = None  # vínculo exclusivo de Endividamento
        return self

    @model_validator(mode="after")
    def validate_debt_fields(self) -> "CompanyFinancialItemCreate":
        # Endividamento segue o mesmo padrão do Custos Fixos: Tipo Manual (Nome) ou
        # Colaborador (colaborador vinculado — só identificação, sem matriz/percentual). A
        # descrição passa a ser complementar (opcional). O `nome` é resolvido no serviço;
        # nunca usa COLABORADOR_MATRIZ. Exige ao menos um identificador.
        if self.tipo != "endividamento":
            return self
        self.item_type = "MANUAL"
        self.percentual = None
        # Colaborador (cadastro operacional) e Desligado (cadastro do Jurídico) são cadastros
        # distintos e o item aponta para UM. Aceitar os dois deixaria o nome ambíguo.
        if self.employee_id is not None and self.legal_person_id is not None:
            raise ValueError("Selecione um Colaborador OU um Desligado, não os dois.")
        has_nome = bool(self.nome and self.nome.strip())
        has_desc = bool(self.item_description and self.item_description.strip())
        if self.employee_id is None and self.legal_person_id is None and not has_nome and not has_desc:
            raise ValueError("Informe o Nome (Manual), um Colaborador ou um Desligado.")
        return self


class CompanyFinancialItemUpdate(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=255)
    item_description: str | None = Field(None, max_length=255)
    valor_referencia: float | None = Field(None, ge=0)
    category: str | None = Field(None, max_length=120)
    cost_center_ref: str | None = Field(
        None,
        min_length=1,
        max_length=64,
        description="ADMINISTRATIVO, FINANCEIRO ou UUID do projeto.",
    )
    description: str | None = Field(None, max_length=4000)
    recurrence: str | None = Field(None, max_length=32)
    item_type: CompanyFinancialItemType | None = None
    employee_id: UUID | None = None
    legal_person_id: UUID | None = None
    percentual: float | None = Field(default=None, ge=0, le=100)
    is_monthly_required: bool | None = None
    # Ciclo de vida — invariante (inativo exige end_date) aplicada no serviço.
    is_active: bool | None = None
    start_date: date | None = None
    end_date: date | None = None

    has_legal_process: bool | None = None
    has_renegotiation: bool | None = None
    renegotiated_amount: float | None = Field(None, ge=0)
    renegotiation_type: RenegotiationType | None = None
    installment_count: int | None = Field(None, ge=1)
    installment_value: float | None = Field(None, gt=0)
    renegotiation_agreement_date: date | None = None
    renegotiation_first_payment_date: date | None = None
    renegotiation_due_day: int | None = Field(None, ge=1, le=31)
    # Modo 2: Cronograma Financeiro Personalizado (ver Create). None = não altera o modo.
    uses_custom_schedule: bool | None = None

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
                self.uses_custom_schedule,
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
            # Renegociação válida exige valor > 0 (0 não faz sentido financeiro; base da dívida).
            if float(self.renegotiated_amount) <= 0:
                raise ValueError("renegotiated_amount deve ser maior que zero quando has_renegotiation=true")
            if self.renegotiation_type is None:
                raise ValueError("renegotiation_type é obrigatório quando has_renegotiation=true")
            # Modo 2 (cronograma): relaxa a igualdade de parcelas fixas (ver Create).
            if self.renegotiation_type == "INSTALLMENTS" and not self.uses_custom_schedule:
                if self.installment_count is None:
                    raise ValueError("installment_count é obrigatório quando renegotiation_type=INSTALLMENTS")
                if self.installment_value is None:
                    raise ValueError("installment_value é obrigatório quando renegotiation_type=INSTALLMENTS")
                total_calc = round(float(self.installment_count) * float(self.installment_value), 2)
                if round(float(self.renegotiated_amount), 2) != total_calc:
                    raise ValueError("renegotiated_amount deve ser igual a installment_count * installment_value")
        elif self.uses_custom_schedule:
            raise ValueError("uses_custom_schedule exige has_renegotiation=true")
        return self

    @model_validator(mode="after")
    def validate_matrix_collaborator(self) -> "CompanyFinancialItemUpdate":
        # Validação parcial: só quando o item é EXPLICITAMENTE COLABORADOR_MATRIZ (Custo
        # Fixo). Não inferimos matriz a partir de `employee_id` isolado — Endividamento
        # agora também usa `employee_id` (só identificação, sem percentual/matriz).
        if self.item_type == "COLABORADOR_MATRIZ":
            if self.employee_id is None:
                raise ValueError("employee_id é obrigatório para item COLABORADOR_MATRIZ.")
            if self.percentual is None:
                raise ValueError("percentual é obrigatório para item COLABORADOR_MATRIZ.")
        # Mesma exclusividade da criação: o item aponta para UM cadastro de pessoa.
        if self.employee_id is not None and self.legal_person_id is not None:
            raise ValueError("Selecione um Colaborador OU um Desligado, não os dois.")
        return self


class ScheduleExecutionRead(BaseModel):
    """Execução oficial da dívida em Modo 2 (fonte ÚNICA). Produzida pelo backend; o frontend
    apenas exibe — nunca recalcula. Pago/saldo/progresso derivam dos pagamentos REAIS do CAP.
    """

    total_negociado: float = 0
    total_cronograma: float = 0
    total_pago: float = 0
    saldo_restante: float = 0
    progresso: float = 0  # 0..1
    parcelas_total: int = 0
    parcelas_pagas: int = 0
    parcelas_restantes: int = 0
    proxima_vencimento: date | None = None
    proxima_valor: float | None = None
    ultima_vencimento: date | None = None
    data_encerramento: date | None = None


class CompanyFinancialItemRead(BaseModel):
    id: UUID
    tipo: str
    item_type: CompanyFinancialItemType | None = None
    employee_id: UUID | None = None
    legal_person_id: UUID | None = None
    employee_name: str | None = None
    employee_employment_type: str | None = None
    legal_person_name: str | None = None
    percentual: float | None = None
    nome: str
    item_description: str | None = None
    valor_referencia: float | None = None
    # Base financeira ÚNICA da dívida (fonte da verdade): renegociado válido (> 0) senão
    # valor_referencia. Valor da Dívida/Pago Total/Saldo Restante/% Quitado usam esta base.
    debt_base: float | None = 0
    category: str | None = None
    cost_center_ref: str
    cost_center: str
    cost_center_project_id: UUID | None = None
    cost_center_system: CompanyFinancialCostCenterSystem | None = None
    description: str | None = None
    recurrence: str | None = None
    is_monthly_required: bool = False
    # Ciclo de vida do cadastro (distinto de `status`, que é o progresso do endividamento).
    is_active: bool = True
    start_date: date | None = None
    end_date: date | None = None
    has_legal_process: bool = False
    has_renegotiation: bool = False
    renegotiated_amount: float | None = None
    renegotiation_type: RenegotiationType | None = None
    installment_count: int | None = None
    installment_value: float | None = None
    renegotiation_agreement_date: date | None = None
    renegotiation_first_payment_date: date | None = None
    renegotiation_due_day: int | None = None
    # Modo do endividamento: false = parcelas iguais (atual); true = cronograma personalizado.
    uses_custom_schedule: bool = False
    # Execução oficial da dívida no Modo 2 (fonte única). None no Modo 1 (contrato inalterado).
    schedule: ScheduleExecutionRead | None = None
    pagamentos: list[PagamentoMes]
    total_pago: float | None = None
    pago_mes: float | None = 0
    restante: float | None = None
    progresso: float | None = None
    status: str | None = None
    progresso_mes: float | None = None
    # Espelho do Contas a Pagar da competência (fonte oficial de pagamento/status no Extrato
    # Analítico). Somente leitura; não altera a geração/sincronização do CAP.
    cap_has_line: bool = False
    cap_amount_paid: float | None = 0
    cap_status: str | None = None
    cap_is_obsolete: bool = False
    # Aviso transitório da sincronização grade→CAP: preenchido apenas na resposta do
    # PUT de pagamentos quando algum mês não pôde ser ajustado por já ter pagamento
    # registrado (ajuste manual necessário). Não é persistido.
    payable_sync_warning: str | None = None

    model_config = {"from_attributes": True}


class PagamentosReplace(BaseModel):
    pagamentos: list[PagamentoMes] = Field(default_factory=list)


class LancamentoCompetenciaIn(BaseModel):
    """Um lançamento (entrada) de uma competência — carga do modal.

    Genérico para qualquer item de Custo Fixo. `id` presente = edição de lançamento existente;
    ausente = novo. Descrição é texto livre (sem enum/hardcode).
    """

    id: str | None = None
    vencimento: date | None = None
    valor: float = Field(..., ge=0)
    # Texto livre; limite confortável. A coluna no banco mantém 255 (headroom); a exibição no
    # CAP trunca com reticências preservando o valor completo persistido.
    descricao: str | None = Field(default=None, max_length=150)


class LancamentosReplace(BaseModel):
    lancamentos: list[LancamentoCompetenciaIn] = Field(default_factory=list)


class LancamentoRead(BaseModel):
    id: str
    competencia: str
    vencimento: date | None = None
    valor: float | None = None
    descricao: str | None = None
    # Espelho do CAP (fonte oficial do pagamento por lançamento).
    cap_amount_paid: float | None = 0
    cap_status: str | None = None
    has_payment: bool = False


class LancamentosCompetenciaRead(BaseModel):
    item_id: str
    competencia: str
    lancamentos: list[LancamentoRead] = Field(default_factory=list)
    total: float | None = 0
    payable_sync_warning: str | None = None


# --------------------------------------------------------------------- #
# Cronograma Financeiro Personalizado (Endividamento — Modo 2)
# --------------------------------------------------------------------- #
class ScheduleRangeIn(BaseModel):
    """Faixa do gerador: parcelas [seq_start..seq_end] com o mesmo valor (expansão sem persistir)."""

    seq_start: int = Field(..., ge=1)
    seq_end: int = Field(..., ge=1)
    valor: float = Field(..., gt=0)
    dia: int = Field(..., ge=1, le=31)
    primeiro_vencimento: date

    @model_validator(mode="after")
    def validate_range(self) -> "ScheduleRangeIn":
        if self.seq_end < self.seq_start:
            raise ValueError("seq_end deve ser >= seq_start.")
        return self


class SchedulePreviewIn(BaseModel):
    ranges: list[ScheduleRangeIn] = Field(default_factory=list)


class SchedulePreviewLine(BaseModel):
    seq: int
    vencimento: date
    valor: float
    descricao: str | None = None


class SchedulePreviewRead(BaseModel):
    lines: list[SchedulePreviewLine] = Field(default_factory=list)
    count: int = 0
    total: float = 0


class ScheduleLineIn(BaseModel):
    """Uma parcela do cronograma. `id` presente = parcela existente; ausente = nova.

    `seq` é a posição da parcela (1..N) — chave estável que preserva parcelas pagas ao regerar.
    """

    id: str | None = None
    seq: int = Field(..., ge=1)
    vencimento: date
    valor: float = Field(..., gt=0)
    descricao: str | None = Field(default=None, max_length=150)


class ScheduleReplaceIn(BaseModel):
    lines: list[ScheduleLineIn] = Field(default_factory=list)
    # Exceção explícita: permite salvar mesmo com diferença de fechamento (uso controlado).
    allow_unbalanced: bool = False


class ScheduleLineRead(BaseModel):
    id: str
    seq: int | None = None
    vencimento: date | None = None
    valor: float | None = None
    descricao: str | None = None
    # Espelho do CAP (fonte oficial do pagamento por parcela, via entry_id).
    cap_amount_paid: float | None = 0
    cap_status: str | None = None
    has_payment: bool = False


class ScheduleRead(BaseModel):
    item_id: str
    uses_custom_schedule: bool = False
    renegotiated_amount: float | None = None
    total_cronograma: float | None = 0
    diferenca: float | None = 0
    is_valid: bool = True
    data_encerramento: date | None = None
    lines: list[ScheduleLineRead] = Field(default_factory=list)
    payable_sync_warning: str | None = None


class KpiEndividamentoRead(BaseModel):
    total_endividamento: float | None = None
    total_pago_mes: float | None = None
    saldo_restante: float | None = None
    quantidade_itens: int


class KpiCustosFixosRead(BaseModel):
    total_esperado_mes: float | None = None
    total_pago_mes: float | None = None
    quantidade_itens: int


class PendenciaLancamentoRead(BaseModel):
    """Item obrigatório mensal sem valor lançado na competência selecionada.

    Apenas monitoramento operacional: não representa lançamento financeiro,
    conta a pagar ou título com valor zero.
    """

    item_id: UUID
    nome: str
    competencia: str  # YYYY-MM
    category: str | None = None
    cost_center: str | None = None
    valor_referencia: float | None = None
    ultimo_valor: float | None = None  # último valor lançado em competência anterior
    ultimo_mes: str | None = None  # YYYY-MM da última competência com valor
    # "cronograma" = pendência derivada de uma parcela do Cronograma Financeiro (Modo 2).
    origem: Literal["manual", "renegociacao", "cronograma"] = "manual"


class PendenciasCustosFixosRead(BaseModel):
    competencia: str  # YYYY-MM
    quantidade: int
    pendencias: list[PendenciaLancamentoRead]
    total_previsto: float | None = 0
    total_pago: float | None = 0


class ChartPoint(BaseModel):
    mes: str
    pagamentos_mes: float | None = None
    saldo_restante_total: float | None = None


class ChartSeriesRead(BaseModel):
    points: list[ChartPoint]
