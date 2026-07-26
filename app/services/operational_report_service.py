"""Dados para relatórios operacionais (reutiliza services/queries existentes)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import Asset, AssetAssignment, AssetInspection, AssetStatus
from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.models.project import Project
from app.models.user import User
from app.repositories.projects import ProjectRepository
from app.services.assets_service import AssetsService, expiration_alert_level
from app.services.asset_categories import normalize_tags
from app.services.finance_service import FinanceService
from app.services.payable_snapshot_service import (
    SOURCE_TAG_PROJECT_MISC,
    SOURCE_TAG_PROJECT_SYSTEM,
    payable_snapshot_derived_fields,
)
from app.services.receivable_advance_batch_service import ReceivableAdvanceBatchService
from app.services.receivable_manual_service import ReceivableManualService
from app.services.receivable_service import ReceivableService
from app.utils.date_utils import normalize_competencia, previous_competencia

from app.services.payable_display import PAYABLE_TYPE_LABELS as _PAYABLE_TYPE_LABELS


def _yyyy_mm(value: Any) -> str:
    """Competência YYYY-MM a partir de date/datetime/str; vazio se ausente."""
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:7]
    return str(value)[:7]


def _parse_yyyy_mm(raw: str | None) -> date | None:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()
    if len(s) == 7 and s[4] == "-":
        y, m = int(s[0:4]), int(s[5:7])
        return date(y, m, 1)
    if len(s) >= 10 and s[4] == "-":
        return normalize_competencia(date(int(s[0:4]), int(s[5:7]), int(s[8:10])))
    raise HTTPException(status_code=400, detail="Período inválido (use YYYY-MM).")


def _receivable_view_status(*, net_value: float, total_received: float) -> str:
    net = float(net_value or 0.0)
    recv = float(total_received or 0.0)
    if recv <= 0:
        return "ABERTO"
    if recv + 0.01 < net:
        return "PARCIAL"
    return "RECEBIDO"


def _inspection_validity_label(exp: date | None, today: date | None = None) -> tuple[str, int | None]:
    if exp is None:
        return "—", None
    ref = today or date.today()
    days = (exp - ref).days
    if days < 0:
        return "Vencido", days
    if days <= 30:
        return "Vence em 30 dias", days
    return "Em dia", days


def _filter_payable_rows(
    rows: list[PayableSnapshot],
    *,
    project_id: UUID | None,
    status_filter: str | None,
    category: str | None,
    allowed_project_ids: set[UUID] | None,
    sees_all: bool,
) -> list[PayableSnapshot]:
    out: list[PayableSnapshot] = []
    cat_q = (category or "").strip().lower()
    st_q = (status_filter or "").strip().upper()
    for r in rows:
        if not sees_all and allowed_project_ids is not None:
            if r.type == PayableSnapshotType.COLLABORATOR:
                if r.project_id not in allowed_project_ids:
                    continue
            elif r.type not in (
                PayableSnapshotType.VEHICLE,
                PayableSnapshotType.FIXED_COST,
                PayableSnapshotType.ENDIVIDAMENTO,
                PayableSnapshotType.FINANCIAL,
                PayableSnapshotType.MANUAL,
                PayableSnapshotType.ANTECIPACAO,
            ):
                continue
        if project_id is not None and r.project_id != project_id:
            continue
        if cat_q and cat_q not in (r.category or "").lower():
            continue
        derived = payable_snapshot_derived_fields(
            amount_paid=r.amount_paid, amount_final=r.amount_final
        )
        if st_q and str(derived["status"]).upper() != st_q:
            continue
        out.append(r)
    return out


class OperationalReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _project_meta_map(
        self, project_ids: set[UUID]
    ) -> dict[UUID, dict[str, str]]:
        """Mapa projeto → {nome, centro de custo, contrato} para enriquecer NFs.

        Carregado em lote (evita lazy-load em contexto async). Usa apenas dados
        cadastrais já existentes do projeto — nenhuma regra é alterada.
        """
        if not project_ids:
            return {}
        rows = (
            await self.session.execute(select(Project).where(Project.id.in_(project_ids)))
        ).scalars().all()
        return {
            p.id: {
                "nome": p.name or "",
                "centro_custo": p.cost_center or "",
                "contrato": p.contract_number or "",
            }
            for p in rows
        }

    async def _load_payable_snapshots(
        self,
        *,
        month: date | None,
        month_to: date | None,
        accessible_project_ids: set[UUID] | None,
        sees_all_projects: bool,
    ) -> list[PayableSnapshot]:
        fin = FinanceService(self.session)
        if month is None:
            return await fin.payable_snapshots.list_all()

        comp_end = normalize_competencia(month_to or month)
        comp_start = normalize_competencia(month)
        rows: list[PayableSnapshot] = []
        cur = comp_start
        while cur <= comp_end:
            try:
                chunk = await fin.get_or_create_payables_snapshot(
                    month=cur,
                    accessible_project_ids=accessible_project_ids,
                    sees_all_projects=sees_all_projects,
                    force_regenerate=False,
                )
            except ValueError:
                chunk = []
            rows.extend(chunk)
            if cur.year == comp_end.year and cur.month == comp_end.month:
                break
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)

        if not sees_all_projects and accessible_project_ids is not None:
            filtered: list[PayableSnapshot] = []
            for r in rows:
                if r.type in (
                    PayableSnapshotType.VEHICLE,
                    PayableSnapshotType.FIXED_COST,
                    PayableSnapshotType.ENDIVIDAMENTO,
                    PayableSnapshotType.FINANCIAL,
                    PayableSnapshotType.MANUAL,
                    PayableSnapshotType.ANTECIPACAO,
                ):
                    filtered.append(r)
                elif r.type == PayableSnapshotType.COLLABORATOR and r.project_id in accessible_project_ids:
                    filtered.append(r)
            rows = filtered
        return rows

    async def generate_payables_detailed(
        self,
        *,
        filters: dict[str, Any],
        accessible_project_ids: set[UUID] | None,
        sees_all_projects: bool,
    ) -> dict[str, Any]:
        month = _parse_yyyy_mm(filters.get("month"))
        month_to = _parse_yyyy_mm(filters.get("month_to"))
        project_id_raw = filters.get("project_id")
        project_id = UUID(str(project_id_raw)) if project_id_raw else None
        status_filter = str(filters["status"]).strip() if filters.get("status") else None
        category = str(filters["category"]).strip() if filters.get("category") else None

        rows = await self._load_payable_snapshots(
            month=month,
            month_to=month_to,
            accessible_project_ids=accessible_project_ids,
            sees_all_projects=sees_all_projects,
        )
        rows = _filter_payable_rows(
            rows,
            project_id=project_id,
            status_filter=status_filter,
            category=category,
            allowed_project_ids=accessible_project_ids,
            sees_all=sees_all_projects,
        )

        project_names: dict[UUID, str] = {}
        if rows:
            pids = {r.project_id for r in rows if r.project_id}
            if pids:
                proj_rows = (
                    await self.session.execute(select(Project).where(Project.id.in_(pids)))
                ).scalars().all()
                project_names = {p.id: p.name for p in proj_rows}

        out_rows: list[dict[str, Any]] = []
        for r in rows:
            derived = payable_snapshot_derived_fields(
                amount_paid=r.amount_paid, amount_final=r.amount_final
            )
            obs = (r.observation or "")
            comp_month = normalize_competencia(r.month)
            if SOURCE_TAG_PROJECT_MISC in obs or SOURCE_TAG_PROJECT_SYSTEM in obs:
                comp_src = comp_month
            else:
                comp_src = previous_competencia(comp_month)
            tipo = r.type.value if hasattr(r.type, "value") else str(r.type)
            out_rows.append(
                {
                    "nome": r.name,
                    "categoria": r.category,
                    "tipo": _PAYABLE_TYPE_LABELS.get(tipo, tipo),
                    "projeto": project_names.get(r.project_id) or "",
                    "centro_custo": r.cost_center or "",
                    "competencia": comp_src.isoformat()[:7],
                    "vencimento": r.due_date.isoformat(),
                    "mes_pagamento": comp_month.isoformat()[:7],
                    "data_pagamento": r.payment_date.isoformat() if r.payment_date else "",
                    "valor_original": float(r.amount_original or 0),
                    "valor_final": float(r.amount_final or 0),
                    "valor_pago": float(r.amount_paid or 0),
                    "saldo": float(derived["amount_remaining"]),
                    "status": derived["status"],
                    "pago": "Sim" if r.paid else "Não",
                    "no_dashboard": "Sim" if r.include_in_dashboard else "Não",
                    "obsoleto": "Sim" if getattr(r, "is_obsolete", False) else "Não",
                    "motivo_obsolescencia": getattr(r, "obsolete_reason", "") or "",
                    # Descrição do lançamento (subtítulo) na coluna Observações — mesmo padrão
                    # do Endividamento; fallback à observação técnica quando não houver descrição.
                    "observacoes": (getattr(r, "item_description", None) or r.observation or ""),
                }
            )
        return {
            "title": "Contas a pagar — detalhado",
            "filters": filters,
            "rows": out_rows,
        }

    async def generate_receivables_detailed(
        self,
        *,
        filters: dict[str, Any],
        workspace_id: str,
        accessible_project_ids: set[UUID] | None,
        sees_all_projects: bool,
    ) -> dict[str, Any]:
        project_id_raw = filters.get("project_id")
        project_id = UUID(str(project_id_raw)) if project_id_raw else None
        status_filter = str(filters["status"]).strip() if filters.get("status") else None
        client = str(filters["client"]).strip() if filters.get("client") else None
        period_field = str(filters.get("period_field") or "issue")
        year = int(filters["year"]) if filters.get("year") not in (None, "") else None
        month = int(filters["month"]) if filters.get("month") not in (None, "") else None
        if (year is None) != (month is None):
            raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período.")

        svc = ReceivableService(self.session)
        manual_svc = ReceivableManualService(self.session)
        project_ids = None if (project_id is not None or sees_all_projects) else accessible_project_ids

        out_rows: list[dict[str, Any]] = []

        invs = await svc.list_invoices(
            project_id=project_id,
            project_ids=project_ids,
            status=status_filter,
            client_busca=client,
            year=year,
            month=month,
            period_field=period_field,
        )
        proj_meta = await self._project_meta_map({inv.project_id for inv in invs if inv.project_id})
        for inv in invs:
            if (inv.invoice_status or "").upper() == "CANCELADA":
                continue
            r = svc.invoice_to_read(inv)
            net = float(r["net_amount"])
            recv_customer = float(r["received_amount"])
            recv = round(recv_customer, 2)
            remaining = round(max(0.0, net - recv), 2)
            st = _receivable_view_status(net_value=net, total_received=recv)
            if status_filter and st != status_filter and status_filter not in ("EMITIDA", "ANTECIPADA", "RECEBIDA"):
                pass
            pm = proj_meta.get(inv.project_id, {})
            out_rows.append(
                {
                    "nf": r["number"],
                    "cliente": r.get("client_name") or inv.client_name,
                    "projeto": r.get("project_name") or pm.get("nome") or "",
                    "contrato": pm.get("contrato", ""),
                    "centro_custo": pm.get("centro_custo", ""),
                    "competencia": _yyyy_mm(r.get("competence_month")),
                    "emissao": r["issue_date"].isoformat() if hasattr(r["issue_date"], "isoformat") else str(r["issue_date"]),
                    "vencimento": r["due_date"].isoformat() if hasattr(r["due_date"], "isoformat") else str(r["due_date"]),
                    "recebimento": r["received_date"].isoformat() if r.get("received_date") else "",
                    "valor_bruto": float(r["gross_amount"]),
                    "valor": net,
                    "valor_antecipado": float(r["advance_amount_received"]) if r.get("advance_amount_received") is not None else "",
                    "recebido": recv,
                    "saldo": remaining,
                    "status": st,
                    "oficial": "Sim" if r.get("is_official") else "Não",
                    "antecipada": "Sim" if r.get("is_anticipated") else "Não",
                    "instituicao": r.get("institution") or "",
                    "observacoes": r.get("notes") or "",
                    "origem": "Nota fiscal",
                }
            )

        manual_rows = await manual_svc.list(
            workspace_id=workspace_id,
            client=client,
            year=year,
            month=month,
            period_field=period_field,
        )
        for it in manual_rows:
            net = float(it.valor_liquido or 0.0)
            recv = round(float(it.valor_recebido or 0.0), 2)
            remaining = round(max(0.0, net - recv), 2)
            st = str(it.status.value if hasattr(it.status, "value") else it.status)
            out_rows.append(
                {
                    "nf": it.numero_referencia or "—",
                    "cliente": it.cliente,
                    "projeto": "—",
                    "contrato": "",
                    "centro_custo": "",
                    "competencia": _yyyy_mm(it.data_emissao),
                    "emissao": it.data_emissao.isoformat(),
                    "vencimento": it.data_vencimento.isoformat(),
                    "recebimento": "",
                    "valor_bruto": "",
                    "valor": net,
                    "valor_antecipado": "",
                    "recebido": recv,
                    "saldo": remaining,
                    "status": st,
                    "oficial": "",
                    "antecipada": "",
                    "instituicao": "",
                    "observacoes": getattr(it, "observacoes", "") or "",
                    "origem": "Lançamento manual",
                }
            )

        return {
            "title": "Contas a receber — detalhado",
            "filters": filters,
            "rows": out_rows,
        }

    async def generate_invoices_detailed(
        self,
        *,
        filters: dict[str, Any],
        accessible_project_ids: set[UUID] | None,
        sees_all_projects: bool,
    ) -> dict[str, Any]:
        project_id_raw = filters.get("project_id")
        project_id = UUID(str(project_id_raw)) if project_id_raw else None
        st = filters.get("status")
        status_filter = str(st).strip() if st is not None and str(st).strip() != "" else None
        year = int(filters["year"]) if filters.get("year") not in (None, "") else None
        month = int(filters["month"]) if filters.get("month") not in (None, "") else None
        if (year is None) != (month is None):
            raise HTTPException(status_code=400, detail="Informe ano e mês juntos para o período.")

        project_ids = None if (project_id is not None or sees_all_projects) else accessible_project_ids
        svc = ReceivableService(self.session)
        invs = await svc.list_invoices(
            project_id=project_id,
            project_ids=project_ids,
            status=status_filter,
            client_busca=str(filters["client"]).strip() if filters.get("client") else None,
            year=year,
            month=month,
            period_field=str(filters.get("period_field") or "issue"),
        )
        proj_meta = await self._project_meta_map({inv.project_id for inv in invs if inv.project_id})
        # Regra 13: histórico N:N — todas as operações de antecipação relacionadas a cada NF.
        batch_svc = ReceivableAdvanceBatchService(self.session)
        ops_map = await batch_svc.operations_for_invoices([inv.id for inv in invs])
        counts_map = await batch_svc.confirmed_operation_counts([inv.id for inv in invs])
        out_rows: list[dict[str, Any]] = []
        for inv in invs:
            r = svc.invoice_to_read(inv)
            net = float(r["net_amount"])
            recv = float(r["received_amount"])
            saldo = max(0.0, net - recv)
            pm = proj_meta.get(inv.project_id, {})
            ops = ops_map.get(inv.id, [])
            ops_label = "; ".join(
                f"SGC {b.sgc_number} ({b.institution})" if getattr(b, "sgc_number", None) is not None
                else f"{b.batch_number} ({b.institution})"
                for b in ops
            )
            out_rows.append(
                {
                    "numero_nf": r["number"],
                    "cliente": r.get("client_name") or inv.client_name,
                    "projeto": r.get("project_name") or pm.get("nome") or "",
                    "contrato": pm.get("contrato", ""),
                    "centro_custo": pm.get("centro_custo", ""),
                    "competencia": _yyyy_mm(r.get("competence_month")),
                    "emissao": inv.issue_date.isoformat(),
                    "vencimento": inv.due_date.isoformat(),
                    "recebimento": r["received_date"].isoformat() if r.get("received_date") else "",
                    "valor_bruto": float(r["gross_amount"]),
                    "valor": net,
                    "valor_antecipado": float(r["advance_amount_received"]) if r.get("advance_amount_received") is not None else "",
                    "custo_antecipacao": float(r["advance_cost_value"]) if r.get("advance_cost_value") is not None else "",
                    "recebido": recv,
                    "saldo": saldo,
                    "prazo_dias": r.get("due_days") if r.get("due_days") is not None else "",
                    "status": r["status"],
                    "oficial": "Sim" if r.get("is_official") else "Não",
                    "antecipada": "Sim" if r.get("is_anticipated") else "Não",
                    "qtd_operacoes": int(counts_map.get(inv.id, 0)),
                    "operacoes": ops_label,
                    "instituicao": r.get("institution") or "",
                    "venc_antecipacao": r["advance_due_date"].isoformat() if r.get("advance_due_date") else "",
                    "no_dashboard": "Sim" if getattr(inv, "include_in_dashboard", True) else "Não",
                    "observacoes": r.get("notes") or "",
                    "criado_em": r["created_at"].isoformat() if r.get("created_at") else "",
                    "atualizado_em": r["updated_at"].isoformat() if r.get("updated_at") else "",
                }
            )
        return {
            "title": "Notas fiscais — detalhado",
            "filters": filters,
            "rows": out_rows,
        }

    async def generate_assets_inventory(
        self, *, filters: dict[str, Any], include_sensitive: bool = True
    ) -> dict[str, Any]:
        svc = AssetsService(self.session)
        from app.models.asset import AssetPhysicalCondition

        status_raw = filters.get("status")
        status = AssetStatus(str(status_raw)) if status_raw else None
        physical = None
        if filters.get("physical_condition"):
            physical = AssetPhysicalCondition(str(filters["physical_condition"]))
        employee_id = UUID(str(filters["employee_id"])) if filters.get("employee_id") else None

        from app.services.asset_categories import is_epi_category

        cat_raw = str(filters["category"]).strip() if filters.get("category") else None
        only_epi = bool(cat_raw and is_epi_category(cat_raw))
        exclude_epi = not only_epi

        items = await svc.list_assets(
            category=cat_raw,
            status=status,
            employee_id=employee_id,
            cost_center_ref=str(filters["cost_center_ref"]).strip() if filters.get("cost_center_ref") else None,
            physical_condition=physical,
            exclude_epi=exclude_epi,
            only_epi=only_epi,
        )

        asset_ids = [i.id for i in items]
        assets_by_id: dict[UUID, Asset] = {}
        if asset_ids:
            assets = (
                await self.session.execute(
                    select(Asset).where(Asset.id.in_(asset_ids), Asset.deleted_at.is_(None))
                )
            ).scalars().all()
            assets_by_id = {a.id: a for a in assets}

        # Resolve nomes de projeto do centro de custo (cadastro; sem regra nova).
        proj_ids = {a.cost_center_project_id for a in assets_by_id.values() if a.cost_center_project_id}
        proj_meta = await self._project_meta_map(proj_ids)

        rows: list[dict[str, Any]] = []
        for item in items:
            asset = assets_by_id.get(item.id)
            tag_list = normalize_tags(asset.tags if asset else None)
            tags = ", ".join(tag_list) if tag_list else ""
            projeto = ""
            if asset and asset.cost_center_project_id:
                projeto = proj_meta.get(asset.cost_center_project_id, {}).get("nome", "")
            rows.append(
                {
                    "codigo": item.asset_code,
                    "item": item.name,
                    "categoria": item.category,
                    "subcategoria": (asset.subcategory if asset else "") or "",
                    "tamanho": item.size or "",
                    "marca": (asset.brand if asset else "") or "",
                    "modelo": (asset.model if asset else "") or "",
                    "numero_serie": (asset.serial_number if asset else "") or "",
                    "patrimonio": (asset.patrimony_tag if asset else "") or "",
                    "imei": (asset.imei if asset else "") or "",
                    "ca": (asset.ca_number if asset else "") or "",
                    "tags": tags,
                    "descricao": (asset.description if asset else "") or "",
                    "responsavel": item.current_holder_name or "",
                    "centro_custo": item.cost_center_label or "",
                    "projeto": projeto,
                    # Financeiro: omitido sem assets.sensitive (relatório sai sem o valor).
                    "valor": (float(item.purchase_value or 0) if include_sensitive else ""),
                    "status": item.status.value if hasattr(item.status, "value") else str(item.status),
                    "estado_fisico": (
                        item.physical_condition.value
                        if item.physical_condition and hasattr(item.physical_condition, "value")
                        else (str(item.physical_condition) if item.physical_condition else "")
                    ),
                    "data_aquisicao": asset.acquisition_date.isoformat() if (asset and asset.acquisition_date) else "",
                    "observacoes": (asset.notes if asset else "") or "",
                    "criado_em": asset.created_at.isoformat() if (asset and getattr(asset, "created_at", None)) else "",
                    "atualizado_em": asset.updated_at.isoformat() if (asset and getattr(asset, "updated_at", None)) else "",
                }
            )
        return {"title": "Inventário patrimonial", "filters": filters, "rows": rows}

    async def generate_assets_in_use(
        self, *, filters: dict[str, Any], include_sensitive: bool = True
    ) -> dict[str, Any]:
        svc = AssetsService(self.session)
        items = await svc.list_assets(status=AssetStatus.IN_USE)
        asset_ids = [i.id for i in items]
        assets_by_id: dict[UUID, Asset] = {}
        if asset_ids:
            assets = (
                await self.session.execute(
                    select(Asset).where(Asset.id.in_(asset_ids), Asset.deleted_at.is_(None))
                )
            ).scalars().all()
            assets_by_id = {a.id: a for a in assets}
        proj_ids = {a.cost_center_project_id for a in assets_by_id.values() if a.cost_center_project_id}
        proj_meta = await self._project_meta_map(proj_ids)

        rows: list[dict[str, Any]] = []
        for item in items:
            open_a = await svc._open_assignment(item.id)
            asset = assets_by_id.get(item.id)
            projeto = ""
            if asset and asset.cost_center_project_id:
                projeto = proj_meta.get(asset.cost_center_project_id, {}).get("nome", "")
            rows.append(
                {
                    "codigo": item.asset_code,
                    "item": item.name,
                    "marca": (asset.brand if asset else "") or "",
                    "modelo": (asset.model if asset else "") or "",
                    "numero_serie": (asset.serial_number if asset else "") or "",
                    "patrimonio": (asset.patrimony_tag if asset else "") or "",
                    "responsavel": item.current_holder_name or "",
                    "centro_custo": item.cost_center_label or "",
                    "projeto": projeto,
                    "data_entrega": open_a.delivery_date.isoformat() if open_a else "",
                    "status": item.status.value if hasattr(item.status, "value") else str(item.status),
                    "estado_fisico": (
                        item.physical_condition.value
                        if item.physical_condition and hasattr(item.physical_condition, "value")
                        else ""
                    ),
                    # Financeiro: omitido sem assets.sensitive.
                    "valor": (float(item.purchase_value or 0) if include_sensitive else ""),
                }
            )
        return {"title": "Ativos em uso", "filters": filters, "rows": rows}

    async def generate_assets_inspections(self, *, filters: dict[str, Any]) -> dict[str, Any]:
        stmt = (
            select(AssetInspection, Asset)
            .join(Asset, Asset.id == AssetInspection.asset_id)
            .where(AssetInspection.deleted_at.is_(None), Asset.deleted_at.is_(None))
            .order_by(AssetInspection.expiration_date.asc().nullslast(), Asset.asset_code.asc())
        )
        pairs = (await self.session.execute(stmt)).all()
        today = date.today()
        rows: list[dict[str, Any]] = []
        for insp, asset in pairs:
            exp = insp.expiration_date
            validity, days = _inspection_validity_label(exp, today)
            alert = expiration_alert_level(exp) if exp else None
            rows.append(
                {
                    "ativo": f"{asset.asset_code} — {asset.name}",
                    "tipo_inspecao": insp.inspection_type,
                    "data_inspecao": insp.inspection_date.isoformat() if insp.inspection_date else "",
                    "validade": exp.isoformat() if exp else "",
                    "meses_validade": insp.expiration_months if insp.expiration_months is not None else "",
                    "status_validade": validity,
                    "dias_restantes": days if days is not None else "",
                    "responsavel": insp.responsible_company or "",
                    "alerta": alert.value if alert and hasattr(alert, "value") else "",
                    "observacoes": insp.notes or "",
                }
            )
        return {"title": "Inspeções e vencimentos", "filters": filters, "rows": rows}

    async def generate_assets_movements(self, *, filters: dict[str, Any]) -> dict[str, Any]:
        stmt = (
            select(AssetAssignment)
            .where(AssetAssignment.deleted_at.is_(None))
            .options(selectinload(AssetAssignment.asset))
            .order_by(AssetAssignment.delivery_date.desc())
        )
        month = _parse_yyyy_mm(filters.get("month"))
        month_to = _parse_yyyy_mm(filters.get("month_to"))
        if month:
            end = month_to or month
            start_d = month
            last_day = monthrange(end.year, end.month)[1]
            end_d = date(end.year, end.month, last_day)
            stmt = stmt.where(
                AssetAssignment.delivery_date >= start_d,
                AssetAssignment.delivery_date <= end_d,
            )

        svc = AssetsService(self.session)
        assignments = list((await self.session.execute(stmt)).scalars().all())
        rows: list[dict[str, Any]] = []
        for a in assignments:
            asset = a.asset
            asset_label = f"{asset.asset_code} — {asset.name}" if asset else str(a.asset_id)
            rows.append(
                {
                    "ativo": asset_label,
                    "entregador": await svc._employee_name(a.delivered_by_employee_id) or "",
                    "recebedor": await svc._employee_name(a.employee_id) or "",
                    "data_entrega": a.delivery_date.isoformat(),
                    "data_devolucao": a.return_date.isoformat() if a.return_date else "",
                    "responsavel_devolucao": await svc._employee_name(a.returned_to_employee_id) or "",
                    "estado_devolucao": (
                        a.returned_condition.value
                        if a.returned_condition and hasattr(a.returned_condition, "value")
                        else ""
                    ),
                    "observacoes": (a.return_notes or a.notes or "")[:2000],
                    "registrado_em": a.created_at.isoformat() if getattr(a, "created_at", None) else "",
                }
            )
        return {"title": "Movimentações patrimoniais", "filters": filters, "rows": rows}


async def resolve_project_access(
    session: AsyncSession, user: User
) -> tuple[bool, set[UUID] | None]:
    from app.api.deps import get_accessible_project_ids, user_sees_all_projects

    sees_all = user_sees_all_projects(user)
    if sees_all:
        return True, None
    allowed = set(await get_accessible_project_ids(user, session))
    if not allowed:
        allowed = set(await ProjectRepository(session).list_all_project_ids())
    return False, allowed
