from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class ProjectContractAdditive(TimestampUUIDMixin, Base):
    """Aditivo contratual de um projeto (relação 1-N, normalizada).

    Cadastro puramente contratual: não participa de nenhuma regra financeira,
    dashboard, snapshot ou indicador. Cada projeto pode ter N aditivos.
    """

    __tablename__ = "project_contract_additives"

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    additive_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    additive_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Prazo adicional (texto livre: "12 meses", "180 dias", …).
    additive_duration: Mapped[str | None] = mapped_column(String(120), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="additives")  # noqa: F821
