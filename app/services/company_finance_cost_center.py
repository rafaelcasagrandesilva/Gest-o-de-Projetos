from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_finance import CompanyFinancialItem
from app.models.project import Project

# Identificadores estáveis (persistidos em cost_center_system).
CC_SYSTEM_ADMINISTRATIVO = "ADMINISTRATIVO"
CC_SYSTEM_FINANCEIRO = "FINANCEIRO"

# Rótulos exibidos em Contas a Pagar, dashboards e relatórios.
CC_LABEL_ADMINISTRATIVO = "Administrativo"
CC_LABEL_FINANCEIRO = "Financeiro"

CC_SYSTEM_LABELS: dict[str, str] = {
    CC_SYSTEM_ADMINISTRATIVO: CC_LABEL_ADMINISTRATIVO,
    CC_SYSTEM_FINANCEIRO: CC_LABEL_FINANCEIRO,
}


def default_system_for_tipo(tipo: str) -> str:
    return CC_SYSTEM_FINANCEIRO if tipo == "endividamento" else CC_SYSTEM_ADMINISTRATIVO


def default_label_for_tipo(tipo: str) -> str:
    return CC_SYSTEM_LABELS[default_system_for_tipo(tipo)]


def _normalize_label_key(label: str) -> str:
    return (
        label.strip()
        .casefold()
        .replace("–", "-")
        .replace("—", "-")
    )


def item_cost_center_ref(item: CompanyFinancialItem) -> str:
    pid = getattr(item, "cost_center_project_id", None)
    if pid is not None:
        return str(pid)
    legacy = (getattr(item, "cost_center", None) or "").strip()
    if legacy:
        mapped = _legacy_label_to_system(legacy)
        if mapped:
            return mapped
    system = getattr(item, "cost_center_system", None)
    if system in CC_SYSTEM_LABELS:
        # Só usa código sistêmico se não houver rótulo legado de projeto.
        if not legacy or _legacy_label_to_system(legacy):
            return str(system)
    return default_system_for_tipo(item.tipo)


def _normalize_legacy_label(raw: str | None) -> str:
    return (raw or "").strip()


def _legacy_label_to_system(label: str) -> str | None:
    low = label.casefold()
    if low in {CC_LABEL_ADMINISTRATIVO.casefold(), "admin"}:
        return CC_SYSTEM_ADMINISTRATIVO
    if low in {CC_LABEL_FINANCEIRO.casefold(), "financeiro", "financas"}:
        return CC_SYSTEM_FINANCEIRO
    return None


class CompanyFinanceCostCenterService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _find_project_by_label(self, label: str) -> Project | None:
        legacy = _normalize_legacy_label(label)
        if not legacy:
            return None
        key = _normalize_label_key(legacy)
        stmt = select(Project).where(Project.deleted_at.is_(None)).limit(500)
        for candidate in (await self.db.execute(stmt)).scalars().all():
            if _normalize_label_key(str(candidate.name)) == key:
                return candidate
        return None

    async def resolve_ref(self, item: CompanyFinancialItem) -> str:
        pid = getattr(item, "cost_center_project_id", None)
        if pid is not None:
            return str(pid)
        legacy = _normalize_legacy_label(getattr(item, "cost_center", None))
        if legacy:
            mapped = _legacy_label_to_system(legacy)
            if mapped:
                return mapped
            proj = await self._find_project_by_label(legacy)
            if proj is not None:
                return str(proj.id)
        system = getattr(item, "cost_center_system", None)
        if system in CC_SYSTEM_LABELS:
            return str(system)
        return default_system_for_tipo(item.tipo)

    async def resolve_label(
        self,
        item: CompanyFinancialItem,
        *,
        project: Project | None = None,
    ) -> str:
        pid = getattr(item, "cost_center_project_id", None)
        if pid is not None:
            proj = project
            if proj is None or proj.id != pid:
                proj = await self.db.get(Project, pid)
            if proj is not None and getattr(proj, "deleted_at", None) is None:
                name = str(proj.name).strip()
                if name:
                    return name
        system = getattr(item, "cost_center_system", None)
        if system in CC_SYSTEM_LABELS:
            return CC_SYSTEM_LABELS[system]
        legacy = _normalize_legacy_label(getattr(item, "cost_center", None))
        mapped = _legacy_label_to_system(legacy) if legacy else None
        if mapped:
            return CC_SYSTEM_LABELS[mapped]
        if legacy:
            return legacy
        return default_label_for_tipo(item.tipo)

    async def apply_ref(
        self,
        item: CompanyFinancialItem,
        cost_center_ref: str,
        *,
        allow_inactive_project_id: UUID | None = None,
    ) -> str:
        ref = str(cost_center_ref).strip()
        if not ref:
            raise ValueError("Centro de custo é obrigatório.")

        if ref == CC_SYSTEM_ADMINISTRATIVO:
            item.cost_center_project_id = None
            item.cost_center_system = CC_SYSTEM_ADMINISTRATIVO
            item.cost_center = CC_LABEL_ADMINISTRATIVO
            return CC_LABEL_ADMINISTRATIVO

        if ref == CC_SYSTEM_FINANCEIRO:
            item.cost_center_project_id = None
            item.cost_center_system = CC_SYSTEM_FINANCEIRO
            item.cost_center = CC_LABEL_FINANCEIRO
            return CC_LABEL_FINANCEIRO

        try:
            project_id = UUID(ref)
        except ValueError as exc:
            raise ValueError(
                "Centro de custo inválido. Selecione Administrativo, Financeiro ou um projeto ativo."
            ) from exc

        proj = await self.db.get(Project, project_id)
        if proj is None or getattr(proj, "deleted_at", None) is not None:
            raise ValueError("Projeto não encontrado para o centro de custo selecionado.")

        is_active = bool(getattr(proj, "is_active", False)) and getattr(proj, "closed_at", None) is None
        if not is_active and project_id != allow_inactive_project_id:
            raise ValueError("Selecione um projeto ativo para o centro de custo.")

        label = str(proj.name).strip()
        if not label:
            raise ValueError("Projeto sem nome válido para centro de custo.")

        item.cost_center_project_id = project_id
        item.cost_center_system = None
        item.cost_center = label
        return label

    async def migrate_legacy_row(self, item: CompanyFinancialItem) -> None:
        """Normaliza linhas antigas com texto livre em cost_center."""
        if getattr(item, "cost_center_project_id", None) is not None:
            label = await self.resolve_label(item)
            item.cost_center = label
            return
        if getattr(item, "cost_center_system", None) in CC_SYSTEM_LABELS:
            item.cost_center = CC_SYSTEM_LABELS[item.cost_center_system]
            return

        legacy = _normalize_legacy_label(getattr(item, "cost_center", None))
        system = _legacy_label_to_system(legacy) if legacy else None
        if system:
            item.cost_center_project_id = None
            item.cost_center_system = system
            item.cost_center = CC_SYSTEM_LABELS[system]
            return

        if legacy:
            proj = await self._find_project_by_label(legacy)
            if proj is not None:
                item.cost_center_project_id = proj.id
                item.cost_center_system = None
                item.cost_center = str(proj.name).strip()
                return
            # Texto legado desconhecido: preserva rótulo e aplica fallback estrutural por tipo.
            item.cost_center = legacy

        system = default_system_for_tipo(item.tipo)
        item.cost_center_project_id = None
        item.cost_center_system = system
        if not legacy:
            item.cost_center = CC_SYSTEM_LABELS[system]
