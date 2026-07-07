from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class PayableSnapshotType(str, enum.Enum):
    COLLABORATOR = "COLLABORATOR"
    VEHICLE = "VEHICLE"
    FIXED_COST = "FIXED_COST"
    ENDIVIDAMENTO = "ENDIVIDAMENTO"
    # Legacy name kept so old databases/rows can still be read until migrated.
    FINANCIAL = "FINANCIAL"
    # Antecipação individual de NF (ref_id = ReceivableInvoiceAnticipation).
    ANTECIPACAO = "ANTECIPACAO"
    # Obrigações financeiras de uma OPERAÇÃO de antecipação/borderô — deságio, tarifas
    # e repasse (ref_id = ReceivableAdvanceBatch). Tipo isolado da antecipação individual
    # para não interferir na reconciliação de snapshot; exibido como "Antecipação" na UI.
    ANTECIPACAO_OPERACAO = "ANTECIPACAO_OPERACAO"
    MANUAL = "MANUAL"


PAYABLE_SNAPSHOT_TYPE_DB = Enum(PayableSnapshotType, name="payable_snapshot_type")


class PayableOrigin(str, enum.Enum):
    """Origem rastreável de um lançamento do Contas a Pagar.

    Armazenada como texto (coluna `origin`), acompanhada do `ref_id` (ID da origem).
    É a base arquitetural para as automações de geração — cada rotina identifica suas
    linhas por (origin, ref_id, competência), garantindo idempotência.
    """

    PROJECT = "PROJECT"
    FIXED_COST = "FIXED_COST"
    DEBT = "DEBT"
    MANUAL = "MANUAL"
    PAYROLL = "PAYROLL"
    ANTECIPACAO = "ANTECIPACAO"


def default_origin_for_type(t: "PayableSnapshotType") -> str:
    """Origem inferida a partir do `type` (para linhas legadas sem `origin`)."""
    if t == PayableSnapshotType.COLLABORATOR:
        return PayableOrigin.PROJECT.value
    if t == PayableSnapshotType.VEHICLE:
        return PayableOrigin.PROJECT.value
    if t == PayableSnapshotType.FIXED_COST:
        return PayableOrigin.FIXED_COST.value
    if t in (PayableSnapshotType.ENDIVIDAMENTO, PayableSnapshotType.FINANCIAL):
        return PayableOrigin.DEBT.value
    if t in (PayableSnapshotType.ANTECIPACAO, PayableSnapshotType.ANTECIPACAO_OPERACAO):
        return PayableOrigin.ANTECIPACAO.value
    return PayableOrigin.MANUAL.value


class PayableSnapshot(TimestampUUIDMixin, Base):
    """
    Snapshot mensal de contas a pagar (imutável após geração).

    `month` é a competência do pagamento (ex.: 2026-05-01).
    Os valores são copiados do mês anterior (fonte) no momento da geração.
    """

    __tablename__ = "payable_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "month",
            "type",
            "ref_id",
            "project_id",
            "name",
            "category",
            "cost_center",
            name="uq_payable_snapshot_identity",
        ),
    )

    month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    type: Mapped[PayableSnapshotType] = mapped_column(PAYABLE_SNAPSHOT_TYPE_DB, nullable=False, index=True)

    ref_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Origem rastreável do lançamento (PROJECT, FIXED_COST, DEBT, MANUAL, PAYROLL, …).
    # Preenchida nas gerações automáticas; NULL em registros legados (origem inferida
    # pelo `type` na leitura). Combinada com `ref_id`, identifica a origem de cada linha.
    origin: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Descrição do item, separada do `name` (que é o Credor). Hoje preenchida em
    # lançamentos de Endividamento vinculados ao cadastro; genérica de propósito
    # (reutilizável por outros tipos no futuro). NULL em legados/demais tipos.
    item_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_center: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    amount_original: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_final: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    include_in_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Reconciliação de snapshot (resíduos cuja origem foi removida) ---
    # Apenas marcação operacional/auditoria: NÃO altera amount_*, pagamentos,
    # estornos ou lançamentos manuais. Permite limpeza manual e remoção do
    # dashboard sem regenerar o mês (que apagaria histórico de pagamentos).
    is_obsolete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    obsolete_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    payments: Mapped[list["PayablePayment"]] = relationship(  # noqa: F821
        "PayablePayment",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
