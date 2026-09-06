from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class PaymentComponentType(TimestampUUIDMixin, Base):
    """Cadastro data-driven dos tipos de Componente Variável de Pagamento.

    Fonte ÚNICA dos tipos usados em Projetos, Custo Fixo, Contas a Pagar e no Relatório
    de Fechamento da Folha. Criar/inativar aqui reflete automaticamente em todas as telas
    e no relatório — não existe lista hardcoded de tipos em lugar nenhum.

    Nunca excluir um tipo já utilizado (ver `PaymentComponentTypeService.delete`): apenas
    inativar (`is_active=False`), preservando o histórico dos lançamentos.
    """

    __tablename__ = "payment_component_types"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # Código interno estável (não muda quando o nome de exibição é editado).
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true", index=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class PaymentVariableComponent(TimestampUUIDMixin, Base):
    """Lançamento variável de pagamento de um colaborador numa competência.

    N por colaborador × competência × contexto. O contexto é polimórfico e EXATAMENTE UM:
    - `project_labor_id`  → componente lançado num Projeto (herda projeto/cenário/competência);
    - `company_financial_item_id` → componente lançado num Custo Fixo (colaborador/matriz).

    `employee_id` e `competencia` são denormalizados (preenchidos a partir do contexto) para
    que a geração de snapshots e a leitura do relatório sejam idênticas nos dois contextos —
    um único pipeline. O valor é INTEGRAL (regra de negócio: componente variável não é
    rateado pelo % de alocação; só o salário-base é).
    """

    __tablename__ = "payment_variable_components"
    __table_args__ = (
        CheckConstraint(
            "(project_labor_id IS NOT NULL)::int + (company_financial_item_id IS NOT NULL)::int = 1",
            name="ck_payment_variable_component_single_context",
        ),
        UniqueConstraint(
            "type_id", "project_labor_id", "company_financial_item_id", "competencia", "amount", "note",
            name="uq_payment_variable_component_identity",
        ),
    )

    type_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        # RESTRICT: o banco recusa apagar um tipo em uso (reforça a regra do service).
        ForeignKey("payment_component_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    project_labor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_labors.id", ondelete="CASCADE"), nullable=True, index=True
    )
    company_financial_item_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("company_financial_items.id", ondelete="CASCADE"), nullable=True, index=True
    )

    type: Mapped["PaymentComponentType"] = relationship("PaymentComponentType", lazy="joined")


class PaymentComponentAttachment(TimestampUUIDMixin, Base):
    """Comprovante de um Componente Variável de Pagamento (nota do reembolso, recibo, cupom).

    N arquivos por lançamento. O vínculo é com o COMPONENTE, não com o contexto: o mesmo
    anexo aparece no lançamento seja ele de Projeto ou de Custo Fixo, porque o componente
    já carrega o contexto. Excluir o componente leva os anexos junto (CASCADE no banco;
    os arquivos em disco são apagados pelo service antes do delete).

    O arquivo mora em disco sob a raiz única de storage (`Settings.resolved_storage_root`),
    como os PDFs de NF e os anexos de ativo — nunca no banco.
    """

    __tablename__ = "payment_component_attachments"

    component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_variable_components.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Caminho RELATIVO à raiz dos anexos (o absoluto muda entre ambientes/deploys).
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
