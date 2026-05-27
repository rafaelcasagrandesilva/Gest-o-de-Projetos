from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.models.payable_snapshot_generation import PayableSnapshotGeneration
from app.schemas.payable_import import (
    PayableImportConfirmResult,
    PayableImportCostCenterScanResult,
    PayableImportPreviewResult,
    PayableImportPreviewRow,
)
from app.services.cost_center_alias_service import CostCenterAliasService, normalize_alias
from app.services.payable_import.mapping import (
    ColumnMapping,
    ParsedImportRow,
    extract_mapped_original,
    parse_mapped_row,
)
from app.services.payable_import.normalization import cell_str, normalize_text
from app.services.payable_snapshot_service import PayableSnapshotService
from app.utils.date_utils import normalize_competencia

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DedupeKey:
    name: str
    cost_center: str
    due_date: date
    amount: Decimal


class PayableImportEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.snapshots = PayableSnapshotService(session)
        self.cost_centers = CostCenterAliasService(session)

    def _dedupe_key(self, row: ParsedImportRow) -> _DedupeKey:
        return _DedupeKey(
            name=row.name.strip(),
            cost_center=row.cost_center.strip(),
            due_date=row.due_date,
            amount=row.amount,
        )

    async def resolve_cost_center(
        self,
        raw: str,
        *,
        session_overrides: dict[str, str] | None = None,
    ) -> tuple[str, bool]:
        result = await self.cost_centers.resolve_cost_center_name(
            raw,
            session_overrides=session_overrides,
        )
        return result.target, result.alias_applied

    async def scan_unknown_cost_centers(
        self,
        data_rows: list[tuple[int, dict[str, object] | tuple]],
        *,
        mapping: ColumnMapping | None = None,
        legacy_tuple_rows: bool = False,
    ) -> PayableImportCostCenterScanResult:
        from app.services.payable_import.legacy import parse_legacy_data_row

        seen_norm: set[str] = set()
        unknown: list[str] = []

        for item in data_rows:
            if legacy_tuple_rows:
                _line_number, row_tuple = item  # type: ignore[misc]
                parsed, err, is_empty = parse_legacy_data_row(_line_number, row_tuple)  # type: ignore[arg-type]
            else:
                _line_number, row_dict = item  # type: ignore[misc]
                assert mapping is not None
                parsed, err, is_empty = parse_mapped_row(
                    line_number=_line_number,
                    row=row_dict,  # type: ignore[arg-type]
                    mapping=mapping,
                )

            if is_empty or err or parsed is None:
                continue

            try:
                await self.resolve_cost_center(parsed.cost_center)
            except ValueError:
                norm = normalize_alias(parsed.cost_center)
                if norm and norm not in seen_norm:
                    seen_norm.add(norm)
                    unknown.append(" ".join(parsed.cost_center.strip().split()))

        targets = await self.cost_centers.list_valid_targets()
        return PayableImportCostCenterScanResult(
            unknown_centers=sorted(unknown, key=str.casefold),
            available_targets=targets,
        )

    async def _exists_manual_duplicate(self, key: _DedupeKey) -> bool:
        found = (
            await self.session.execute(
                select(PayableSnapshot.id)
                .where(
                    PayableSnapshot.type == PayableSnapshotType.MANUAL,
                    PayableSnapshot.name == key.name,
                    PayableSnapshot.cost_center == key.cost_center,
                    PayableSnapshot.due_date == key.due_date,
                    PayableSnapshot.amount_final == key.amount,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return found is not None

    async def _ensure_month_allows_manual(self, month: date) -> None:
        comp = normalize_competencia(month)
        if await self.snapshots.is_generated(month=comp):
            return
        self.session.add(PayableSnapshotGeneration(month=comp, created_at=datetime.now(timezone.utc)))
        await self.session.flush()

    def _preview_row_from_parsed(
        self,
        parsed: ParsedImportRow,
        *,
        status: str,
        message: str | None,
        cost_center_resolved: str | None = None,
        alias_applied: bool = False,
        original: dict[str, str | None] | None = None,
    ) -> PayableImportPreviewRow:
        original = original or {}
        return PayableImportPreviewRow(
            line_number=parsed.line_number,
            cost_center=cost_center_resolved,
            alias_applied=alias_applied,
            name=parsed.name,
            due_date=parsed.due_date,
            amount=float(parsed.amount),
            observation=parsed.observation,
            category=parsed.category,
            payment_month=parsed.payment_month,
            status=status,  # type: ignore[arg-type]
            message=message,
            original_name=original.get("original_name"),
            original_cost_center=original.get("original_cost_center"),
            original_due_date=original.get("original_due_date"),
            original_amount=original.get("original_amount"),
            original_category=original.get("original_category"),
            original_observation=original.get("original_observation"),
        )

    def _preview_row_from_original(
        self,
        *,
        line_number: int,
        status: str,
        message: str | None,
        original: dict[str, str | None] | None = None,
    ) -> PayableImportPreviewRow:
        original = original or {}
        return PayableImportPreviewRow(
            line_number=line_number,
            status=status,  # type: ignore[arg-type]
            message=message,
            original_name=original.get("original_name"),
            original_cost_center=original.get("original_cost_center"),
            original_due_date=original.get("original_due_date"),
            original_amount=original.get("original_amount"),
            original_category=original.get("original_category"),
            original_observation=original.get("original_observation"),
        )

    async def preview_rows(
        self,
        data_rows: list[tuple[int, dict[str, object] | tuple]],
        *,
        mapping: ColumnMapping | None = None,
        legacy_tuple_rows: bool = False,
        cost_center_resolutions: dict[str, str] | None = None,
    ) -> PayableImportPreviewResult:
        from app.services.payable_import.legacy import parse_legacy_data_row

        preview_rows: list[PayableImportPreviewRow] = []
        valid = duplicate = errors = empty = 0
        seen_in_file: set[_DedupeKey] = set()

        for item in data_rows:
            if legacy_tuple_rows:
                line_number, row_tuple = item  # type: ignore[misc]
                # Legacy é A–F fixo, a ordem é:
                # A=centro de custo, B=nome, C=vencimento, D=valor, E=observ, F=categoria
                original = {
                    "original_cost_center": cell_str(row_tuple[0]) if len(row_tuple) > 0 else None,
                    "original_name": cell_str(row_tuple[1]) if len(row_tuple) > 1 else None,
                    "original_due_date": (
                        row_tuple[2].strftime("%d/%m/%Y")
                        if len(row_tuple) > 2 and isinstance(row_tuple[2], (date, datetime))
                        else cell_str(row_tuple[2]) if len(row_tuple) > 2 else None
                    ),
                    "original_amount": cell_str(row_tuple[3]) if len(row_tuple) > 3 else None,
                    "original_observation": cell_str(row_tuple[4]) if len(row_tuple) > 4 else None,
                    "original_category": cell_str(row_tuple[5]) if len(row_tuple) > 5 else None,
                }
                parsed, err, is_empty = parse_legacy_data_row(line_number, row_tuple)  # type: ignore[arg-type]
            else:
                line_number, row_dict = item  # type: ignore[misc]
                assert mapping is not None
                original = extract_mapped_original(row_dict, mapping)
                parsed, err, is_empty = parse_mapped_row(
                    line_number=line_number, row=row_dict, mapping=mapping  # type: ignore[arg-type]
                )

            if is_empty:
                empty += 1
                preview_rows.append(
                    self._preview_row_from_original(
                        line_number=line_number,
                        status="empty",
                        message="Linha vazia",
                        original=original,
                    )
                )
                continue
            if err or parsed is None:
                errors += 1
                preview_rows.append(
                    self._preview_row_from_original(
                        line_number=line_number,
                        status="error",
                        message=err,
                        original=original,
                    )
                )
                continue

            try:
                cc_resolved, alias_applied = await self.resolve_cost_center(
                    parsed.cost_center,
                    session_overrides=cost_center_resolutions,
                )
            except ValueError as exc:
                errors += 1
                preview_rows.append(
                    self._preview_row_from_parsed(
                        parsed,
                        status="error",
                        message=str(exc),
                        cost_center_resolved=None,
                        original=original,
                    )
                )
                continue

            key = _DedupeKey(
                name=parsed.name.strip(),
                cost_center=cc_resolved,
                due_date=parsed.due_date,
                amount=parsed.amount,
            )
            if key in seen_in_file:
                duplicate += 1
                preview_rows.append(
                    self._preview_row_from_parsed(
                        parsed,
                        status="duplicate",
                        message="Duplicata na planilha.",
                        cost_center_resolved=cc_resolved,
                        alias_applied=alias_applied,
                        original=original,
                    )
                )
                continue
            seen_in_file.add(key)

            if await self._exists_manual_duplicate(key):
                duplicate += 1
                preview_rows.append(
                    self._preview_row_from_parsed(
                        parsed,
                        status="duplicate",
                        message="Já existe lançamento MANUAL igual.",
                        cost_center_resolved=cc_resolved,
                        alias_applied=alias_applied,
                        original=original,
                    )
                )
                continue

            valid += 1
            preview_rows.append(
                self._preview_row_from_parsed(
                    parsed,
                    status="valid",
                    message=None,
                    cost_center_resolved=cc_resolved,
                    alias_applied=alias_applied,
                    original=original,
                )
            )

        return PayableImportPreviewResult(
            total_rows=len(preview_rows),
            valid_count=valid,
            duplicate_count=duplicate,
            error_count=errors,
            empty_count=empty,
            rows=preview_rows,
        )

    async def confirm_rows(
        self,
        data_rows: list[tuple[int, dict[str, object] | tuple]],
        *,
        mapping: ColumnMapping | None = None,
        legacy_tuple_rows: bool = False,
        cost_center_resolutions: dict[str, str] | None = None,
    ) -> PayableImportConfirmResult:
        from app.services.payable_import.legacy import parse_legacy_data_row

        imported = skipped_duplicate = skipped_empty = errors = 0
        error_details: list[str] = []
        seen_in_file: set[_DedupeKey] = set()
        months_ready: set[date] = set()

        for item in data_rows:
            if legacy_tuple_rows:
                line_number, row_tuple = item  # type: ignore[misc]
                parsed, err, is_empty = parse_legacy_data_row(line_number, row_tuple)  # type: ignore[arg-type]
            else:
                line_number, row_dict = item  # type: ignore[misc]
                assert mapping is not None
                parsed, err, is_empty = parse_mapped_row(
                    line_number=line_number, row=row_dict, mapping=mapping  # type: ignore[arg-type]
                )

            if is_empty:
                skipped_empty += 1
                continue
            if err or parsed is None:
                errors += 1
                if len(error_details) < 50:
                    error_details.append(f"Linha {line_number}: {err}")
                continue

            try:
                cc, _alias_applied = await self.resolve_cost_center(
                    parsed.cost_center,
                    session_overrides=cost_center_resolutions,
                )
            except ValueError as exc:
                errors += 1
                if len(error_details) < 50:
                    error_details.append(f"Linha {line_number}: {exc}")
                continue

            key = _DedupeKey(
                name=parsed.name.strip(),
                cost_center=cc,
                due_date=parsed.due_date,
                amount=parsed.amount,
            )
            if key in seen_in_file:
                skipped_duplicate += 1
                continue
            seen_in_file.add(key)

            if await self._exists_manual_duplicate(key):
                skipped_duplicate += 1
                continue

            comp = parsed.payment_month
            if comp not in months_ready:
                await self._ensure_month_allows_manual(comp)
                months_ready.add(comp)

            try:
                await self.snapshots.create_manual(
                    month=comp,
                    name=parsed.name,
                    category=parsed.category,
                    cost_center=cc,
                    amount=float(parsed.amount),
                    due_date=parsed.due_date,
                    observation=parsed.observation,
                )
                imported += 1
            except ValueError as exc:
                errors += 1
                if len(error_details) < 50:
                    error_details.append(f"Linha {line_number}: {exc}")
            except Exception as exc:
                logger.exception("payables import row failed line=%s", line_number)
                errors += 1
                if len(error_details) < 50:
                    error_details.append(f"Linha {line_number}: {exc}")

        return PayableImportConfirmResult(
            imported=imported,
            skipped_duplicate=skipped_duplicate,
            skipped_empty=skipped_empty,
            errors=errors,
            error_details=error_details,
        )
