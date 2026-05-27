from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_center_alias import CostCenterAlias
from app.models.project import Project
from app.services.payable_snapshot_service import MANUAL_PAYABLE_FIXED_COST_CENTERS


def normalize_alias(value: str) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


@dataclass(frozen=True)
class CostCenterResolveResult:
    target: str
    alias_applied: bool


class CostCenterAliasService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_valid_targets(self) -> list[str]:
        projects = (
            await self.session.execute(
                select(Project.name)
                .where(Project.deleted_at.is_(None))
                .order_by(Project.name.asc())
            )
        ).scalars().all()
        fixed = sorted(MANUAL_PAYABLE_FIXED_COST_CENTERS, key=str.casefold)
        names = {str(n).strip() for n in projects if str(n).strip()}
        out = list(fixed)
        for n in sorted(names, key=str.casefold):
            if n not in out:
                out.append(n)
        return out

    async def _resolve_target_canonical(self, target: str) -> str:
        """Valida que o centro de destino existe (fixo ou projeto) e retorna nome canônico."""
        cc = " ".join(str(target or "").strip().split())
        if not cc:
            raise ValueError("Centro de custo de destino é obrigatório.")
        lowered = cc.casefold()
        for fixed in MANUAL_PAYABLE_FIXED_COST_CENTERS:
            if fixed.casefold() == lowered:
                return fixed
        exact = (
            await self.session.execute(
                select(Project.name).where(Project.deleted_at.is_(None), Project.name == cc).limit(1)
            )
        ).scalar_one_or_none()
        if exact:
            return str(exact)
        insensitive = (
            await self.session.execute(
                select(Project.name).where(
                    Project.deleted_at.is_(None),
                    func.lower(Project.name) == lowered,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if insensitive:
            return str(insensitive)
        raise ValueError(
            "Centro de custo de destino inválido. Use «Administrativo», «Financeiro» "
            "ou o nome exato de um projeto cadastrado."
        )

    def _lookup_session_override(self, raw: str, session_overrides: dict[str, str]) -> str | None:
        if not session_overrides:
            return None
        norm = normalize_alias(raw)
        for key, target in session_overrides.items():
            if normalize_alias(key) == norm:
                return target
        return None

    async def _is_direct_match(self, raw: str) -> str | None:
        """Match nativo SGP (fixo ou projeto), sem alias."""
        cc = " ".join(str(raw or "").strip().split())
        if not cc:
            return None
        lowered = cc.casefold()
        for fixed in MANUAL_PAYABLE_FIXED_COST_CENTERS:
            if fixed.casefold() == lowered:
                return fixed
        exact = (
            await self.session.execute(
                select(Project.name).where(Project.deleted_at.is_(None), Project.name == cc).limit(1)
            )
        ).scalar_one_or_none()
        if exact:
            return str(exact)
        insensitive = (
            await self.session.execute(
                select(Project.name).where(
                    Project.deleted_at.is_(None),
                    func.lower(Project.name) == lowered,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if insensitive:
            return str(insensitive)
        return None

    async def _lookup_alias_row(self, raw: str) -> str | None:
        norm = normalize_alias(raw)
        if not norm:
            return None
        row = (
            await self.session.execute(
                select(CostCenterAlias.target_cost_center).where(
                    CostCenterAlias.alias_name_normalized == norm
                ).limit(1)
            )
        ).scalar_one_or_none()
        return str(row) if row else None

    async def resolve_cost_center_name(
        self,
        raw: str,
        *,
        session_overrides: dict[str, str] | None = None,
    ) -> CostCenterResolveResult:
        cc = " ".join(str(raw or "").strip().split())
        if not cc:
            raise ValueError("Centro de custo é obrigatório.")

        direct = await self._is_direct_match(cc)
        if direct is not None:
            return CostCenterResolveResult(target=direct, alias_applied=False)

        override_target = self._lookup_session_override(cc, session_overrides or {})
        if override_target is not None:
            canonical = await self._resolve_target_canonical(override_target)
            return CostCenterResolveResult(target=canonical, alias_applied=True)

        alias_target = await self._lookup_alias_row(cc)
        if alias_target is not None:
            canonical = await self._resolve_target_canonical(alias_target)
            return CostCenterResolveResult(target=canonical, alias_applied=True)

        raise ValueError(
            "Centro de custo não reconhecido. "
            "Use «Administrativo», «Financeiro», o nome exato de um projeto ou cadastre um alias (DE-PARA)."
        )

    async def list_aliases(self) -> list[CostCenterAlias]:
        return list(
            (
                await self.session.execute(
                    select(CostCenterAlias).order_by(CostCenterAlias.alias_name.asc())
                )
            ).scalars().all()
        )

    async def create_alias(
        self,
        *,
        alias_name: str,
        target_cost_center: str,
        created_by_user_id: UUID | None = None,
    ) -> CostCenterAlias:
        display = " ".join(str(alias_name or "").strip().split())
        if not display:
            raise ValueError("Alias não pode ser vazio.")
        norm = normalize_alias(display)
        if not norm:
            raise ValueError("Alias não pode ser vazio.")

        canonical_target = await self._resolve_target_canonical(target_cost_center)
        if normalize_alias(canonical_target) == norm:
            raise ValueError("O alias não pode ser igual ao nome oficial do centro de custo.")

        existing = await self._lookup_alias_row(display)
        if existing is not None:
            raise ValueError("Já existe um alias com este nome.")

        row = CostCenterAlias(
            alias_name=display,
            alias_name_normalized=norm,
            target_cost_center=canonical_target,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise ValueError("Já existe um alias com este nome.") from exc
        return row

    async def delete_alias(self, alias_id: UUID) -> bool:
        row = await self.session.get(CostCenterAlias, alias_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
