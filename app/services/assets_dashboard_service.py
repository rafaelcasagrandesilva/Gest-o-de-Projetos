from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetAssignment, AssetInspection, AssetPhysicalCondition, AssetStatus
from app.models.project import Project
from app.schemas.assets_dashboard import (
    AssetDashboardAlertSummary,
    AssetDashboardAlerts,
    AssetDashboardCountValue,
    AssetDashboardCostCenterRow,
    AssetDashboardGroupRow,
    AssetDashboardPhysicalRow,
    AssetDashboardRead,
    AssetDashboardStatusKpis,
)
from app.services.asset_categories import (
    PATRIMONIAL_MACRO_CATEGORIES,
    is_epi_category,
    normalize_macro_category,
    sqlalchemy_exclude_epi,
)
from app.services.company_finance_cost_center import (
    CC_LABEL_ADMINISTRATIVO,
    CC_LABEL_FINANCEIRO,
    CC_LABEL_RH,
    CC_SYSTEM_ADMINISTRATIVO,
    CC_SYSTEM_FINANCEIRO,
    CC_SYSTEM_RH,
    CC_SYSTEM_LABELS,
)

_CATEGORY_ORDER = list(PATRIMONIAL_MACRO_CATEGORIES)
_SYSTEM_CC_ORDER = [CC_LABEL_ADMINISTRATIVO, CC_LABEL_FINANCEIRO, CC_LABEL_RH]

_PHYSICAL_ORDER: list[tuple[AssetPhysicalCondition, str]] = [
    (AssetPhysicalCondition.NEW, "Novo"),
    (AssetPhysicalCondition.GOOD, "Bom estado"),
    (AssetPhysicalCondition.FAIR, "Mau estado"),
    (AssetPhysicalCondition.DAMAGED, "Quebrado"),
]

def _category_bucket(category: str) -> str:
    return normalize_macro_category(category)


def _cost_center_group(
    *,
    project_id: UUID | None,
    system: str | None,
    project_name: str | None,
    cost_center_label: str | None,
) -> tuple[str, str]:
    """Retorna (key estável, rótulo exibido)."""
    if project_id is not None:
        label = (project_name or cost_center_label or "").strip() or f"Projeto {project_id}"
        return str(project_id), label
    sys_key = (system or CC_SYSTEM_ADMINISTRATIVO).strip()
    label = CC_SYSTEM_LABELS.get(sys_key, cost_center_label or CC_LABEL_ADMINISTRATIVO)
    return sys_key, str(label).strip() or CC_LABEL_ADMINISTRATIVO


def _sort_cost_center_rows(rows: list[AssetDashboardCostCenterRow]) -> list[AssetDashboardCostCenterRow]:
    def sort_key(row: AssetDashboardCostCenterRow) -> tuple[int, int | str]:
        if row.label in _SYSTEM_CC_ORDER:
            return (0, _SYSTEM_CC_ORDER.index(row.label))
        return (1, row.label.casefold())

    return sorted(rows, key=sort_key)


def _average_value(amount_total: float, asset_count: int) -> float:
    if asset_count <= 0:
        return 0.0
    return round(amount_total / asset_count, 2)


def _alert_summary(count: int, amount: float, *, damaged_count: int | None = None) -> AssetDashboardAlertSummary:
    return AssetDashboardAlertSummary(
        count=count,
        amount_total=round(amount, 2),
        damaged_count=damaged_count,
    )


def _cv(count: int = 0, value: float = 0.0) -> AssetDashboardCountValue:
    return AssetDashboardCountValue(count=count, value=round(float(value), 2))


class AssetsDashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_dashboard(self) -> AssetDashboardRead:
        today = date.today()
        in_30 = today + timedelta(days=30)
        base = and_(Asset.deleted_at.is_(None), sqlalchemy_exclude_epi(Asset.category))
        pv = func.coalesce(Asset.purchase_value, 0)

        status_rows = (
            await self.db.execute(
                select(Asset.status, func.count(Asset.id), func.sum(pv)).where(base).group_by(Asset.status)
            )
        ).all()

        status_map: dict[AssetStatus, tuple[int, float]] = {}
        total_count = 0
        total_value = 0.0
        for st, cnt, val in status_rows:
            c = int(cnt or 0)
            v = float(val or 0)
            status_map[st] = (c, v)
            total_count += c
            total_value += v

        def sum_status(*statuses: AssetStatus) -> AssetDashboardCountValue:
            c = sum(status_map.get(s, (0, 0.0))[0] for s in statuses)
            v = sum(status_map.get(s, (0, 0.0))[1] for s in statuses)
            return _cv(c, v)

        status_kpis = AssetDashboardStatusKpis(
            total=_cv(total_count, total_value),
            in_use=sum_status(AssetStatus.IN_USE),
            available=sum_status(AssetStatus.AVAILABLE),
            maintenance=sum_status(AssetStatus.MAINTENANCE),
            lost_or_discarded=sum_status(AssetStatus.LOST, AssetStatus.DISCARDED),
        )

        phys_rows = (
            await self.db.execute(
                select(Asset.physical_condition, func.count(Asset.id), func.sum(pv))
                .where(base, Asset.physical_condition.isnot(None))
                .group_by(Asset.physical_condition)
            )
        ).all()
        phys_map = {row[0]: (int(row[1] or 0), float(row[2] or 0)) for row in phys_rows}
        physical_condition = [
            AssetDashboardPhysicalRow(
                condition=cond.value,
                label=label,
                count=phys_map.get(cond, (0, 0.0))[0],
                value=round(phys_map.get(cond, (0, 0.0))[1], 2),
            )
            for cond, label in _PHYSICAL_ORDER
        ]

        asset_rows = (
            await self.db.execute(
                select(
                    Asset.id,
                    Asset.asset_code,
                    Asset.name,
                    Asset.category,
                    Asset.subcategory,
                    Asset.cost_center,
                    Asset.cost_center_system,
                    Asset.cost_center_project_id,
                    Project.name.label("project_name"),
                    Asset.physical_condition,
                    Asset.status,
                    pv,
                )
                .outerjoin(Project, Project.id == Asset.cost_center_project_id)
                .where(base)
            )
        ).all()

        cat_acc: dict[str, tuple[int, float]] = {k: (0, 0.0) for k in _CATEGORY_ORDER}
        cc_acc: dict[str, tuple[str, int, float]] = {}
        fair_count = 0
        fair_value = 0.0
        damaged_count = 0

        for row in asset_rows:
            _id, code, name, category, _subcategory, cc_label, cc_sys, cc_proj, proj_name, phys, st, val = row
            if is_epi_category(str(category)):
                continue
            v = float(val or 0)
            bucket = _category_bucket(str(category))
            if bucket not in cat_acc:
                cat_acc[bucket] = (0, 0.0)
            c0, v0 = cat_acc[bucket]
            cat_acc[bucket] = (c0 + 1, v0 + v)

            cc_key, cc_display = _cost_center_group(
                project_id=cc_proj,
                system=cc_sys,
                project_name=str(proj_name) if proj_name else None,
                cost_center_label=str(cc_label) if cc_label else None,
            )
            if cc_key not in cc_acc:
                cc_acc[cc_key] = (cc_display, 0, 0.0)
            disp, c1, v1 = cc_acc[cc_key]
            cc_acc[cc_key] = (disp, c1 + 1, v1 + v)

            if phys == AssetPhysicalCondition.DAMAGED:
                damaged_count += 1
            if phys == AssetPhysicalCondition.FAIR:
                fair_count += 1
                fair_value += v

        by_category = [
            AssetDashboardGroupRow(key=k, label=k, count=cat_acc[k][0], value=round(cat_acc[k][1], 2))
            for k in _CATEGORY_ORDER
        ]
        by_cost_center = _sort_cost_center_rows(
            [
                AssetDashboardCostCenterRow(
                    key=k,
                    label=cc_acc[k][0],
                    asset_count=cc_acc[k][1],
                    amount_total=round(cc_acc[k][2], 2),
                    average_value=_average_value(cc_acc[k][2], cc_acc[k][1]),
                )
                for k in cc_acc
            ]
        )

        max_exp_sq = (
            select(
                AssetInspection.asset_id.label("asset_id"),
                func.max(AssetInspection.expiration_date).label("max_exp"),
            )
            .where(
                AssetInspection.deleted_at.is_(None),
                AssetInspection.expiration_date.isnot(None),
            )
            .group_by(AssetInspection.asset_id)
            .subquery()
        )

        insp_rows = (
            await self.db.execute(
                select(Asset.id, pv, max_exp_sq.c.max_exp)
                .join(max_exp_sq, max_exp_sq.c.asset_id == Asset.id)
                .where(base)
            )
        ).all()

        expired_count = 0
        expired_value = 0.0
        expiring_count = 0
        expiring_value = 0.0
        for _aid, val, exp in insp_rows:
            if exp is None:
                continue
            exp_d = exp if isinstance(exp, date) else exp
            v = float(val or 0)
            if exp_d < today:
                expired_count += 1
                expired_value += v
            elif today <= exp_d <= in_30:
                expiring_count += 1
                expiring_value += v

        open_ids = select(AssetAssignment.asset_id).where(
            AssetAssignment.return_date.is_(None),
            AssetAssignment.deleted_at.is_(None),
        )
        no_holder_agg = (
            await self.db.execute(
                select(func.count(Asset.id), func.sum(pv))
                .where(
                    base,
                    Asset.id.not_in(open_ids),
                    Asset.status.not_in((AssetStatus.LOST, AssetStatus.DISCARDED)),
                )
            )
        ).one()
        without_count = int(no_holder_agg[0] or 0)
        without_value = float(no_holder_agg[1] or 0)

        return AssetDashboardRead(
            status=status_kpis,
            physical_condition=physical_condition,
            by_category=by_category,
            by_cost_center=by_cost_center,
            alerts=AssetDashboardAlerts(
                expired_inspections=_alert_summary(expired_count, expired_value),
                expiring_inspections=_alert_summary(expiring_count, expiring_value),
                without_holder=_alert_summary(without_count, without_value),
                fair_condition=_alert_summary(
                    fair_count,
                    fair_value,
                    damaged_count=damaged_count if damaged_count > 0 else None,
                ),
            ),
        )
