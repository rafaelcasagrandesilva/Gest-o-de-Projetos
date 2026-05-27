from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class CostCenterAlias(TimestampUUIDMixin, Base):
    """DE-PARA: texto da planilha → centro de custo canônico no SGP."""

    __tablename__ = "cost_center_aliases"
    __table_args__ = (
        UniqueConstraint("alias_name_normalized", name="uq_cost_center_alias_normalized"),
    )

    alias_name: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_name_normalized: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_cost_center: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
