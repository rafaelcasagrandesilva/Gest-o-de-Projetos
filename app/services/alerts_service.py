from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.financial import Invoice
from app.models.project import Project
from app.services.financial_service import FinancialService


class AlertsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.financial = FinancialService(session)

    async def check_contas_vencendo(self, *, today: date, days_ahead: int = 7) -> list[Alert]:
        limit_date = today + timedelta(days=days_ahead)
        stmt = select(Invoice).where(Invoice.status == "open", Invoice.due_date <= limit_date)
        invoices = list((await self.session.execute(stmt)).scalars().all())
        alerts: list[Alert] = []
        for inv in invoices:
            alerts.append(
                Alert(
                    project_id=inv.project_id,
                    competencia=inv.competencia,
                    alert_type="invoice_due",
                    severity="warning",
                    message=f"Conta a vencer (due_date={inv.due_date.isoformat()} | amount={float(inv.amount):.2f}).",
                )
            )
        for a in alerts:
            self.session.add(a)
        await self.session.commit()
        for a in alerts:
            await self.session.refresh(a)
        return alerts

    async def check_margem_negativa(self, *, competencia: date) -> list[Alert]:
        projects = list((await self.session.execute(select(Project))).scalars().all())
        alerts: list[Alert] = []
        for p in projects:
            margem = await self.financial.calcular_margem(project_id=p.id, competencia=competencia)
            if margem < 0:
                alerts.append(
                    Alert(
                        project_id=p.id,
                        competencia=competencia,
                        alert_type="negative_margin",
                        severity="critical",
                        message=f"Margem negativa no projeto '{p.name}' (margem={margem:.4f}).",
                    )
                )
        for a in alerts:
            self.session.add(a)
        await self.session.commit()
        for a in alerts:
            await self.session.refresh(a)
        return alerts

    async def list_alerts(self, *, offset: int = 0, limit: int = 50) -> list[Alert]:
        stmt = select(Alert).order_by(Alert.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def resolve_alert(self, *, alert_id, is_resolved: bool) -> Alert:
        alert = await self.session.get(Alert, alert_id)
        if not alert:
            raise ValueError("Alert not found")
        alert.is_resolved = is_resolved
        await self.session.commit()
        await self.session.refresh(alert)
        return alert

