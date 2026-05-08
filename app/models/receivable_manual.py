from __future__ import annotations

from datetime import date
from enum import Enum

from sqlalchemy import Date, Enum as SAEnum, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class ReceivableManualStatus(str, Enum):
    ABERTO = "ABERTO"
    PARCIAL = "PARCIAL"
    RECEBIDO = "RECEBIDO"


class ReceivableManualItem(TimestampUUIDMixin, Base):
    __tablename__ = "receivable_manual_items"

    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="finance")
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    cliente: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    numero_referencia: Mapped[str | None] = mapped_column(String(64), nullable=True)

    data_emissao: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    valor_liquido: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    valor_recebido: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    data_recebimento: Mapped[date | None] = mapped_column(Date, nullable=True)

    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[ReceivableManualStatus] = mapped_column(
        SAEnum(ReceivableManualStatus, name="receivable_manual_status"),
        nullable=False,
        default=ReceivableManualStatus.ABERTO,
        server_default=ReceivableManualStatus.ABERTO.value,
    )
