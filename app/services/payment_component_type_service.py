from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_component import PaymentComponentType, PaymentVariableComponent


class PaymentComponentTypeService:
    """CRUD do cadastro de Tipos de Componente Variável (Configurações).

    Espelha o padrão de `AdvanceInstitutionService`: nome/código únicos; nunca exclui um
    tipo já utilizado — orienta a inativar (`is_active=False`) para preservar histórico.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, *, only_active: bool = False) -> list[PaymentComponentType]:
        stmt = select(PaymentComponentType).order_by(
            PaymentComponentType.display_order.asc(), PaymentComponentType.name.asc()
        )
        if only_active:
            stmt = stmt.where(PaymentComponentType.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def usage_counts(self, type_ids: list[UUID]) -> dict[UUID, int]:
        """Quantidade de lançamentos por tipo (para a coluna 'Utilizações'), em lote."""
        if not type_ids:
            return {}
        rows = (
            await self.db.execute(
                select(
                    PaymentVariableComponent.type_id, func.count()
                )
                .where(PaymentVariableComponent.type_id.in_(type_ids))
                .group_by(PaymentVariableComponent.type_id)
            )
        ).all()
        return {tid: int(n or 0) for tid, n in rows}

    async def get(self, type_id: UUID) -> PaymentComponentType | None:
        return await self.db.get(PaymentComponentType, type_id)

    async def _field_taken(self, field, value: str, *, exclude_id: UUID | None = None) -> bool:
        stmt = select(func.count()).select_from(PaymentComponentType).where(
            func.lower(field) == value.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(PaymentComponentType.id != exclude_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0) > 0

    async def create(self, data: dict) -> PaymentComponentType:
        name = str(data["name"]).strip()
        code = str(data["code"]).strip().lower()
        if await self._field_taken(PaymentComponentType.name, name):
            raise ValueError("Já existe um tipo com esse nome.")
        if await self._field_taken(PaymentComponentType.code, code):
            raise ValueError("Já existe um tipo com esse código interno.")
        row = PaymentComponentType(
            name=name,
            code=code,
            description=data.get("description"),
            is_active=bool(data.get("is_active", True)),
            display_order=int(data.get("display_order", 0) or 0),
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update(self, type_id: UUID, data: dict) -> PaymentComponentType | None:
        row = await self.get(type_id)
        if row is None:
            return None
        if "name" in data and data["name"] is not None:
            new_name = str(data["name"]).strip()
            if await self._field_taken(PaymentComponentType.name, new_name, exclude_id=type_id):
                raise ValueError("Já existe um tipo com esse nome.")
            row.name = new_name
        if "code" in data and data["code"] is not None:
            new_code = str(data["code"]).strip().lower()
            if await self._field_taken(PaymentComponentType.code, new_code, exclude_id=type_id):
                raise ValueError("Já existe um tipo com esse código interno.")
            row.code = new_code
        if "description" in data:
            row.description = data["description"]
        if "is_active" in data and data["is_active"] is not None:
            row.is_active = bool(data["is_active"])
        if "display_order" in data and data["display_order"] is not None:
            row.display_order = int(data["display_order"])
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def _usage_count(self, type_id: UUID) -> int:
        stmt = select(func.count()).select_from(PaymentVariableComponent).where(
            PaymentVariableComponent.type_id == type_id
        )
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def delete(self, type_id: UUID) -> bool:
        """Exclui apenas se nunca utilizado; caso contrário, orienta a inativar (histórico)."""
        row = await self.get(type_id)
        if row is None:
            return False
        if await self._usage_count(type_id) > 0:
            raise ValueError(
                "Tipo já utilizado em lançamentos; inative-o (Ativo/Inativo) em vez de excluir."
            )
        await self.db.delete(row)
        await self.db.flush()
        return True
