from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin
from app.models.employee import Employee
from app.models.project import Project


class RenegotiationType(str, Enum):
    UNIQUE = "UNIQUE"
    INSTALLMENTS = "INSTALLMENTS"


class CompanyFinancialItemType(str, Enum):
    MANUAL = "MANUAL"
    COLABORADOR_MATRIZ = "COLABORADOR_MATRIZ"


class CompanyFinancialItem(TimestampUUIDMixin, Base):
    """Item corporativo: endividamento (finito) ou custo fixo recorrente."""

    __tablename__ = "company_financial_items"

    tipo: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    item_type: Mapped[CompanyFinancialItemType] = mapped_column(
        SAEnum(CompanyFinancialItemType, name="company_financial_item_type"),
        nullable=False,
        default=CompanyFinancialItemType.MANUAL,
        server_default=CompanyFinancialItemType.MANUAL.value,
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Ex-colaborador do Jurídico (`legal_persons`), cadastro próprio e praticamente disjunto de
    # `employees`. Só ENDIVIDAMENTO usa: um passivo trabalhista costuma ser com quem já saiu.
    # Como `employee_id` no endividamento, é apenas identificação — define o nome do item e não
    # entra em cálculo nenhum. Excludente com `employee_id` (validado no schema).
    legal_person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("legal_persons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    percentual: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    # Descrição própria do item (ex.: "Acordo de Remuneração"), separada do `nome`.
    # Genérica de propósito (reutilizável por outros tipos futuros); hoje usada por
    # Endividamento. NULL em registros legados — o `nome` continua sendo a fonte de exibição.
    item_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    valor_referencia: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_center_project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cost_center_system: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Controle operacional (custos fixos): sinaliza itens obrigatórios mensais
    # para detectar competências sem valor lançado. NÃO afeta cálculos/lançamentos.
    is_monthly_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Ciclo de vida do cadastro. start_date = início; end_date = encerramento.
    # Inativo (is_active=False) não gera NOVOS lançamentos automáticos nem pendências,
    # mas permanece no histórico e vinculado aos lançamentos antigos. Inativo exige
    # end_date; ativo pode manter ambos nulos.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Campos adicionais (endividamento)
    has_legal_process: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    has_renegotiation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    renegotiated_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    renegotiation_type: Mapped[RenegotiationType | None] = mapped_column(
        SAEnum(RenegotiationType, name="renegotiation_type"),
        nullable=True,
    )
    installment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    installment_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Cronograma da renegociação (endividamento). Servem para derivar a parcela
    # esperada por competência (obrigatoriedade automática). Não criam lançamento.
    renegotiation_agreement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    renegotiation_first_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    renegotiation_due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Modo do endividamento renegociado (Cronograma Financeiro Personalizado).
    # False (todos os legados) → Modo 1 "parcelas iguais": comportamento ATUAL, inalterado.
    # True  → Modo 2: o conjunto de LANÇAMENTOS (payments) é a fonte oficial da execução da
    #   dívida; cada linha vira um título no CAP por `entry_id`. Neste modo, pago/saldo/progresso
    #   derivam EXCLUSIVAMENTE do cronograma + pagamentos reais do CAP (nunca da soma das linhas).
    # Genérico de propósito: base para reutilizar "cronograma financeiro" em outras obrigações
    # (acordos judiciais, parcelamentos tributários, financiamentos) no futuro.
    uses_custom_schedule: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    payments: Mapped[list["CompanyFinancialPayment"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )

    employee: Mapped[Employee | None] = relationship()
    cost_center_project: Mapped[Project | None] = relationship()


class CompanyFinancialPayment(TimestampUUIDMixin, Base):
    """Lançamento de uma competência (grade mensal).

    Historicamente havia EXATAMENTE um lançamento por (item, competência) — o valor
    esperado do mês. A partir da evolução "múltiplos lançamentos por competência" a
    restrição de unicidade foi removida: um mesmo item pode ter N lançamentos no mesmo
    mês (ex.: fornecedor que fatura mais de uma vez). Cada lançamento vira um título
    independente no Contas a Pagar (PayableSnapshot.entry_id = este id), com pagamento
    próprio. A tela principal mostra apenas a SOMA dos lançamentos da competência.

    Genérico de propósito — serve qualquer item de Custo Fixo, sem regra por fornecedor.
    Nota de nomenclatura: a tabela chama-se `..._payments` por herança histórica; cada
    linha é conceitualmente um LANÇAMENTO (não um pagamento — o pagamento vive no CAP).
    """

    __tablename__ = "company_financial_payments"

    item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company_financial_items.id", ondelete="CASCADE"), index=True
    )
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    # Vencimento do lançamento (governa o due_date do título no CAP). NULL apenas em
    # registros legados até o backfill; novos lançamentos sempre preenchem.
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Descrição livre do lançamento (ex.: "1ª quinzena", "NF 45872", "Complemento").
    # Texto totalmente livre — sem enum/hardcode. Opcional.
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Sequência da PARCELA no Cronograma Financeiro Personalizado (Modo 2). Preenchido apenas
    # em lançamentos de cronograma; NULL em legados/Custos Fixos. Chave estável que permite
    # regerar o cronograma por faixas preservando as parcelas já pagas (casamento por seq).
    schedule_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)

    item: Mapped["CompanyFinancialItem"] = relationship(back_populates="payments")
