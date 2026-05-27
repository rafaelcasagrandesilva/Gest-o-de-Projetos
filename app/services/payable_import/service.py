from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payable_import_template import PayableImportTemplate
from app.schemas.payable_import import (
    PayableImportAnalyzeResult,
    PayableImportColumnMapping,
    PayableImportConfirmResult,
    PayableImportCostCenterScanResult,
    PayableImportPreviewResult,
    PayableImportTemplateCreate,
    PayableImportTemplateRead,
)
from app.services.payable_import.constants import ANALYZE_SAMPLE_ROWS
from app.services.payable_import.engine import PayableImportEngine
from app.services.payable_import.file_reader import read_raw_sheet, sample_rows, table_from_raw
from app.services.payable_import.legacy import looks_like_legacy_template, parse_legacy_workbook
from app.services.payable_import.mapping import ColumnMapping, suggest_mapping


class PayableManualImportService:
    """Fachada de importação de contas a pagar (legado + mapeamento configurável)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.engine = PayableImportEngine(session)

    # --- Legado (colunas A–F) ---

    async def preview(self, content: bytes, *, filename: str = "") -> PayableImportPreviewResult:
        rows = parse_legacy_workbook(content, filename=filename)
        return await self.engine.preview_rows(
            [(ln, r) for ln, r in rows], legacy_tuple_rows=True
        )

    async def confirm(self, content: bytes, *, filename: str = "") -> PayableImportConfirmResult:
        rows = parse_legacy_workbook(content, filename=filename)
        return await self.engine.confirm_rows(
            [(ln, r) for ln, r in rows], legacy_tuple_rows=True
        )

    # --- Mapeamento configurável ---

    async def analyze(
        self,
        content: bytes,
        *,
        filename: str = "",
        header_row: int = 1,
    ) -> PayableImportAnalyzeResult:
        raw = read_raw_sheet(content=content, filename=filename)
        table = table_from_raw(raw=raw, header_row=header_row)
        suggested = PayableImportColumnMapping.model_validate(suggest_mapping(table.columns))
        legacy = looks_like_legacy_template(raw)
        return PayableImportAnalyzeResult(
            header_row=header_row,
            columns=table.columns,
            sample_rows=sample_rows(table, limit=ANALYZE_SAMPLE_ROWS),
            suggested_mapping=suggested,
            detected_legacy_template=legacy,
            total_data_rows=len(table.rows),
        )

    async def scan_mapped_cost_centers(
        self,
        content: bytes,
        *,
        filename: str = "",
        header_row: int,
        mapping: ColumnMapping,
    ) -> PayableImportCostCenterScanResult:
        mapping.validate()
        raw = read_raw_sheet(content=content, filename=filename)
        table = table_from_raw(raw=raw, header_row=header_row)
        return await self.engine.scan_unknown_cost_centers(table.rows, mapping=mapping)

    async def preview_mapped(
        self,
        content: bytes,
        *,
        filename: str = "",
        header_row: int,
        mapping: ColumnMapping,
        cost_center_resolutions: dict[str, str] | None = None,
    ) -> PayableImportPreviewResult:
        mapping.validate()
        raw = read_raw_sheet(content=content, filename=filename)
        table = table_from_raw(raw=raw, header_row=header_row)
        return await self.engine.preview_rows(
            table.rows,
            mapping=mapping,
            cost_center_resolutions=cost_center_resolutions,
        )

    async def confirm_mapped(
        self,
        content: bytes,
        *,
        filename: str = "",
        header_row: int,
        mapping: ColumnMapping,
        cost_center_resolutions: dict[str, str] | None = None,
    ) -> PayableImportConfirmResult:
        mapping.validate()
        raw = read_raw_sheet(content=content, filename=filename)
        table = table_from_raw(raw=raw, header_row=header_row)
        return await self.engine.confirm_rows(
            table.rows,
            mapping=mapping,
            cost_center_resolutions=cost_center_resolutions,
        )

    # --- Modelos salvos ---

    async def list_templates(self, user_id: UUID) -> list[PayableImportTemplateRead]:
        rows = (
            await self.session.execute(
                select(PayableImportTemplate)
                .where(PayableImportTemplate.user_id == user_id)
                .order_by(PayableImportTemplate.name.asc())
            )
        ).scalars().all()
        return [self._template_to_read(r) for r in rows]

    async def create_template(
        self, user_id: UUID, payload: PayableImportTemplateCreate
    ) -> PayableImportTemplateRead:
        ColumnMapping.from_dict(payload.column_mapping).validate()
        row = PayableImportTemplate(
            user_id=user_id,
            name=payload.name.strip(),
            header_row=payload.header_row,
            column_mapping=payload.column_mapping.model_dump(),
        )
        self.session.add(row)
        await self.session.flush()
        return self._template_to_read(row)

    async def delete_template(self, user_id: UUID, template_id: UUID) -> bool:
        row = await self.session.get(PayableImportTemplate, template_id)
        if row is None or row.user_id != user_id:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    @staticmethod
    def _template_to_read(row: PayableImportTemplate) -> PayableImportTemplateRead:
        return PayableImportTemplateRead(
            id=row.id,
            name=row.name,
            header_row=row.header_row,
            column_mapping=PayableImportColumnMapping.model_validate(row.column_mapping),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def parse_cost_center_resolutions_json(raw: str | None) -> dict[str, str]:
        if raw is None or not str(raw).strip():
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Resoluções de centro de custo inválidas (JSON).") from exc
        if not isinstance(data, dict):
            raise ValueError("Resoluções de centro de custo inválidas.")
        out: dict[str, str] = {}
        for key, value in data.items():
            src = " ".join(str(key or "").strip().split())
            tgt = " ".join(str(value or "").strip().split())
            if src and tgt:
                out[src] = tgt
        return out

    @staticmethod
    def parse_mapping_json(raw: str) -> ColumnMapping:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Mapeamento de colunas inválido (JSON).") from exc
        if not isinstance(data, dict):
            raise ValueError("Mapeamento de colunas inválido.")
        return ColumnMapping.from_dict(data)
