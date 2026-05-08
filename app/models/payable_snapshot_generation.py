from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PayableSnapshotGeneration(Base):
    """Marca que o snapshot do mês já foi gerado (mesmo que vazio)."""

    __tablename__ = "payable_snapshot_generations"

    month: Mapped[date] = mapped_column(Date, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
