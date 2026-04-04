from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial import Invoice, InvoiceAnticipation, Revenue
from app.repositories.financial import InvoiceAnticipationRepository, InvoiceRepository, RevenueRepository
from app.core.scenario import coerce_scenario
from app.services.audit_service import AuditService
from app.services.utils import model_to_dict


def revenue_retention_value(*, amount: float, has_retention: bool) -> float:
    """Retenção de 10% sobre o valor do faturamento quando has_retention; senão zero."""
    return round(float(amount) * 0.10, 2) if has_retention else 0.0


class FinancialCrudService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.revenues = RevenueRepository(session)
        self.invoices = InvoiceRepository(session)
        self.anticipations = InvoiceAnticipationRepository(session)
        self.audit = AuditService(session)

    async def list_revenues(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        project_id=None,
        project_ids: list[UUID] | None = None,
        scenario: str | None = None,
    ) -> list[Revenue]:
        sc = coerce_scenario(scenario)
        return await self.revenues.list(
            offset=offset,
            limit=limit,
            project_id=project_id,
            project_ids=project_ids,
            scenario=sc,
        )

    async def create_revenue(self, *, actor_user_id, data: dict) -> Revenue:
        row = Revenue(**data)
        await self.revenues.add(row)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="Revenue",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_revenue(self, *, actor_user_id, revenue_id, data: dict) -> Revenue:
        row = await self.revenues.get(revenue_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receita não encontrada.")
        before = model_to_dict(row)
        self.revenues.apply_updates(row, data)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="update",
            entity="Revenue",
            entity_id=row.id,
            before=before,
            after=model_to_dict(row),
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete_revenue(self, *, actor_user_id, revenue_id) -> None:
        row = await self.revenues.get(revenue_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receita não encontrada.")
        before = model_to_dict(row)
        await self.revenues.delete(row)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="delete",
            entity="Revenue",
            entity_id=revenue_id,
            before=before,
            after=None,
        )
        await self.session.commit()

    async def list_invoices(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        project_id=None,
        project_ids: list[UUID] | None = None,
    ) -> list[Invoice]:
        return await self.invoices.list(
            offset=offset, limit=limit, project_id=project_id, project_ids=project_ids
        )

    async def create_invoice(self, *, actor_user_id, data: dict) -> Invoice:
        row = Invoice(**data)
        await self.invoices.add(row)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="Invoice",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def create_anticipation(self, *, actor_user_id, data: dict) -> InvoiceAnticipation:
        row = InvoiceAnticipation(**data)
        await self.anticipations.add(row)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="InvoiceAnticipation",
            entity_id=row.id,
            before=None,
            after=model_to_dict(row),
        )
        await self.session.commit()
        await self.session.refresh(row)
        return row

