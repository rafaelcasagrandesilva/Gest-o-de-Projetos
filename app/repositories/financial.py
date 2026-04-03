from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial import Invoice, InvoiceAnticipation, Revenue
from app.repositories.base import Repository


class RevenueRepository(Repository[Revenue]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Revenue)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        project_id: UUID | None = None,
        project_ids: list[UUID] | None = None,
    ) -> list[Revenue]:
        stmt = select(Revenue).order_by(Revenue.competencia.desc()).offset(offset).limit(limit)
        if project_id is not None:
            stmt = stmt.where(Revenue.project_id == project_id)
        elif project_ids is not None:
            if len(project_ids) == 0:
                return []
            stmt = stmt.where(Revenue.project_id.in_(project_ids))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class InvoiceRepository(Repository[Invoice]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Invoice)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        project_id: UUID | None = None,
        project_ids: list[UUID] | None = None,
    ) -> list[Invoice]:
        stmt = select(Invoice).order_by(Invoice.competencia.desc()).offset(offset).limit(limit)
        if project_id is not None:
            stmt = stmt.where(Invoice.project_id == project_id)
        elif project_ids is not None:
            if len(project_ids) == 0:
                return []
            stmt = stmt.where(Invoice.project_id.in_(project_ids))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class InvoiceAnticipationRepository(Repository[InvoiceAnticipation]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, InvoiceAnticipation)
