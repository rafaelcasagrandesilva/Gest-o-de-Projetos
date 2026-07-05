from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class AdvanceInstitution(TimestampUUIDMixin, Base):
    """Instituição financeira de antecipação (ex.: Lepta Multissetorial, Banco Daycoval).

    O `operation_profile` é a chave usada pelo AdvanceOperationService para resolver
    o handler de regras (LEPTA, DAYCOVAL, …). É um texto (não enum no banco) para que
    novas instituições/perfis possam ser adicionados apenas cadastrando + implementando
    um handler, sem migration de tipo.
    """

    __tablename__ = "advance_institutions"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    institution_type: Mapped[str] = mapped_column(String(64), nullable=False, default="OUTROS")
    operation_profile: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
