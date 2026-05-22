from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset import (
    Asset,
    AssetAssignment,
    AssetAttachment,
    AssetAttachmentType,
    AssetInspection,
    AssetPhysicalCondition,
    AssetStatus,
)
from app.models.employee import Employee
from app.models.project import Project
from app.schemas.assets import (
    AssetAssignmentCreate,
    AssetAssignmentRead,
    AssetAssignmentReturn,
    AssetAssignmentReturnUpdate,
    AssetAttachmentRead,
    AssetCreate,
    AssetDetail,
    AssetInspectionCreate,
    AssetInspectionRead,
    AssetListItem,
    AssetRead,
    AssetTimelineEvent,
    AssetUpdate,
    ExpirationAlertLevel,
)
from app.services.company_finance_cost_center import (
    CC_LABEL_ADMINISTRATIVO,
    CC_LABEL_FINANCEIRO,
    CC_LABEL_RH,
    CC_SYSTEM_ADMINISTRATIVO,
    CC_SYSTEM_FINANCEIRO,
    CC_SYSTEM_LABELS,
    CC_SYSTEM_RH,
    CompanyFinanceCostCenterService,
)

from app.services.asset_categories import (
    ASSET_MACRO_CATEGORIES,
    _LEGACY_TO_MACRO,
    normalize_macro_category,
    normalize_tags,
)

ASSET_CODE_PREFIX = "ASSET-"
_ASSET_CODE_RE = re.compile(r"^ASSET-(\d+)$", re.IGNORECASE)
_ASSET_CODE_MAX_ATTEMPTS = 3


def _format_asset_code(sequence: int) -> str:
    return f"{ASSET_CODE_PREFIX}{sequence:05d}"


def _integrity_error_is_asset_code_duplicate(exc: IntegrityError) -> bool:
    parts: list[str] = [str(exc).lower()]
    orig = getattr(exc, "orig", None)
    if orig is not None:
        parts.append(str(orig).lower())
    blob = " ".join(parts)
    return "ix_assets_asset_code" in blob or "asset_code" in blob


async def _generate_asset_code(db: AsyncSession) -> str:
    """
    Próximo código patrimonial sequencial.

    Considera todos os registros (inclui soft delete) para nunca reutilizar código.
    """
    row = (
        await db.execute(
            text(
                """
                SELECT COALESCE(MAX(
                    (regexp_match(asset_code, '^ASSET-([0-9]+)$', 'i'))[1]::integer
                ), 0)
                FROM assets
                """
            )
        )
    ).scalar_one()
    max_n = int(row or 0)
    return _format_asset_code(max_n + 1)


def expiration_alert_level(expiration_date: date | None, *, today: date | None = None) -> ExpirationAlertLevel | None:
    if expiration_date is None:
        return None
    today = today or date.today()
    if expiration_date < today:
        return ExpirationAlertLevel.RED
    delta = (expiration_date - today).days
    if delta == 1:
        return ExpirationAlertLevel.TOMORROW
    if delta <= 7:
        return ExpirationAlertLevel.ORANGE
    if delta <= 30:
        return ExpirationAlertLevel.YELLOW
    return ExpirationAlertLevel.NORMAL


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    last_day = monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


class AssetsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._cc = CompanyFinanceCostCenterService(db)

    @staticmethod
    def categories_meta() -> list[str]:
        return list(ASSET_MACRO_CATEGORIES)

    @staticmethod
    def _asset_tags(asset: Asset) -> list[str] | None:
        raw = asset.tags
        if not raw or not isinstance(raw, list):
            return None
        return [str(t) for t in raw if str(t).strip()] or None

    @staticmethod
    def _category_filter_values(category: str) -> set[str]:
        norm = normalize_macro_category(category)
        values = {norm, category.strip()}
        for leg, macro in _LEGACY_TO_MACRO.items():
            if macro == norm:
                values.add(leg)
                values.add(macro)
        return values

    async def _generate_asset_code(self) -> str:
        return await _generate_asset_code(self.db)

    async def _employee_name(self, employee_id: UUID | None) -> str | None:
        if employee_id is None:
            return None
        row = await self.db.get(Employee, employee_id)
        return str(row.full_name).strip() if row else None

    def _asset_cost_center_ref(self, asset: Asset) -> str | None:
        if asset.cost_center_project_id is not None:
            return str(asset.cost_center_project_id)
        if asset.cost_center_system in CC_SYSTEM_LABELS:
            return str(asset.cost_center_system)
        return None

    async def _asset_cost_center_label(self, asset: Asset) -> str | None:
        if asset.cost_center_project_id is not None:
            proj = await self.db.get(Project, asset.cost_center_project_id)
            if proj is not None:
                return str(proj.name).strip()
        if asset.cost_center_system in CC_SYSTEM_LABELS:
            return CC_SYSTEM_LABELS[asset.cost_center_system]
        return (asset.cost_center or "").strip() or None

    async def _apply_cost_center_ref(self, asset: Asset, ref: str | None) -> None:
        if ref is None:
            return
        ref = str(ref).strip()
        if not ref:
            return
        if ref == CC_SYSTEM_ADMINISTRATIVO:
            asset.cost_center_project_id = None
            asset.cost_center_system = CC_SYSTEM_ADMINISTRATIVO
            asset.cost_center = CC_LABEL_ADMINISTRATIVO
            return
        if ref == CC_SYSTEM_FINANCEIRO:
            asset.cost_center_project_id = None
            asset.cost_center_system = CC_SYSTEM_FINANCEIRO
            asset.cost_center = CC_LABEL_FINANCEIRO
            return
        if ref == CC_SYSTEM_RH:
            asset.cost_center_project_id = None
            asset.cost_center_system = CC_SYSTEM_RH
            asset.cost_center = CC_LABEL_RH
            return
        project_id = UUID(ref)
        proj = await self.db.get(Project, project_id)
        if proj is None or getattr(proj, "deleted_at", None) is not None:
            raise ValueError("Projeto não encontrado para o centro de custo selecionado.")
        asset.cost_center_project_id = project_id
        asset.cost_center_system = None
        asset.cost_center = str(proj.name).strip()

    async def _inspection_validity_meta(self, asset_id: UUID) -> tuple[bool, date | None, ExpirationAlertLevel | None]:
        """
        Controle de validade só existe se houver ao menos um ensaio/inspeção com data de validade.
        """
        exp = (
            await self.db.execute(
                select(func.max(AssetInspection.expiration_date)).where(
                    AssetInspection.asset_id == asset_id,
                    AssetInspection.deleted_at.is_(None),
                    AssetInspection.expiration_date.isnot(None),
                )
            )
        ).scalar_one()
        if exp is None:
            return False, None, None
        return True, exp, expiration_alert_level(exp)

    async def _open_assignment(self, asset_id: UUID) -> AssetAssignment | None:
        stmt = (
            select(AssetAssignment)
            .where(
                AssetAssignment.asset_id == asset_id,
                AssetAssignment.return_date.is_(None),
                AssetAssignment.deleted_at.is_(None),
            )
            .order_by(AssetAssignment.delivery_date.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalars().first()

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        if value is None:
            return None
        return float(value)

    async def _assignment_to_read(self, row: AssetAssignment) -> AssetAssignmentRead:
        return AssetAssignmentRead(
            id=row.id,
            asset_id=row.asset_id,
            employee_id=row.employee_id,
            employee_name=(await self._employee_name(row.employee_id)) or "—",
            delivered_by_employee_id=row.delivered_by_employee_id,
            delivered_by_name=await self._employee_name(row.delivered_by_employee_id),
            delivery_date=row.delivery_date,
            return_date=row.return_date,
            returned_by_employee_id=row.returned_by_employee_id,
            returned_by_name=await self._employee_name(row.returned_by_employee_id),
            returned_to_employee_id=row.returned_to_employee_id,
            returned_to_name=await self._employee_name(row.returned_to_employee_id),
            returned_condition=row.returned_condition,
            return_notes=row.return_notes,
            notes=row.notes,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _asset_to_list_item(self, asset: Asset) -> AssetListItem:
        open_a = await self._open_assignment(asset.id)
        has_insp, exp, alert = await self._inspection_validity_meta(asset.id)
        holder_id = open_a.employee_id if open_a else None
        holder_name = await self._employee_name(holder_id) if holder_id else None
        return AssetListItem(
            id=asset.id,
            asset_code=asset.asset_code,
            name=asset.name,
            category=asset.category,
            subcategory=asset.subcategory,
            size=(asset.size or "").strip() or None,
            status=asset.status,
            physical_condition=asset.physical_condition,
            purchase_value=self._float_or_none(asset.purchase_value),
            cost_center_label=await self._asset_cost_center_label(asset),
            cost_center_ref=self._asset_cost_center_ref(asset),
            current_holder_id=holder_id,
            current_holder_name=holder_name,
            has_inspection_control=has_insp,
            next_expiration_date=exp,
            expiration_alert=alert,
        )

    async def list_assets(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        status: AssetStatus | None = None,
        employee_id: UUID | None = None,
        cost_center_ref: str | None = None,
        expiration: str | None = None,
        size: str | None = None,
        without_holder: bool | None = None,
        physical_condition: AssetPhysicalCondition | None = None,
    ) -> list[AssetListItem]:
        stmt = select(Asset).where(Asset.deleted_at.is_(None)).order_by(Asset.asset_code.asc())
        if category:
            cats = self._category_filter_values(category)
            stmt = stmt.where(Asset.category.in_(list(cats)))
        if status:
            stmt = stmt.where(Asset.status == status)
        if size:
            stmt = stmt.where(Asset.size.ilike(size.strip()))
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Asset.name.ilike(like),
                    Asset.asset_code.ilike(like),
                    Asset.serial_number.ilike(like),
                    Asset.patrimony_tag.ilike(like),
                    Asset.size.ilike(like),
                    cast(Asset.tags, String).ilike(like),
                )
            )
        if cost_center_ref:
            ref = cost_center_ref.strip()
            if ref in CC_SYSTEM_LABELS:
                stmt = stmt.where(Asset.cost_center_system == ref, Asset.cost_center_project_id.is_(None))
            else:
                try:
                    pid = UUID(ref)
                    stmt = stmt.where(Asset.cost_center_project_id == pid)
                except ValueError:
                    pass
        if employee_id:
            open_ids = (
                select(AssetAssignment.asset_id)
                .where(
                    AssetAssignment.employee_id == employee_id,
                    AssetAssignment.return_date.is_(None),
                    AssetAssignment.deleted_at.is_(None),
                )
                .distinct()
            )
            stmt = stmt.where(Asset.id.in_(open_ids))
        if without_holder:
            open_assignment_ids = select(AssetAssignment.asset_id).where(
                AssetAssignment.return_date.is_(None),
                AssetAssignment.deleted_at.is_(None),
            )
            stmt = stmt.where(
                Asset.id.not_in(open_assignment_ids),
                Asset.status.not_in((AssetStatus.LOST, AssetStatus.DISCARDED)),
            )
        if physical_condition is not None:
            stmt = stmt.where(Asset.physical_condition == physical_condition)

        rows = list((await self.db.execute(stmt)).scalars().all())
        items: list[AssetListItem] = []
        today = date.today()
        for asset in rows:
            item = await self._asset_to_list_item(asset)
            if expiration:
                if not item.has_inspection_control or item.next_expiration_date is None:
                    continue
                exp = item.next_expiration_date
                delta = (exp - today).days
                if expiration == "expired" and exp >= today:
                    continue
                if expiration == "30" and not (0 <= delta <= 30):
                    continue
                if expiration == "7" and not (1 < delta <= 7):
                    continue
                if expiration == "tomorrow" and delta != 1:
                    continue
            items.append(item)
        return items

    async def get_asset(self, asset_id: UUID) -> Asset | None:
        stmt = select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
        return (await self.db.execute(stmt)).scalars().first()

    async def create_asset(self, payload: AssetCreate) -> AssetRead:
        last_error: IntegrityError | None = None
        asset: Asset | None = None

        for _ in range(_ASSET_CODE_MAX_ATTEMPTS):
            candidate = Asset(
                asset_code=await self._generate_asset_code(),
                name=payload.name.strip(),
                category=payload.category.strip(),
                subcategory=(payload.subcategory or "").strip() or None,
                tags=normalize_tags(payload.tags),
                size=(payload.size or "").strip() or None,
                description=payload.description,
                brand=payload.brand,
                model=payload.model,
                serial_number=payload.serial_number,
                patrimony_tag=payload.patrimony_tag,
                imei=payload.imei,
                ca_number=payload.ca_number,
                status=payload.status,
                physical_condition=payload.physical_condition,
                acquisition_date=payload.acquisition_date,
                purchase_value=payload.purchase_value,
                notes=payload.notes,
            )
            await self._apply_cost_center_ref(candidate, payload.cost_center_ref)
            self.db.add(candidate)
            try:
                async with self.db.begin_nested():
                    await self.db.flush()
                asset = candidate
                break
            except IntegrityError as exc:
                last_error = exc
                self.db.expunge(candidate)
                if not _integrity_error_is_asset_code_duplicate(exc):
                    raise ValueError("Não foi possível criar o ativo.") from exc

        if asset is None:
            raise ValueError(
                "Não foi possível gerar código único do ativo. Tente novamente."
            ) from last_error

        base = await self._asset_to_list_item(asset)
        return AssetRead(
            **base.model_dump(),
            tags=self._asset_tags(asset),
            description=asset.description,
            brand=asset.brand,
            model=asset.model,
            serial_number=asset.serial_number,
            patrimony_tag=asset.patrimony_tag,
            imei=asset.imei,
            ca_number=asset.ca_number,
            acquisition_date=asset.acquisition_date,
            notes=asset.notes,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    async def update_asset(self, asset_id: UUID, payload: AssetUpdate) -> AssetRead | None:
        asset = await self.get_asset(asset_id)
        if asset is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        ref = data.pop("cost_center_ref", None)
        if "size" in data:
            raw = data["size"]
            data["size"] = (raw or "").strip() or None if isinstance(raw, str) else raw
        if "tags" in data:
            data["tags"] = normalize_tags(data["tags"])
        if "subcategory" in data:
            raw_sub = data["subcategory"]
            data["subcategory"] = (raw_sub or "").strip() or None if isinstance(raw_sub, str) else raw_sub
        for k, v in data.items():
            setattr(asset, k, v)
        if ref is not None:
            await self._apply_cost_center_ref(asset, ref)
        await self.db.flush()
        base = await self._asset_to_list_item(asset)
        return AssetRead(
            **base.model_dump(),
            tags=self._asset_tags(asset),
            description=asset.description,
            brand=asset.brand,
            model=asset.model,
            serial_number=asset.serial_number,
            patrimony_tag=asset.patrimony_tag,
            imei=asset.imei,
            ca_number=asset.ca_number,
            acquisition_date=asset.acquisition_date,
            notes=asset.notes,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    async def soft_delete_asset(self, asset_id: UUID) -> bool:
        asset = await self.get_asset(asset_id)
        if asset is None:
            return False
        asset.deleted_at = datetime.now(timezone.utc)
        return True

    async def get_detail(self, asset_id: UUID) -> AssetDetail | None:
        asset = await self.get_asset(asset_id)
        if asset is None:
            return None
        assignments_active = list(
            (
                await self.db.execute(
                    select(AssetAssignment)
                    .where(AssetAssignment.asset_id == asset_id, AssetAssignment.deleted_at.is_(None))
                    .order_by(AssetAssignment.delivery_date.desc(), AssetAssignment.created_at.desc())
                )
            ).scalars().all()
        )
        assignments_all = list(
            (
                await self.db.execute(
                    select(AssetAssignment)
                    .where(AssetAssignment.asset_id == asset_id)
                    .order_by(AssetAssignment.delivery_date.desc(), AssetAssignment.created_at.desc())
                )
            ).scalars().all()
        )
        inspections_active = list(
            (
                await self.db.execute(
                    select(AssetInspection)
                    .where(AssetInspection.asset_id == asset_id, AssetInspection.deleted_at.is_(None))
                    .order_by(AssetInspection.inspection_date.desc())
                )
            ).scalars().all()
        )
        inspections_all = list(
            (
                await self.db.execute(
                    select(AssetInspection)
                    .where(AssetInspection.asset_id == asset_id)
                    .order_by(AssetInspection.inspection_date.desc())
                )
            ).scalars().all()
        )
        attachments_active = list(
            (
                await self.db.execute(
                    select(AssetAttachment)
                    .where(AssetAttachment.asset_id == asset_id, AssetAttachment.deleted_at.is_(None))
                    .order_by(AssetAttachment.created_at.desc())
                )
            ).scalars().all()
        )
        attachments_all = list(
            (
                await self.db.execute(
                    select(AssetAttachment)
                    .where(AssetAttachment.asset_id == asset_id)
                    .order_by(AssetAttachment.created_at.desc())
                )
            ).scalars().all()
        )

        base_item = await self._asset_to_list_item(asset)
        base = AssetRead(
            **base_item.model_dump(),
            tags=self._asset_tags(asset),
            description=asset.description,
            brand=asset.brand,
            model=asset.model,
            serial_number=asset.serial_number,
            patrimony_tag=asset.patrimony_tag,
            imei=asset.imei,
            ca_number=asset.ca_number,
            acquisition_date=asset.acquisition_date,
            notes=asset.notes,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

        assignment_reads = [await self._assignment_to_read(a) for a in assignments_active]
        inspection_reads = [
            AssetInspectionRead(
                id=i.id,
                asset_id=i.asset_id,
                inspection_type=i.inspection_type,
                inspection_date=i.inspection_date,
                expiration_months=i.expiration_months,
                expiration_date=i.expiration_date,
                responsible_company=i.responsible_company,
                report_attachment_id=i.report_attachment_id,
                notes=i.notes,
                expiration_alert=expiration_alert_level(i.expiration_date),
                created_at=i.created_at,
                updated_at=i.updated_at,
            )
            for i in inspections_active
        ]
        attachment_reads = [
            AssetAttachmentRead(
                id=a.id,
                asset_id=a.asset_id,
                file_name=a.file_name,
                file_type=a.file_type,
                mime_type=a.mime_type,
                created_at=a.created_at,
                download_url=f"assets/{asset_id}/attachments/{a.id}/download",
            )
            for a in attachments_active
        ]

        timeline: list[AssetTimelineEvent] = []
        for a in assignments_all:
            name = await self._employee_name(a.employee_id) or "—"
            timeline.append(
                AssetTimelineEvent(
                    kind="assignment",
                    at=datetime.combine(a.delivery_date, datetime.min.time(), tzinfo=timezone.utc),
                    title=f"Entrega para {name}",
                    detail=a.notes,
                )
            )
            if a.return_date:
                timeline.append(
                    AssetTimelineEvent(
                        kind="return",
                        at=datetime.combine(a.return_date, datetime.min.time(), tzinfo=timezone.utc),
                        title=f"Devolução de {name}",
                        detail=a.notes,
                    )
                )
            if a.deleted_at is not None:
                delivered = await self._employee_name(a.delivered_by_employee_id) or "—"
                timeline.append(
                    AssetTimelineEvent(
                        kind="deleted",
                        at=a.deleted_at,
                        title=f"Movimentação removida: {delivered} → {name}",
                        detail=None,
                    )
                )
        for i in inspections_all:
            timeline.append(
                AssetTimelineEvent(
                    kind="inspection",
                    at=datetime.combine(i.inspection_date, datetime.min.time(), tzinfo=timezone.utc),
                    title=f"Ensaio/inspeção: {i.inspection_type}",
                    detail=i.notes,
                )
            )
            if i.deleted_at is not None:
                timeline.append(
                    AssetTimelineEvent(
                        kind="deleted",
                        at=i.deleted_at,
                        title=f"Ensaio removido: {i.inspection_type}",
                        detail=None,
                    )
                )
        for att in attachments_all:
            timeline.append(
                AssetTimelineEvent(
                    kind="attachment",
                    at=att.created_at,
                    title=f"Anexo: {att.file_name}",
                    detail=att.file_type.value,
                )
            )
            if att.deleted_at is not None:
                timeline.append(
                    AssetTimelineEvent(
                        kind="deleted",
                        at=att.deleted_at,
                        title=f"Anexo removido: {att.file_name}",
                        detail=None,
                    )
                )
        if asset.deleted_at is not None:
            timeline.append(
                AssetTimelineEvent(
                    kind="deleted",
                    at=asset.deleted_at,
                    title=f"Ativo removido: {asset.name}",
                    detail=None,
                )
            )
        timeline.sort(key=lambda e: e.at, reverse=True)

        return AssetDetail(
            **base.model_dump(),
            assignments=assignment_reads,
            inspections=inspection_reads,
            attachments=attachment_reads,
            timeline=timeline,
        )

    async def create_assignment(self, asset_id: UUID, payload: AssetAssignmentCreate) -> AssetAssignmentRead | None:
        asset = await self.get_asset(asset_id)
        if asset is None:
            return None
        if await self._open_assignment(asset_id) is not None:
            raise ValueError("Ativo já possui responsável ativo. Registre a devolução antes de nova entrega.")
        if payload.employee_id == payload.delivered_by_employee_id:
            raise ValueError("Entregador e recebedor devem ser colaboradores distintos.")
        row = AssetAssignment(
            asset_id=asset_id,
            employee_id=payload.employee_id,
            delivered_by_employee_id=payload.delivered_by_employee_id,
            received_by_employee_id=payload.employee_id,
            delivery_date=payload.delivery_date,
            notes=payload.notes,
        )
        self.db.add(row)
        if asset.status == AssetStatus.AVAILABLE:
            asset.status = AssetStatus.IN_USE
        await self.db.flush()
        return await self._assignment_to_read(row)

    async def _get_assignment(
        self, asset_id: UUID, assignment_id: UUID, *, require_active: bool = True
    ) -> AssetAssignment | None:
        stmt = select(AssetAssignment).where(
            AssetAssignment.id == assignment_id,
            AssetAssignment.asset_id == asset_id,
        )
        if require_active:
            stmt = stmt.where(AssetAssignment.deleted_at.is_(None))
        return (await self.db.execute(stmt)).scalars().first()

    async def _sync_asset_physical_condition_from_returns(self, asset_id: UUID) -> None:
        asset = await self.get_asset(asset_id)
        if asset is None:
            return
        last = (
            await self.db.execute(
                select(AssetAssignment)
                .where(
                    AssetAssignment.asset_id == asset_id,
                    AssetAssignment.deleted_at.is_(None),
                    AssetAssignment.return_date.isnot(None),
                    AssetAssignment.returned_condition.isnot(None),
                )
                .order_by(AssetAssignment.return_date.desc(), AssetAssignment.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        asset.physical_condition = last.returned_condition if last else None

    async def return_assignment(
        self, asset_id: UUID, assignment_id: UUID, payload: AssetAssignmentReturn
    ) -> AssetAssignmentRead | None:
        row = await self._get_assignment(asset_id, assignment_id)
        if row is None:
            return None
        if row.return_date is not None:
            raise ValueError("Devolução já registrada. Use editar devolução.")
        if payload.return_date < row.delivery_date:
            raise ValueError("Data de devolução não pode ser anterior à entrega.")
        row.return_date = payload.return_date
        row.returned_by_employee_id = row.employee_id
        row.returned_to_employee_id = payload.returned_to_employee_id
        row.returned_condition = payload.returned_condition
        row.return_notes = (payload.return_notes or "").strip() or None
        asset = await self.get_asset(asset_id)
        if asset:
            asset.physical_condition = payload.returned_condition
            if asset.status == AssetStatus.IN_USE:
                asset.status = AssetStatus.AVAILABLE
        await self.db.flush()
        return await self._assignment_to_read(row)

    async def update_return_assignment(
        self, asset_id: UUID, assignment_id: UUID, payload: AssetAssignmentReturnUpdate
    ) -> AssetAssignmentRead | None:
        row = await self._get_assignment(asset_id, assignment_id)
        if row is None:
            return None
        if row.return_date is None:
            raise ValueError("Esta movimentação ainda não possui devolução registrada.")
        data = payload.model_dump(exclude_unset=True)
        if "return_date" in data and data["return_date"] is not None:
            if data["return_date"] < row.delivery_date:
                raise ValueError("Data de devolução não pode ser anterior à entrega.")
            row.return_date = data["return_date"]
        if "returned_to_employee_id" in data and data["returned_to_employee_id"] is not None:
            row.returned_to_employee_id = data["returned_to_employee_id"]
        if "returned_condition" in data and data["returned_condition"] is not None:
            row.returned_condition = data["returned_condition"]
        if "return_notes" in data:
            row.return_notes = (data["return_notes"] or "").strip() or None
        await self._sync_asset_physical_condition_from_returns(asset_id)
        await self.db.flush()
        return await self._assignment_to_read(row)

    async def delete_return_assignment(self, asset_id: UUID, assignment_id: UUID) -> AssetAssignmentRead | None:
        row = await self._get_assignment(asset_id, assignment_id)
        if row is None:
            return None
        if row.return_date is None:
            raise ValueError("Esta movimentação não possui devolução.")
        row.return_date = None
        row.returned_by_employee_id = None
        row.returned_to_employee_id = None
        row.returned_condition = None
        row.return_notes = None
        asset = await self.get_asset(asset_id)
        if asset:
            await self._sync_asset_physical_condition_from_returns(asset_id)
            asset.status = AssetStatus.IN_USE
        await self.db.flush()
        return await self._assignment_to_read(row)

    async def soft_delete_assignment(self, asset_id: UUID, assignment_id: UUID) -> bool:
        row = (
            await self.db.execute(
                select(AssetAssignment).where(
                    AssetAssignment.id == assignment_id,
                    AssetAssignment.asset_id == asset_id,
                    AssetAssignment.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if row is None:
            return False
        if row.return_date is None:
            asset = await self.get_asset(asset_id)
            if asset and asset.status == AssetStatus.IN_USE:
                asset.status = AssetStatus.AVAILABLE
        row.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True

    async def soft_delete_inspection(self, asset_id: UUID, inspection_id: UUID) -> bool:
        row = (
            await self.db.execute(
                select(AssetInspection).where(
                    AssetInspection.id == inspection_id,
                    AssetInspection.asset_id == asset_id,
                    AssetInspection.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if row is None:
            return False
        row.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True

    async def create_inspection(self, asset_id: UUID, payload: AssetInspectionCreate) -> AssetInspectionRead | None:
        if await self.get_asset(asset_id) is None:
            return None
        exp_date = payload.expiration_date
        if exp_date is None and payload.expiration_months:
            exp_date = _add_months(payload.inspection_date, payload.expiration_months)
        row = AssetInspection(
            asset_id=asset_id,
            inspection_type=payload.inspection_type.strip(),
            inspection_date=payload.inspection_date,
            expiration_months=payload.expiration_months,
            expiration_date=exp_date,
            responsible_company=payload.responsible_company,
            report_attachment_id=payload.report_attachment_id,
            notes=payload.notes,
        )
        self.db.add(row)
        await self.db.flush()
        return AssetInspectionRead(
            id=row.id,
            asset_id=row.asset_id,
            inspection_type=row.inspection_type,
            inspection_date=row.inspection_date,
            expiration_months=row.expiration_months,
            expiration_date=row.expiration_date,
            responsible_company=row.responsible_company,
            report_attachment_id=row.report_attachment_id,
            notes=row.notes,
            expiration_alert=expiration_alert_level(row.expiration_date),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def attachment_base_dir(self) -> Path:
        base = Path(settings.asset_upload_dir).resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base

    async def save_attachment(
        self,
        asset_id: UUID,
        *,
        file_name: str,
        body: bytes,
        mime_type: str | None,
        file_type: AssetAttachmentType,
        uploaded_by_user_id: UUID | None,
    ) -> AssetAttachment | None:
        if await self.get_asset(asset_id) is None:
            return None
        file_id = uuid4()
        ext = Path(file_name).suffix or ""
        base = self.attachment_base_dir() / str(asset_id)
        base.mkdir(parents=True, exist_ok=True)
        stored_name = f"{file_id}{ext}"
        dest = (base / stored_name).resolve()
        dest.write_bytes(body)
        rel = str(dest.relative_to(self.attachment_base_dir()))
        row = AssetAttachment(
            id=file_id,
            asset_id=asset_id,
            file_name=file_name[:255],
            file_type=file_type,
            stored_path=rel,
            mime_type=mime_type,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def get_attachment(self, asset_id: UUID, attachment_id: UUID) -> AssetAttachment | None:
        stmt = select(AssetAttachment).where(
            AssetAttachment.id == attachment_id,
            AssetAttachment.asset_id == asset_id,
            AssetAttachment.deleted_at.is_(None),
        )
        return (await self.db.execute(stmt)).scalars().first()

    def attachment_disk_path(self, row: AssetAttachment) -> Path:
        return (self.attachment_base_dir() / row.stored_path).resolve()

    async def delete_attachment(self, asset_id: UUID, attachment_id: UUID) -> bool:
        row = (
            await self.db.execute(
                select(AssetAttachment).where(
                    AssetAttachment.id == attachment_id,
                    AssetAttachment.asset_id == asset_id,
                    AssetAttachment.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if row is None:
            return False
        row.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True
