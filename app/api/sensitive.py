"""Eixo de dados sensíveis: omissão de valores financeiros no BACKEND (fonte da verdade).

Regra única do sistema: **se existe valor monetário, ele depende da permissão
`<recurso>.sensitive`**. Quem tem `<recurso>.read`/`.list` mas NÃO tem `<recurso>.sensitive`
recebe o payload SEM os campos financeiros (o backend deixa de enviá-los — não é só ocultar
no frontend). Vale para módulos atuais e futuros.

NÃO depende de "ativar" o código na sessão: a checagem usa `user_has_permission`, que resolve
o efetivo (perfil + deltas + grafo `<r>.view ⇒ <r>.sensitive`) independentemente de
`ACTIVE_PERMISSION_CODES`. Assim usa-se a permissão "Dados sensíveis" que já existe na grade,
sem alterar o modelo de permissões.

Uso no router (padrão único — mesmo de Colaboradores/Veículos/Ativos):
    from app.api.sensitive import redact_for
    return [redact_for("payables", m, user) for m in models]      # lista
    return redact_for("payables", model, user)                    # item único
Placeholder de ausência é responsabilidade do frontend (exibir "—" quando o valor vier null).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from app.core.permission_codes import (
    ASSETS_SENSITIVE,
    BILLING_SENSITIVE,
    COMPANY_FINANCE_SENSITIVE,
    COSTS_SENSITIVE,
    DASHBOARD_SENSITIVE,
    DEBTS_SENSITIVE,
    EMPLOYEES_SENSITIVE,
    FINANCIAL_DASHBOARD_SENSITIVE,
    INDICATORS_SENSITIVE,
    INVOICES_SENSITIVE,
    LEGAL_CASES_SENSITIVE,
    LEGAL_PERSONS_SENSITIVE,
    PAYABLES_SENSITIVE,
    PROJECTS_SENSITIVE,
    RECEIVABLES_SENSITIVE,
    VEHICLES_SENSITIVE,
)

T = TypeVar("T", bound=BaseModel)


def redact(model: T, sensitive_fields: tuple[str, ...], include: bool) -> T:
    """Devolve o modelo com os campos sensíveis zerados (None) quando `include` é False.

    Não muta o original — usa `model_copy`. Os campos precisam ser Optional no schema.
    """
    if include:
        return model
    return model.model_copy(update={f: None for f in sensitive_fields if f in type(model).model_fields})


# ---------------------------------------------------------------------------
# Registro central (fonte ÚNICA): recurso → (permissão sensível, campos monetários).
# Um novo módulo passa a respeitar "Dados sensíveis" apenas registrando aqui e chamando
# `redact_for(...)` no router — sem duplicar lógica.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensitiveSpec:
    code: str  # permissão que libera os valores, ex.: "payables.sensitive"
    fields: tuple[str, ...]  # campos monetários a omitir sem a permissão
    # Redação recursiva: (atributo, recurso_do_filho). Aplica a mesma decisão de permissão
    # a modelos aninhados (listas ou objeto único), sem expor valores por caminhos alternativos.
    nested: tuple[tuple[str, str], ...] = ()


# Conjuntos de campos sensíveis por recurso (fonte única).
EMPLOYEE_SENSITIVE_FIELDS: tuple[str, ...] = (
    "salary_base",
    "additional_costs",
    "total_cost",
    "pj_additional_cost",
    "pj_hours_per_month",
    "pix_key",
    "pix_key_type",
)
VEHICLE_SENSITIVE_FIELDS: tuple[str, ...] = ("monthly_cost",)
# Ativos (Patrimônio): valor de aquisição/contábil do item. Os agregados do dashboard patrimonial
# (valores por status/categoria/centro de custo) são omitidos à parte, no router.
ASSET_SENSITIVE_FIELDS: tuple[str, ...] = ("purchase_value",)

# Contas a Pagar (snapshot): todos os valores monetários da linha. `status`/`paid`/`is_overpaid`
# e datas permanecem (informação estrutural). Redação a nível de campo; agregados (dashboards)
# do CAP, quando houver, seguem redator próprio.
PAYABLE_SNAPSHOT_SENSITIVE_FIELDS: tuple[str, ...] = (
    "amount_original",
    "amount_final",
    "amount_paid",
    "amount_remaining",
    "overpaid_amount",
    "paid_in_period",
)

# Contas a Receber (visão NF + manual).
RECEIVABLE_VIEW_SENSITIVE_FIELDS: tuple[str, ...] = (
    "net_value",
    "amount_received_advance",
    "amount_received_customer",
    "total_received",
    "remaining",
)
RECEIVABLE_MANUAL_SENSITIVE_FIELDS: tuple[str, ...] = ("valor_liquido", "valor_recebido")
RECEIVABLE_KPIS_SENSITIVE_FIELDS: tuple[str, ...] = (
    "total_a_receber",
    "total_bruto_a_receber",
    "recebido_no_mes",
    "em_atraso_valor",
)  # `total_nfs` (contagem) permanece.

# Notas Fiscais (ReceivableInvoiceRead) + estruturas aninhadas (antecipações/lote/histórico).
INVOICE_SENSITIVE_FIELDS: tuple[str, ...] = (
    "gross_amount",
    "net_amount",
    "advance_amount_received",
    "advance_amount_due",
    "received_amount",
    "interest_amount",
    "advance_cost_value",
    "advance_interest_rate",
    "advance_monthly_rate",
    "implied_monthly_rate_percent",
)
INVOICE_ANTICIPATION_SENSITIVE_FIELDS: tuple[str, ...] = (
    "amount_received",
    "amount_to_repay",
    "juros_total",
    "taxa_percentual",
    "taxa_mensal",
)
ADVANCE_BATCH_SUMMARY_SENSITIVE_FIELDS: tuple[str, ...] = ("received_amount", "gross_amount")
ADVANCE_OPERATION_HISTORY_SENSITIVE_FIELDS: tuple[str, ...] = ("advanced_amount", "received_amount")

# Faturamento (Revenue). `retention_value` é campo calculado a partir de `amount` — fica
# null-safe (None quando `amount` é omitido). Nota fiscal simples do financeiro: `amount`.
# `nf_amount` é a soma faturada do mês: mesmo tipo de valor que `amount` e, portanto, sob o
# mesmo gate — sem isso a coluna de conciliação exporia a receita a quem não pode vê-la.
REVENUE_SENSITIVE_FIELDS: tuple[str, ...] = ("amount", "nf_amount")
BILLING_INVOICE_SENSITIVE_FIELDS: tuple[str, ...] = ("amount",)
BILLING_INVOICE_ANTICIPATION_SENSITIVE_FIELDS: tuple[str, ...] = ("fee_amount",)

# --- Projetos (custos do projeto: mão de obra, veículos, sistemas, contrato) ---
PROJECT_CONTRACT_SENSITIVE_FIELDS: tuple[str, ...] = (
    "contract_value", "additive_value",
    # Base do "consumo do contrato". Só campos DECLARADOS entram aqui: a redação não alcança
    # campo calculado. Os derivados (contract_total_value, contract_balance,
    # contract_consumed_pct) devolvem None sozinhos quando a base vem redigida.
    "additive_value_total", "invoiced_total",
)
PROJECT_LABOR_SENSITIVE_FIELDS: tuple[str, ...] = (
    "monthly_cost", "full_cost", "allocated_cost", "variable_components_total", "total_cost",
    "cost_salary_base", "cost_extra_hours_50",
    "cost_extra_hours_70", "cost_extra_hours_100", "cost_pj_hours_per_month",
    "cost_pj_additional_cost", "cost_total_override",
)
LABOR_BREAKDOWN_SENSITIVE_FIELDS: tuple[str, ...] = (
    "salary_base", "periculosidade", "adicional_dirigida", "vr", "horas_extras",
    "encargos", "additional_costs", "ajuda_custo",
)
PROJECT_VEHICLE_SENSITIVE_FIELDS: tuple[str, ...] = (
    "monthly_cost", "fuel_cost_realized", "display_fuel_cost", "fuel_cost_per_km_realized",
)
PROJECT_VALUE_SENSITIVE_FIELDS: tuple[str, ...] = ("value",)  # sistemas / operacional fixo
EMPLOYEE_ALLOCATION_SENSITIVE_FIELDS: tuple[str, ...] = ("monthly_cost",)

# --- Endividamento / Finanças da empresa (company_finance; gate por tipo) ---
COMPANY_FINANCE_ITEM_SENSITIVE_FIELDS: tuple[str, ...] = (
    "valor_referencia", "debt_base", "renegotiated_amount", "installment_value",
    "total_pago", "pago_mes", "cap_amount_paid", "restante", "progresso", "progresso_mes",
)
KPI_ENDIVIDAMENTO_SENSITIVE_FIELDS: tuple[str, ...] = (
    "total_endividamento", "total_pago_mes", "saldo_restante",
)  # quantidade_itens permanece
KPI_CUSTOS_FIXOS_SENSITIVE_FIELDS: tuple[str, ...] = ("total_esperado_mes", "total_pago_mes")
CHART_POINT_SENSITIVE_FIELDS: tuple[str, ...] = ("pagamentos_mes", "saldo_restante_total")
PENDENCIA_SENSITIVE_FIELDS: tuple[str, ...] = ("valor_referencia", "ultimo_valor")
PENDENCIAS_TOTALS_SENSITIVE_FIELDS: tuple[str, ...] = ("total_previsto", "total_pago")  # quantidade permanece

# --- Dashboard (indicadores/gráficos financeiros) ---
# Tupla única (redact filtra pelos campos presentes em cada modelo): receita/custo/lucro/
# margem/EBITDA + composição de custos e seus percentuais financeiros. Datas/contagens ficam.
DASHBOARD_MONEY_SENSITIVE_FIELDS: tuple[str, ...] = (
    "revenue_total", "total_revenue", "cost_total", "total_cost", "total_retention",
    "operational_profit", "net_profit", "margin_operational", "margin_net", "profit", "margin",
    "ebitda", "ebitda_margin", "operational_cost", "labor_cost", "vehicle_cost", "system_cost",
    "fixed_operational_cost", "tax_amount", "overhead_amount", "anticipation_amount",
    "labor_cost_pct", "vehicle_cost_pct", "system_cost_pct", "fixed_operational_cost_pct",
    "operational_cost_pct", "tax_amount_pct", "overhead_amount_pct", "anticipation_amount_pct",
    "value",  # KPIRead.value
    "lucro_liquido_previsto", "lucro_liquido_realizado",  # wrapper FinancialDashboardSummary
)

# --- Dashboard Financeiro (Financeiro → Dashboard; caixa: faturamento/pago/caixa) ---
# Recurso próprio (financial_dashboard.sensitive), espelhando o Dashboard de Projetos. Datas/labels
# permanecem; só os valores monetários são omitidos.
FINANCIAL_DASHBOARD_MONEY_SENSITIVE_FIELDS: tuple[str, ...] = ("faturamento", "pago", "caixa")
FINANCIAL_DASHBOARD_BREAKDOWN_SENSITIVE_FIELDS: tuple[str, ...] = ("total", "received_total", "paid_total")
FINANCIAL_DASHBOARD_GROUP_SENSITIVE_FIELDS: tuple[str, ...] = ("value",)

# --- Indicadores (ROI, evolução financeira, KPIs, insights) ---
INDICATOR_ROI_SENSITIVE_FIELDS: tuple[str, ...] = (
    "revenue", "cost", "operational_profit", "roi", "roi_pct",
)  # project_count/ids/nome permanecem
INDICATOR_FIN_POINT_SENSITIVE_FIELDS: tuple[str, ...] = (
    "faturamento", "custo_total", "custo_mo", "custo_veiculos",
    "lucro_operacional", "lucro_liquido", "custo_cap",
)
INDICATOR_FIN_KPI_SENSITIVE_FIELDS: tuple[str, ...] = ("total", "growth_pct")
INDICATOR_HIGHLIGHT_SENSITIVE_FIELDS: tuple[str, ...] = ("value",)
INDICATOR_INSIGHTS_TOTALS_SENSITIVE_FIELDS: tuple[str, ...] = ("crescimento_acumulado_pct",)

# --- Custos (project fixed / corporate / allocation) ---
COST_SENSITIVE_FIELDS: tuple[str, ...] = ("amount_real", "amount_calculated")
COST_ALLOCATION_SENSITIVE_FIELDS: tuple[str, ...] = (
    "allocated_amount_real", "allocated_amount_calculated",
)

# --- Jurídico (legal.sensitive) ---
# Valores do PROCESSO. Número, partes, status, foro, datas e movimentação permanecem — o que
# depende de `legal.sensitive` é a exposição financeira do passivo.
LEGAL_CASE_SENSITIVE_FIELDS: tuple[str, ...] = (
    "amount_claimed",
    "amount_considered",
    "amount_agreed",
    "amount_paid",
    "amount_pending",
    "agreement_terms",  # descreve o plano de pagamento do acordo (valor por parcela)
)
# Valores da RESCISÃO do ex-colaborador + agregados derivados dos seus processos.
LEGAL_PERSON_SENSITIVE_FIELDS: tuple[str, ...] = (
    "severance_amount",
    "fgts_balance",
    "total_claimed",
    "total_considered",
    "total_agreed",
    "total_paid",
    "total_pending",
)  # `case_count` (quantidade) permanece
# KPIs e séries dos gráficos da tela de Processos (contagens permanecem).
LEGAL_KPIS_SENSITIVE_FIELDS: tuple[str, ...] = (
    "total_claimed",
    "total_considered",
    "total_agreed",
    "total_paid",
    "total_pending",
)
LEGAL_BUCKET_SENSITIVE_FIELDS: tuple[str, ...] = ("value",)


SENSITIVE_SPECS: dict[str, SensitiveSpec] = {
    # Módulos de referência (já em produção) — agora registrados na fonte única.
    "employees": SensitiveSpec(EMPLOYEES_SENSITIVE, EMPLOYEE_SENSITIVE_FIELDS),
    "vehicles": SensitiveSpec(VEHICLES_SENSITIVE, VEHICLE_SENSITIVE_FIELDS),
    "assets": SensitiveSpec(ASSETS_SENSITIVE, ASSET_SENSITIVE_FIELDS),
    # Financeiro — Contas a Pagar (Etapa 1).
    "payables": SensitiveSpec(PAYABLES_SENSITIVE, PAYABLE_SNAPSHOT_SENSITIVE_FIELDS),
    # Financeiro — Contas a Receber.
    "receivables": SensitiveSpec(RECEIVABLES_SENSITIVE, RECEIVABLE_VIEW_SENSITIVE_FIELDS),
    "receivables_manual": SensitiveSpec(RECEIVABLES_SENSITIVE, RECEIVABLE_MANUAL_SENSITIVE_FIELDS),
    # Financeiro — Notas Fiscais (com redação recursiva das estruturas aninhadas).
    "invoices": SensitiveSpec(
        INVOICES_SENSITIVE,
        INVOICE_SENSITIVE_FIELDS,
        nested=(
            ("anticipations", "invoice_anticipations"),
            ("advance_batch", "advance_batch_summary"),
            ("advance_operations", "advance_operations"),
        ),
    ),
    "invoice_anticipations": SensitiveSpec(INVOICES_SENSITIVE, INVOICE_ANTICIPATION_SENSITIVE_FIELDS),
    "advance_batch_summary": SensitiveSpec(INVOICES_SENSITIVE, ADVANCE_BATCH_SUMMARY_SENSITIVE_FIELDS),
    "advance_operations": SensitiveSpec(INVOICES_SENSITIVE, ADVANCE_OPERATION_HISTORY_SENSITIVE_FIELDS),
    "invoices_kpis": SensitiveSpec(INVOICES_SENSITIVE, RECEIVABLE_KPIS_SENSITIVE_FIELDS),
    "billing_invoice": SensitiveSpec(INVOICES_SENSITIVE, BILLING_INVOICE_SENSITIVE_FIELDS),
    "billing_invoice_anticipation": SensitiveSpec(
        INVOICES_SENSITIVE, BILLING_INVOICE_ANTICIPATION_SENSITIVE_FIELDS
    ),
    # Financeiro — Faturamento.
    "billing_revenue": SensitiveSpec(BILLING_SENSITIVE, REVENUE_SENSITIVE_FIELDS),
    # --- Projetos (custos do projeto) ---
    "project": SensitiveSpec(PROJECTS_SENSITIVE, PROJECT_CONTRACT_SENSITIVE_FIELDS),
    "project_labor": SensitiveSpec(PROJECTS_SENSITIVE, PROJECT_LABOR_SENSITIVE_FIELDS),
    "project_labor_detail": SensitiveSpec(
        PROJECTS_SENSITIVE, PROJECT_LABOR_SENSITIVE_FIELDS,
        nested=(("breakdown", "labor_breakdown"),),
    ),
    "labor_breakdown": SensitiveSpec(PROJECTS_SENSITIVE, LABOR_BREAKDOWN_SENSITIVE_FIELDS),
    "project_vehicle": SensitiveSpec(PROJECTS_SENSITIVE, PROJECT_VEHICLE_SENSITIVE_FIELDS),
    "project_value": SensitiveSpec(PROJECTS_SENSITIVE, PROJECT_VALUE_SENSITIVE_FIELDS),
    "employee_allocation": SensitiveSpec(PROJECTS_SENSITIVE, EMPLOYEE_ALLOCATION_SENSITIVE_FIELDS),
    # --- Endividamento (gate debts.sensitive) e Finanças da empresa (company_finance.sensitive).
    # Mesmos campos; o router escolhe o recurso por `tipo` (endividamento vs custo_fixo).
    # `pagamentos` (grade mensal) também é redigido — valores monetários por competência.
    "debt_item": SensitiveSpec(
        DEBTS_SENSITIVE, COMPANY_FINANCE_ITEM_SENSITIVE_FIELDS,
        nested=(("pagamentos", "company_finance_payment"),),
    ),
    "custo_fixo_item": SensitiveSpec(
        COMPANY_FINANCE_SENSITIVE, COMPANY_FINANCE_ITEM_SENSITIVE_FIELDS,
        nested=(("pagamentos", "company_finance_payment"),),
    ),
    "company_finance_payment": SensitiveSpec(DEBTS_SENSITIVE, ("valor",)),
    "kpi_endividamento": SensitiveSpec(DEBTS_SENSITIVE, KPI_ENDIVIDAMENTO_SENSITIVE_FIELDS),
    "kpi_custos_fixos": SensitiveSpec(COMPANY_FINANCE_SENSITIVE, KPI_CUSTOS_FIXOS_SENSITIVE_FIELDS),
    "debt_chart": SensitiveSpec(DEBTS_SENSITIVE, (), nested=(("points", "chart_point"),)),
    "custo_fixo_chart": SensitiveSpec(COMPANY_FINANCE_SENSITIVE, (), nested=(("points", "chart_point"),)),
    "chart_point": SensitiveSpec(DEBTS_SENSITIVE, CHART_POINT_SENSITIVE_FIELDS),
    "debt_pendencias": SensitiveSpec(
        DEBTS_SENSITIVE, PENDENCIAS_TOTALS_SENSITIVE_FIELDS, nested=(("pendencias", "pendencia_item"),)
    ),
    "custo_fixo_pendencias": SensitiveSpec(
        COMPANY_FINANCE_SENSITIVE, PENDENCIAS_TOTALS_SENSITIVE_FIELDS,
        nested=(("pendencias", "pendencia_item"),),
    ),
    "pendencia_item": SensitiveSpec(COMPANY_FINANCE_SENSITIVE, PENDENCIA_SENSITIVE_FIELDS),
    # --- Dashboard (dashboard.sensitive) ---
    "dashboard_point": SensitiveSpec(DASHBOARD_SENSITIVE, DASHBOARD_MONEY_SENSITIVE_FIELDS),
    "dashboard_summary": SensitiveSpec(DASHBOARD_SENSITIVE, DASHBOARD_MONEY_SENSITIVE_FIELDS),
    "dashboard_financial_summary": SensitiveSpec(
        DASHBOARD_SENSITIVE, DASHBOARD_MONEY_SENSITIVE_FIELDS,
        nested=(
            ("summary", "dashboard_summary"),
            ("monthly_series", "dashboard_point"),
            ("monthly_series_previsto", "dashboard_point"),
            ("monthly_series_realizado", "dashboard_point"),
        ),
    ),
    "dashboard_project_response": SensitiveSpec(
        DASHBOARD_SENSITIVE, (),
        nested=(
            ("summary", "dashboard_summary"),
            ("monthly_series", "dashboard_point"),
            ("monthly_series_previsto", "dashboard_point"),
            ("monthly_series_realizado", "dashboard_point"),
        ),
    ),
    # --- Dashboard Financeiro (financial_dashboard.sensitive) ---
    # Endpoints /financial/dashboard, /financial/dashboard/timeseries e /financial/dashboard/breakdown.
    "financial_dashboard_summary": SensitiveSpec(
        FINANCIAL_DASHBOARD_SENSITIVE, FINANCIAL_DASHBOARD_MONEY_SENSITIVE_FIELDS
    ),
    "financial_dashboard_point": SensitiveSpec(
        FINANCIAL_DASHBOARD_SENSITIVE, FINANCIAL_DASHBOARD_MONEY_SENSITIVE_FIELDS
    ),
    "financial_dashboard": SensitiveSpec(
        FINANCIAL_DASHBOARD_SENSITIVE, (),
        nested=(
            ("summary", "financial_dashboard_summary"),
            ("timeseries", "financial_dashboard_point"),
        ),
    ),
    "financial_dashboard_group": SensitiveSpec(
        FINANCIAL_DASHBOARD_SENSITIVE, FINANCIAL_DASHBOARD_GROUP_SENSITIVE_FIELDS
    ),
    "financial_dashboard_breakdown": SensitiveSpec(
        FINANCIAL_DASHBOARD_SENSITIVE, FINANCIAL_DASHBOARD_BREAKDOWN_SENSITIVE_FIELDS,
        nested=(
            ("groups", "financial_dashboard_group"),
            ("received_groups", "financial_dashboard_group"),
            ("paid_groups", "financial_dashboard_group"),
        ),
    ),
    # --- Indicadores (indicators.sensitive) ---
    "indicator_roi": SensitiveSpec(INDICATORS_SENSITIVE, INDICATOR_ROI_SENSITIVE_FIELDS),
    "roi_ranking": SensitiveSpec(INDICATORS_SENSITIVE, (), nested=(("items", "indicator_roi"),)),
    "roi_evolution_point": SensitiveSpec(INDICATORS_SENSITIVE, INDICATOR_ROI_SENSITIVE_FIELDS),
    "roi_evolution": SensitiveSpec(
        INDICATORS_SENSITIVE, (), nested=(("points", "roi_evolution_point"),)
    ),
    "fin_evolution_point": SensitiveSpec(INDICATORS_SENSITIVE, INDICATOR_FIN_POINT_SENSITIVE_FIELDS),
    "financial_evolution": SensitiveSpec(
        INDICATORS_SENSITIVE, (), nested=(("points", "fin_evolution_point"),)
    ),
    "financial_kpi": SensitiveSpec(INDICATORS_SENSITIVE, INDICATOR_FIN_KPI_SENSITIVE_FIELDS),
    "financial_kpis": SensitiveSpec(
        INDICATORS_SENSITIVE, (),
        nested=(
            ("faturamento", "financial_kpi"),
            ("custo_mo", "financial_kpi"),
            ("lucro_operacional", "financial_kpi"),
            ("lucro_liquido", "financial_kpi"),
        ),
    ),
    "indicator_highlight": SensitiveSpec(INDICATORS_SENSITIVE, INDICATOR_HIGHLIGHT_SENSITIVE_FIELDS),
    "financial_insights": SensitiveSpec(
        INDICATORS_SENSITIVE, INDICATOR_INSIGHTS_TOTALS_SENSITIVE_FIELDS,
        nested=(
            ("maior_faturamento", "indicator_highlight"),
            ("menor_faturamento", "indicator_highlight"),
            ("maior_lucro_operacional", "indicator_highlight"),
            ("maior_lucro_liquido", "indicator_highlight"),
            ("projeto_maior_faturamento", "indicator_highlight"),
            ("projeto_maior_lucro", "indicator_highlight"),
        ),
    ),
    # --- Custos (costs.sensitive) ---
    "cost_item": SensitiveSpec(COSTS_SENSITIVE, COST_SENSITIVE_FIELDS),
    "cost_allocation": SensitiveSpec(COSTS_SENSITIVE, COST_ALLOCATION_SENSITIVE_FIELDS),
    # --- Jurídico (legal.sensitive) ---
    # Processos: valores do processo. Também governam os agregados do Dashboard e do relatório —
    # de propósito, para não existirem dois códigos mandando no mesmo número.
    "legal_case": SensitiveSpec(LEGAL_CASES_SENSITIVE, LEGAL_CASE_SENSITIVE_FIELDS),
    # Desligados: rescisão/FGTS + totais.
    #
    # SEM `nested` para os processos da ficha — de propósito. `nested` propaga a decisão do PAI
    # para os filhos (ver `_redact_model`), o que só é correto quando pai e filho compartilham a
    # MESMA permissão, como em invoices→anticipations. Aqui os códigos são diferentes
    # (`legal_persons.sensitive` × `legal_cases.sensitive`), e propagar vazaria valor de processo
    # para quem só tem o sensitive de Desligados. O router redige cada nível com o SEU recurso.
    "legal_person": SensitiveSpec(LEGAL_PERSONS_SENSITIVE, LEGAL_PERSON_SENSITIVE_FIELDS),
    "legal_kpis": SensitiveSpec(LEGAL_CASES_SENSITIVE, LEGAL_KPIS_SENSITIVE_FIELDS),
    "legal_bucket": SensitiveSpec(LEGAL_CASES_SENSITIVE, LEGAL_BUCKET_SENSITIVE_FIELDS),
    "legal_overview": SensitiveSpec(
        LEGAL_CASES_SENSITIVE, (),
        nested=(
            ("kpis", "legal_kpis"),
            ("by_status", "legal_bucket"),
            ("by_type", "legal_bucket"),
            ("by_uf", "legal_bucket"),
            ("by_company", "legal_bucket"),
            ("by_project", "legal_bucket"),
        ),
    ),
}


def sensitive_include(resource: str, user) -> bool:
    """True se o usuário pode VER os valores do recurso (tem a permissão `<recurso>.sensitive`).

    Usa o efetivo (não a sessão): funciona mesmo com o código ainda inativo na sessão.
    """
    from app.api.deps import user_has_permission  # lazy: evita ciclo de import

    spec = SENSITIVE_SPECS[resource]
    return user_has_permission(user, spec.code)


def _redact_model(resource: str, model: T) -> T:
    """Zera os campos monetários do modelo (e recursivamente dos aninhados registrados).

    Puro (sem checagem de permissão) — a decisão é feita uma única vez em `redact_for`, e a
    mesma decisão vale para todos os níveis aninhados (não há caminho alternativo com valor).
    """
    spec = SENSITIVE_SPECS[resource]
    fields = type(model).model_fields
    update: dict[str, object] = {f: None for f in spec.fields if f in fields}
    for attr, child in spec.nested:
        if attr not in fields:
            continue
        value = getattr(model, attr, None)
        if value is None:
            continue
        if isinstance(value, list):
            update[attr] = [_redact_model(child, item) for item in value]
        else:
            update[attr] = _redact_model(child, value)
    return model.model_copy(update=update)


def redact_for(resource: str, model: T, user) -> T:
    """Redige (omite) os valores monetários do recurso quando o usuário não tem `sensitive`.

    Ponto único que todo router deve usar. `resource` precisa estar em `SENSITIVE_SPECS`.
    Cobre estruturas aninhadas (listas/objetos) via `SensitiveSpec.nested` — sem caminhos
    alternativos que ainda exponham valores.
    """
    if sensitive_include(resource, user):
        return model
    return _redact_model(resource, model)
