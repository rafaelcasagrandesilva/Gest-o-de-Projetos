from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_finance import CompanyFinancialItem
from app.models.payment_component import PaymentComponentType, PaymentVariableComponent
from app.models.project_operational import ProjectLabor
from app.services.payable_snapshot_service import PayableSnapshotService
from app.utils.date_utils import normalize_competencia


class PaymentVariableComponentService:
    """CRUD dos Componentes Variáveis de Pagamento.

    REQUISITO ARQUITETURAL: cada operação (criar/editar/excluir) reconstrói o snapshot do
    Contas a Pagar na MESMA transação (flush aqui; o router faz um único commit). Não há
    janela em que o componente exista sem o CAP refletir. A sincronização
    (`PayableSnapshotService.apply_variable_component`) é idempotente e é a fonte de verdade
    — a reconciliação não decide sobre estes lançamentos.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.snapshots = PayableSnapshotService(db)

    def _to_read_row(self, row: PaymentVariableComponent) -> dict:
        return {
            "id": row.id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "type_id": row.type_id,
            "type_name": getattr(row.type, "name", ""),
            "type_code": getattr(row.type, "code", ""),
            "employee_id": row.employee_id,
            "competencia": row.competencia,
            "amount": float(row.amount),
            "note": row.note,
            "project_labor_id": row.project_labor_id,
            "company_financial_item_id": row.company_financial_item_id,
        }

    async def list_for_project_labor(self, labor_id: UUID) -> list[dict]:
        rows = (
            await self.db.execute(
                select(PaymentVariableComponent)
                .where(PaymentVariableComponent.project_labor_id == labor_id)
                .order_by(PaymentVariableComponent.created_at.asc())
            )
        ).scalars().all()
        return [self._to_read_row(r) for r in rows]

    async def list_for_company_item(self, item_id: UUID, competencia: date) -> list[dict]:
        comp = normalize_competencia(competencia)
        rows = (
            await self.db.execute(
                select(PaymentVariableComponent)
                .where(
                    PaymentVariableComponent.company_financial_item_id == item_id,
                    PaymentVariableComponent.competencia == comp,
                )
                .order_by(PaymentVariableComponent.created_at.asc())
            )
        ).scalars().all()
        return [self._to_read_row(r) for r in rows]

    async def _require_active_type(self, type_id: UUID) -> PaymentComponentType:
        t = await self.db.get(PaymentComponentType, type_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Tipo de componente não encontrado.")
        if not t.is_active:
            raise HTTPException(
                status_code=400,
                detail="Tipo inativo não pode ser usado em novos lançamentos.",
            )
        return t

    async def get(self, component_id: UUID) -> PaymentVariableComponent | None:
        return await self.db.get(PaymentVariableComponent, component_id)

    async def create(self, payload: dict) -> dict:
        await self._require_active_type(payload["type_id"])

        project_labor_id = payload.get("project_labor_id")
        company_financial_item_id = payload.get("company_financial_item_id")
        if bool(project_labor_id) == bool(company_financial_item_id):
            raise HTTPException(
                status_code=400,
                detail="Informe exatamente um contexto: project_labor_id OU company_financial_item_id.",
            )

        if project_labor_id is not None:
            labor = await self.db.get(ProjectLabor, project_labor_id)
            if labor is None:
                raise HTTPException(status_code=404, detail="Vínculo de mão de obra não encontrado.")
            employee_id = labor.employee_id
            competencia = normalize_competencia(labor.competencia)
        else:
            item = await self.db.get(CompanyFinancialItem, company_financial_item_id)
            if item is None:
                raise HTTPException(status_code=404, detail="Item de custo fixo não encontrado.")
            if item.employee_id is None:
                raise HTTPException(status_code=400, detail="Item de custo fixo não é vinculado a colaborador.")
            if payload.get("competencia") is None:
                raise HTTPException(status_code=400, detail="Informe a competência do componente (custo fixo).")
            employee_id = item.employee_id
            competencia = normalize_competencia(payload["competencia"])

        row = PaymentVariableComponent(
            type_id=payload["type_id"],
            employee_id=employee_id,
            competencia=competencia,
            amount=payload["amount"],
            note=(payload.get("note") or None),
            project_labor_id=project_labor_id,
            company_financial_item_id=company_financial_item_id,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        # Mesma transação: materializa o snapshot no CAP.
        await self.snapshots.apply_variable_component(component=row)
        return self._to_read_row(row)

    async def update(self, component_id: UUID, payload: dict) -> dict:
        row = await self.get(component_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Componente não encontrado.")

        # Editar não é permitido se o lançamento já foi pago (preserva histórico).
        existing = await self.snapshots._find_variable_snapshot(component_id)
        if existing is not None and (
            float(existing.amount_paid or 0) > 0
            or await self.snapshots._sum_active_payments(existing.id) > 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Componente com pagamento registrado não pode ser editado.",
            )

        if "type_id" in payload and payload["type_id"] is not None:
            await self._require_active_type(payload["type_id"])
            row.type_id = payload["type_id"]
        if "amount" in payload and payload["amount"] is not None:
            row.amount = payload["amount"]
        if "note" in payload:
            row.note = payload.get("note") or None

        await self.db.flush()
        await self.db.refresh(row)
        # Mesma transação: reconstrói o snapshot.
        await self.snapshots.apply_variable_component(component=row)
        return self._to_read_row(row)

    async def replace_for_project_labor(self, labor_id: UUID, items: list[dict]) -> list[dict]:
        """Reconcilia (create/update/delete) o conjunto de componentes de um vínculo de
        projeto em UMA transação (o router faz o commit). Reusa create/update/delete —
        cada um reconstrói seu snapshot; guardas de pagamento continuam valendo.
        """
        labor = await self.db.get(ProjectLabor, labor_id)
        if labor is None:
            raise HTTPException(status_code=404, detail="Vínculo de mão de obra não encontrado.")

        existing = await self.list_for_project_labor(labor_id)
        existing_ids = {r["id"] for r in existing}
        desired_ids = {i["id"] for i in items if i.get("id") is not None}

        # Remove os que saíram da lista (bloqueia se pago).
        for cid in existing_ids - desired_ids:
            await self.delete(cid)

        out: list[dict] = []
        for item in items:
            if item.get("id") is not None:
                out.append(
                    await self.update(
                        item["id"],
                        {k: item[k] for k in ("type_id", "amount", "note") if k in item},
                    )
                )
            else:
                out.append(
                    await self.create(
                        {
                            "type_id": item["type_id"],
                            "amount": item["amount"],
                            "note": item.get("note"),
                            "project_labor_id": labor_id,
                        }
                    )
                )
        return out

    async def replace_for_company_item(
        self, item_id: UUID, competencia: date, items: list[dict]
    ) -> list[dict]:
        """Reconcilia os componentes de um item de Custo Fixo numa competência, em 1 transação.

        Espelha `replace_for_project_labor`: reusa create/update/delete (cada um reconstrói
        seu snapshot); a competência é obrigatória (o item não é por competência).
        """
        item = await self.db.get(CompanyFinancialItem, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Item de custo fixo não encontrado.")
        comp = normalize_competencia(competencia)

        existing = await self.list_for_company_item(item_id, comp)
        existing_ids = {r["id"] for r in existing}
        desired_ids = {i["id"] for i in items if i.get("id") is not None}

        for cid in existing_ids - desired_ids:
            await self.delete(cid)

        out: list[dict] = []
        for item_data in items:
            if item_data.get("id") is not None:
                out.append(
                    await self.update(
                        item_data["id"],
                        {k: item_data[k] for k in ("type_id", "amount", "note") if k in item_data},
                    )
                )
            else:
                out.append(
                    await self.create(
                        {
                            "type_id": item_data["type_id"],
                            "amount": item_data["amount"],
                            "note": item_data.get("note"),
                            "company_financial_item_id": item_id,
                            "competencia": comp,
                        }
                    )
                )
        return out

    async def delete(self, component_id: UUID) -> None:
        row = await self.get(component_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Componente não encontrado.")
        # Mesma transação: remove o snapshot (bloqueia se houver pagamento).
        removed = await self.snapshots.remove_variable_component_snapshot(component_id=component_id)
        if not removed:
            raise HTTPException(
                status_code=400,
                detail="Componente com pagamento registrado não pode ser excluído.",
            )
        await self.db.delete(row)
        await self.db.flush()
