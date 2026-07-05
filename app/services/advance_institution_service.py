from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.advance_institution import AdvanceInstitution
from app.models.receivable_advance_batch import ReceivableAdvanceBatch


class AdvanceInstitutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, *, only_active: bool = False) -> list[AdvanceInstitution]:
        stmt = select(AdvanceInstitution).order_by(AdvanceInstitution.name.asc())
        if only_active:
            stmt = stmt.where(AdvanceInstitution.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def get(self, institution_id: UUID) -> AdvanceInstitution | None:
        return await self.db.get(AdvanceInstitution, institution_id)

    async def _name_taken(self, name: str, *, exclude_id: UUID | None = None) -> bool:
        stmt = select(func.count()).select_from(AdvanceInstitution).where(
            func.lower(AdvanceInstitution.name) == name.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(AdvanceInstitution.id != exclude_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0) > 0

    async def create(self, data: dict) -> AdvanceInstitution:
        name = str(data["name"]).strip()
        if await self._name_taken(name):
            raise ValueError("Já existe uma instituição com esse nome.")
        row = AdvanceInstitution(
            name=name,
            institution_type=str(data.get("institution_type") or "OUTROS").strip() or "OUTROS",
            operation_profile=str(data["operation_profile"]).strip().upper(),
            is_active=bool(data.get("is_active", True)),
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update(self, institution_id: UUID, data: dict) -> AdvanceInstitution | None:
        row = await self.get(institution_id)
        if row is None:
            return None
        if "name" in data and data["name"] is not None:
            new_name = str(data["name"]).strip()
            if await self._name_taken(new_name, exclude_id=institution_id):
                raise ValueError("Já existe uma instituição com esse nome.")
            row.name = new_name
        if "institution_type" in data and data["institution_type"] is not None:
            row.institution_type = str(data["institution_type"]).strip() or "OUTROS"
        if "operation_profile" in data and data["operation_profile"] is not None:
            row.operation_profile = str(data["operation_profile"]).strip().upper()
        if "is_active" in data and data["is_active"] is not None:
            row.is_active = bool(data["is_active"])
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def _usage_count(self, institution_id: UUID) -> int:
        stmt = select(func.count()).select_from(ReceivableAdvanceBatch).where(
            ReceivableAdvanceBatch.institution_id == institution_id
        )
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def delete(self, institution_id: UUID) -> bool:
        """Exclui apenas se nunca utilizada. Caso contrário, oriente a desativar (is_active=False)."""
        row = await self.get(institution_id)
        if row is None:
            return False
        if await self._usage_count(institution_id) > 0:
            raise ValueError(
                "Instituição já utilizada em operações; desative-a (Ativa/Inativa) em vez de excluir."
            )
        await self.db.delete(row)
        await self.db.flush()
        return True
