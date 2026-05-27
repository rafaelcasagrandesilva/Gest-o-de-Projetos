from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class PayableImportTemplate(TimestampUUIDMixin, Base):
    """Modelo de mapeamento de importação de contas a pagar por usuário."""

    __tablename__ = "payable_import_templates"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_payable_import_template_user_name"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    header_row: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    column_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
