from __future__ import annotations

import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class ChartAccountType(str, enum.Enum):
    COST = "COST"
    EXPENSE = "EXPENSE"


CHART_ACCOUNT_TYPE_DB = Enum(ChartAccountType, name="chart_account_type")


class ChartOfAccounts(TimestampUUIDMixin, Base):
    __tablename__ = "chart_of_accounts"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[ChartAccountType] = mapped_column(CHART_ACCOUNT_TYPE_DB, nullable=False, index=True)

