import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  createCompanyFinanceItem,
  deleteCompanyFinanceItem,
  fetchChartSeries,
  fetchKpiCustosFixos,
  fetchKpiEndividamento,
  fetchPendenciasCustosFixos,
  listCompanyFinanceItems,
  replaceCompanyFinancePayments,
  updateCompanyFinanceItem,
  type ChartPoint,
  type CompanyFinancialItem,
  type PendenciaLancamento,
  type RenegotiationType,
  type TipoFinanceiro,
} from "@/services/companyFinance";
import { listEmployees, type Employee } from "@/services/employees";
import { listProjects, type Project } from "@/services/projects";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import { COMPANY_FINANCE_SORT_COLUMNS, defaultCompanyFinanceSort } from "@/tableSort/companyFinance";
import {
  CC_REF_ADMINISTRATIVO,
  defaultCostCenterRef,
  itemCostCenterRef,
} from "@/components/company-finance/costCenter";
import { CostCenterSelect } from "@/components/company-finance/CostCenterSelect";
import { CompanyFinanceAnalyticTable } from "@/components/company-finance/CompanyFinanceAnalyticTable";
import { ViewModeToggle } from "@/components/finance/ViewModeToggle";
import { itemMatchesSearch } from "@/components/company-finance/itemSearch";
import { CollapsiblePanel, PrimaryAddButton } from "@/components/ExpandableFormSection";
import { isAxiosError } from "axios";
import { GESTOR_GLOBAL_EDIT_TOOLTIP, useGestorGlobalReadOnly } from "@/hooks/useGestorGlobalReadOnly";
import { usePermission } from "@/hooks/usePermission";
import {
  formatCurrency,
  formatCurrencyInputFromApi,
  normalizeCurrencyForApi,
} from "@/utils/currency";

const MONTH_SHORT = [
  "JAN",
  "FEV",
  "MAR",
  "ABR",
  "MAI",
  "JUN",
  "JUL",
  "AGO",
  "SET",
  "OUT",
  "NOV",
  "DEZ",
];

function formatBRL(n: number): string {
  return formatCurrency(n);
}

function parseBRLInput(raw: string): number {
  return normalizeCurrencyForApi(raw);
}

/** Só envia meses com valor ou que tinham pagamento (evita zerar os outros 11 meses da janela). */
function buildPagamentosPayload(
  monthKeys: string[],
  localPayments: Record<string, string>,
  originalPagamentos: { mes: string; valor: number }[],
): { mes: string; valor: number }[] {
  const originalByMes = new Map(originalPagamentos.map((p) => [p.mes, p.valor]));
  return monthKeys
    .map((mes) => ({
      mes,
      valor: parseBRLInput(localPayments[mes] ?? ""),
    }))
    .filter(({ mes, valor }) => {
      const prev = originalByMes.get(mes) ?? 0;
      if (valor > 0) return true;
      if (prev > 0) return true;
      return (localPayments[mes] ?? "").trim().length > 0;
    });
}

/** 12 meses em ordem cronológica terminando em `endMes` (YYYY-MM). */
function rollingMonthKeys(endMes: string): string[] {
  const [y, m] = endMes.split("-").map(Number);
  const out: string[] = [];
  let yy = y;
  let mm = m;
  for (let i = 0; i < 12; i++) {
    out.push(`${yy}-${String(mm).padStart(2, "0")}`);
    mm -= 1;
    if (mm < 1) {
      mm = 12;
      yy -= 1;
    }
  }
  return out.reverse();
}

function mesLabel(mes: string): string {
  const m = Number.parseInt(mes.split("-")[1] ?? "1", 10);
  return MONTH_SHORT[m - 1] ?? mes;
}

function progressBarClass(ratio: number): string {
  const p = Math.min(1, Math.max(0, ratio));
  if (p >= 1) return "bg-emerald-500";
  if (p >= 0.5) return "bg-amber-400";
  return "bg-red-500";
}

function defaultCategory(tipo: TipoFinanceiro): string {
  return tipo === "endividamento" ? "Endividamento" : "Custos diversos";
}

function defaultRecurrence(tipo: TipoFinanceiro): string {
  return tipo === "endividamento" ? "INSTALLMENTS" : "MONTHLY";
}

/** Eixo Y com zoom na faixa dos dados (+10% margem), para variações pequenas não virarem linha reta. */
function yAxisDomainFromValues(values: number[]): [number, number] | undefined {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return undefined;
  let min = Math.min(...finite);
  let max = Math.max(...finite);
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.01, 1);
    return [min - pad, max + pad];
  }
  const padding = (max - min) * 0.1;
  return [min - padding, max + padding];
}

type Props = {
  tipo: TipoFinanceiro;
  title: string;
  subtitle: string;
};

type DebtCreditorFilter =
  | "ALL"
  | "HAS_LEGAL_PROCESS"
  | "NO_LEGAL_PROCESS"
  | "HAS_RENEGOTIATION"
  | "NO_RENEGOTIATION";

export function CompanyFinanceExecutive({ tipo, title, subtitle }: Props) {
  const gestorGlobalReadOnly = useGestorGlobalReadOnly();
  const canEditCompanyFinance = usePermission("company_finance.edit");
  const financeReadOnly = gestorGlobalReadOnly || !canEditCompanyFinance;
  const financeReadOnlyTitle = financeReadOnly
    ? gestorGlobalReadOnly
      ? GESTOR_GLOBAL_EDIT_TOOLTIP
      : "Sem permissão para editar (finanças da empresa)."
    : undefined;
  const [competencia, setCompetencia] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [items, setItems] = useState<CompanyFinancialItem[]>([]);
  const [kpiDebt, setKpiDebt] = useState<Awaited<ReturnType<typeof fetchKpiEndividamento>> | null>(null);
  const [kpiFixed, setKpiFixed] = useState<Awaited<ReturnType<typeof fetchKpiCustosFixos>> | null>(null);
  const [pendencias, setPendencias] = useState<PendenciaLancamento[]>([]);
  const [chartPoints, setChartPoints] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showCharts, setShowCharts] = useState(false);
  const [creditorFilter, setCreditorFilter] = useState<DebtCreditorFilter>("ALL");
  const [view, setView] = useState<"executive" | "analytic">("executive");
  const [draftName, setDraftName] = useState("");
  const [draftRef, setDraftRef] = useState("");
  const [draftCategory, setDraftCategory] = useState(() => defaultCategory(tipo));
  const [draftCostCenterRef, setDraftCostCenterRef] = useState(() => defaultCostCenterRef(tipo));
  const [projectOptions, setProjectOptions] = useState<Project[]>([]);
  const [draftDescription, setDraftDescription] = useState("");
  const [draftRecurrence, setDraftRecurrence] = useState(() => defaultRecurrence(tipo));
  const [draftItemType, setDraftItemType] = useState<"MANUAL" | "COLABORADOR_MATRIZ">("MANUAL");
  const [draftEmployeeQuery, setDraftEmployeeQuery] = useState("");
  const [draftEmployeeOptions, setDraftEmployeeOptions] = useState<Employee[]>([]);
  const [draftEmployeeOpen, setDraftEmployeeOpen] = useState(false);
  const [draftEmployeeLoading, setDraftEmployeeLoading] = useState(false);
  const [draftEmployeeId, setDraftEmployeeId] = useState("");
  const [draftPercentual, setDraftPercentual] = useState("100");
  const [draftIsMonthlyRequired, setDraftIsMonthlyRequired] = useState(false);
  const [draftHasLegalProcess, setDraftHasLegalProcess] = useState(false);
  const [draftHasRenegotiation, setDraftHasRenegotiation] = useState(false);
  const [draftRenegotiatedAmount, setDraftRenegotiatedAmount] = useState("");
  const [draftRenegotiationType, setDraftRenegotiationType] = useState<RenegotiationType>("UNIQUE");
  const [draftInstallmentCount, setDraftInstallmentCount] = useState("");
  const [draftInstallmentValue, setDraftInstallmentValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [itemSearch, setItemSearch] = useState("");

  const monthKeys = useMemo(() => rollingMonthKeys(competencia), [competencia]);

  const resetCreateForm = useCallback(() => {
    setDraftName("");
    setDraftRef("");
    setDraftCategory(defaultCategory(tipo));
    setDraftCostCenterRef(defaultCostCenterRef(tipo));
    setDraftDescription("");
    setDraftRecurrence(defaultRecurrence(tipo));
    setDraftItemType("MANUAL");
    setDraftEmployeeQuery("");
    setDraftEmployeeOptions([]);
    setDraftEmployeeId("");
    setDraftPercentual("100");
    setDraftIsMonthlyRequired(false);
    setDraftHasLegalProcess(false);
    setDraftHasRenegotiation(false);
    setDraftRenegotiatedAmount("");
    setDraftRenegotiationType("UNIQUE");
    setDraftInstallmentCount("");
    setDraftInstallmentValue("");
  }, [tipo]);

  useEffect(() => {
    setDraftCategory(defaultCategory(tipo));
    setDraftCostCenterRef(defaultCostCenterRef(tipo));
    setDraftRecurrence(defaultRecurrence(tipo));
  }, [tipo]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const list = await listProjects({ status: "ACTIVE", limit: 200 });
        if (!cancelled) {
          setProjectOptions([...list].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")));
        }
      } catch {
        if (!cancelled) setProjectOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ") {
      setDraftCostCenterRef(CC_REF_ADMINISTRATIVO);
    }
  }, [tipo, draftItemType]);

  const installmentCountN = useMemo(() => {
    const n = Number.parseInt(draftInstallmentCount || "0", 10);
    return Number.isFinite(n) ? n : 0;
  }, [draftInstallmentCount]);
  const installmentValueN = useMemo(() => parseBRLInput(draftInstallmentValue), [draftInstallmentValue]);
  const renegotiatedAmountN = useMemo(() => parseBRLInput(draftRenegotiatedAmount), [draftRenegotiatedAmount]);
  const totalCalculated = useMemo(
    () => (installmentCountN > 0 && installmentValueN > 0 ? installmentCountN * installmentValueN : 0),
    [installmentCountN, installmentValueN],
  );

  const createValidationError = useMemo(() => {
    if (tipo !== "endividamento") return null;
    if (!draftHasRenegotiation) return null;

    if (renegotiatedAmountN <= 0) return "Informe o valor renegociado.";
    if (draftRenegotiationType === "INSTALLMENTS") {
      if (installmentCountN <= 0) return "Quantidade de parcelas deve ser maior que 0.";
      if (installmentValueN <= 0) return "Valor da parcela deve ser maior que 0.";
      const diff = Math.abs(totalCalculated - renegotiatedAmountN);
      if (diff > 0.009) return "Total calculado (parcelas) deve ser igual ao valor renegociado.";
    }
    return null;
  }, [
    tipo,
    draftHasRenegotiation,
    renegotiatedAmountN,
    draftRenegotiationType,
    installmentCountN,
    installmentValueN,
    totalCalculated,
  ]);

  const selectedEmployee = useMemo(
    () => draftEmployeeOptions.find((e) => e.id === draftEmployeeId) ?? null,
    [draftEmployeeOptions, draftEmployeeId],
  );

  const percentualN = useMemo(() => {
    const n = Number(String(draftPercentual || "0").replace(",", "."));
    return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 0;
  }, [draftPercentual]);

  const calculatedRef = useMemo(() => {
    if (tipo !== "custo_fixo") return parseBRLInput(draftRef);
    if (draftItemType !== "COLABORADOR_MATRIZ") return parseBRLInput(draftRef);
    const base = Number(selectedEmployee?.total_cost ?? 0);
    return Math.max(0, Math.round(base * (percentualN / 100) * 100) / 100);
  }, [tipo, draftItemType, draftRef, selectedEmployee, percentualN]);

  const loadEmployeeOptions = useCallback(
    async (q: string) => {
      setDraftEmployeeLoading(true);
      try {
        const items = await listEmployees({
          competencia: `${competencia}-01`,
          search: q.trim() ? q.trim() : undefined,
          limit: 20,
          offset: 0,
        }).catch(() => []);
        setDraftEmployeeOptions(items);
      } finally {
        setDraftEmployeeLoading(false);
      }
    },
    [competencia],
  );

  useEffect(() => {
    if (!draftEmployeeOpen) return;
    const t = window.setTimeout(() => {
      void loadEmployeeOptions(draftEmployeeQuery);
    }, 300);
    return () => window.clearTimeout(t);
  }, [draftEmployeeQuery, draftEmployeeOpen, loadEmployeeOptions]);

  const loadAll = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const [list, series] = await Promise.all([
        listCompanyFinanceItems(tipo, competencia),
        fetchChartSeries(tipo),
      ]);
      setItems(list);
      setChartPoints(series.points);
      if (tipo === "endividamento") {
        const k = await fetchKpiEndividamento(competencia);
        setKpiDebt(k);
        setKpiFixed(null);
        setPendencias([]);
      } else {
        const [k, pend] = await Promise.all([
          fetchKpiCustosFixos(competencia),
          fetchPendenciasCustosFixos(competencia),
        ]);
        setKpiFixed(k);
        setKpiDebt(null);
        setPendencias(pend.pendencias);
      }
    } catch (e) {
      if (isAxiosError(e)) setError(e.response?.data?.detail ?? "Erro ao carregar dados.");
      else setError("Erro ao carregar dados.");
    } finally {
      setLoading(false);
    }
  }, [tipo, competencia]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const lineData = useMemo(() => {
    if (tipo === "endividamento") {
      return chartPoints.map((p) => ({
        mes: mesLabel(p.mes),
        saldo: p.saldo_restante_total ?? 0,
      }));
    }
    let cum = 0;
    return chartPoints.map((p) => {
      cum += p.pagamentos_mes;
      return { mes: mesLabel(p.mes), acumulado: cum };
    });
  }, [chartPoints, tipo]);

  const saldoLineYDomain = useMemo(() => {
    if (tipo !== "endividamento") return undefined;
    const rows = lineData as { mes: string; saldo: number }[];
    return yAxisDomainFromValues(rows.map((d) => d.saldo));
  }, [tipo, lineData]);

  /** Variação do saldo entre o primeiro e o último ponto da série exibida. */
  const saldoPeriodDelta = useMemo(() => {
    if (tipo !== "endividamento" || lineData.length < 2) return null;
    const rows = lineData as { mes: string; saldo: number }[];
    return rows[rows.length - 1].saldo - rows[0].saldo;
  }, [tipo, lineData]);

  const barData = useMemo(
    () => chartPoints.map((p) => ({ mes: mesLabel(p.mes), pagamentos: p.pagamentos_mes })),
    [chartPoints],
  );

  const filteredItems = useMemo(() => {
    let list = items;
    if (tipo === "endividamento") {
      list = list.filter((it) => {
        const hasLegal = Boolean(it.has_legal_process);
        const hasReneg = Boolean(it.has_renegotiation);
        switch (creditorFilter) {
          case "HAS_LEGAL_PROCESS":
            return hasLegal;
          case "NO_LEGAL_PROCESS":
            return !hasLegal;
          case "HAS_RENEGOTIATION":
            return hasReneg;
          case "NO_RENEGOTIATION":
            return !hasReneg;
          case "ALL":
          default:
            return true;
        }
      });
    }
    if (itemSearch.trim()) {
      list = list.filter((it) => itemMatchesSearch(it, itemSearch, projectOptions, tipo));
    }
    return list;
  }, [tipo, items, creditorFilter, itemSearch, projectOptions]);

  const { sortedRows: sortedFilteredItems, headerSort } = useTableSort(
    filteredItems,
    COMPANY_FINANCE_SORT_COLUMNS,
    { defaultCompare: defaultCompanyFinanceSort },
  );

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (financeReadOnly) return;
    const nome =
      tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ"
        ? (selectedEmployee?.full_name ?? "").trim()
        : draftName.trim();
    const ref = calculatedRef;
    if (!nome || ref < 0) return;
    if (!draftCostCenterRef) {
      setError("Selecione o centro de custo.");
      return;
    }
    if (createValidationError) {
      setError(createValidationError);
      return;
    }
    if (tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ") {
      if (!draftEmployeeId) {
        setError("Selecione um colaborador.");
        return;
      }
      if (percentualN <= 0) {
        setError("Percentual deve ser maior que 0.");
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      await createCompanyFinanceItem({
        tipo,
        nome,
        valor_referencia: ref,
        category: draftCategory.trim() || defaultCategory(tipo),
        cost_center_ref: draftCostCenterRef || defaultCostCenterRef(tipo),
        description: draftDescription.trim() || null,
        recurrence: draftRecurrence.trim() || defaultRecurrence(tipo),
        item_type: tipo === "custo_fixo" ? draftItemType : "MANUAL",
        employee_id: tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ" ? draftEmployeeId : null,
        percentual: tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ" ? percentualN : null,
        is_monthly_required: tipo === "custo_fixo" ? draftIsMonthlyRequired : false,
        has_legal_process: tipo === "endividamento" ? draftHasLegalProcess : false,
        has_renegotiation: tipo === "endividamento" ? draftHasRenegotiation : false,
        renegotiated_amount: tipo === "endividamento" && draftHasRenegotiation ? renegotiatedAmountN : null,
        renegotiation_type:
          tipo === "endividamento" && draftHasRenegotiation ? (draftRenegotiationType as RenegotiationType) : null,
        installment_count:
          tipo === "endividamento" && draftHasRenegotiation && draftRenegotiationType === "INSTALLMENTS"
            ? installmentCountN
            : null,
        installment_value:
          tipo === "endividamento" && draftHasRenegotiation && draftRenegotiationType === "INSTALLMENTS"
            ? installmentValueN
            : null,
      });
      resetCreateForm();
      setShowCreateForm(false);
      await loadAll();
    } catch (err) {
      if (isAxiosError(err)) setError(String(err.response?.data?.detail ?? err.message));
      else setError("Não foi possível criar o item.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (financeReadOnly) return;
    if (!window.confirm("Excluir este item e todo o histórico de pagamentos?")) return;
    try {
      await deleteCompanyFinanceItem(id);
      if (expandedId === id) setExpandedId(null);
      await loadAll();
    } catch {
      setError("Não foi possível excluir.");
    }
  }

  /** Alterna `is_monthly_required` direto na tabela: otimista + persiste + atualiza pendências. */
  const handleToggleRequired = useCallback(
    async (itemId: string, value: boolean) => {
      if (financeReadOnly) return;
      setItems((prev) => prev.map((it) => (it.id === itemId ? { ...it, is_monthly_required: value } : it)));
      try {
        await updateCompanyFinanceItem(itemId, { is_monthly_required: value }, competencia);
        const pend = await fetchPendenciasCustosFixos(competencia);
        setPendencias(pend.pendencias);
      } catch (e) {
        setItems((prev) => prev.map((it) => (it.id === itemId ? { ...it, is_monthly_required: !value } : it)));
        if (isAxiosError(e)) {
          const detail = e.response?.data?.detail;
          setError(typeof detail === "string" ? detail : "Não foi possível atualizar 'Obrigatório mensal'.");
        } else {
          setError("Não foi possível atualizar 'Obrigatório mensal'.");
        }
      }
    },
    [financeReadOnly, competencia],
  );

  const pendingItemIds = useMemo(() => new Set(pendencias.map((p) => p.item_id)), [pendencias]);

  /** Ação rápida: abre a estrutura do item já posicionada na competência atual. */
  function handlePreencherValor(itemId: string) {
    setView("executive");
    setItemSearch("");
    setExpandedId(itemId);
    window.requestAnimationFrame(() => {
      const el = document.getElementById(`cf-item-${itemId}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }

  const pendenciasCount = pendencias.length;

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
          <p className="mt-1 text-sm text-slate-600">{subtitle}</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-end">
          {tipo === "endividamento" && (
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Filtro de credores</span>
              <select
                value={creditorFilter}
                onChange={(e) => setCreditorFilter(e.target.value as DebtCreditorFilter)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm"
              >
                <option value="ALL">Todos</option>
                <option value="HAS_LEGAL_PROCESS">Com processo</option>
                <option value="NO_LEGAL_PROCESS">Sem processo</option>
                <option value="HAS_RENEGOTIATION">Renegociados</option>
                <option value="NO_RENEGOTIATION">Não renegociados</option>
              </select>
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Competência (mês de referência)</span>
            <input
              type="month"
              value={competencia}
              onChange={(e) => setCompetencia(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-slate-900 shadow-sm"
            />
          </label>
          <PrimaryAddButton
            open={showCreateForm}
            disabled={financeReadOnly}
            onToggle={() => {
              setShowCreateForm((open) => {
                if (open) resetCreateForm();
                return !open;
              });
            }}
          />
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {/* KPIs */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tipo === "endividamento" && kpiDebt && (
          <>
            <KpiCard label="Total de endividamento" value={formatBRL(kpiDebt.total_endividamento)} />
            <KpiCard label="Total pago no mês" value={formatBRL(kpiDebt.total_pago_mes)} />
            <KpiCard label="Saldo restante" value={formatBRL(kpiDebt.saldo_restante)} accent="text-amber-800" />
            <KpiCard label="Quantidade de itens" value={String(kpiDebt.quantidade_itens)} />
          </>
        )}
        {tipo === "custo_fixo" && kpiFixed && (
          <>
            <KpiCard label="Total esperado no mês" value={formatBRL(kpiFixed.total_esperado_mes)} />
            <KpiCard label="Total pago no mês" value={formatBRL(kpiFixed.total_pago_mes)} />
            <KpiCard label="Itens cadastrados" value={String(kpiFixed.quantidade_itens)} />
            <KpiCard
              label="Cobertura do mês"
              value={
                kpiFixed.total_esperado_mes > 0
                  ? `${((kpiFixed.total_pago_mes / kpiFixed.total_esperado_mes) * 100).toFixed(1)}%`
                  : "—"
              }
            />
            <KpiCard
              label="Pendências"
              value={String(pendenciasCount)}
              accent={pendenciasCount > 0 ? "text-amber-600" : "text-emerald-600"}
            />
          </>
        )}
        {loading && !kpiDebt && !kpiFixed && (
          <p className="col-span-full text-sm text-slate-500">Carregando indicadores…</p>
        )}
      </section>

      {/* Pendências de Lançamento (apenas custos fixos) — controle operacional */}
      {tipo === "custo_fixo" && (
        <PendingEntriesSection
          pendencias={pendencias}
          competencia={competencia}
          readOnly={financeReadOnly}
          readOnlyTitle={financeReadOnlyTitle}
          onPreencher={handlePreencherValor}
        />
      )}

      {/* Seletor de visão (logo abaixo dos cards principais) */}
      <ViewModeToggle
        value={view}
        onChange={setView}
        options={[
          { value: "executive", label: "Visão Executiva" },
          { value: "analytic", label: "Extrato Analítico" },
        ]}
      />

      {view === "analytic" ? (
        <CompanyFinanceAnalyticTable
          items={filteredItems}
          tipo={tipo}
          search={itemSearch}
          onSearch={setItemSearch}
          readOnly={financeReadOnly}
          readOnlyTitle={financeReadOnlyTitle}
          pendingItemIds={pendingItemIds}
          onToggleRequired={handleToggleRequired}
        />
      ) : (
        <>
      {/* Gráficos (recolhível) */}
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-sm font-medium text-slate-800">Gráficos</h2>
            <p className="text-xs text-slate-500">Opcional: abra para visualizar tendências do período.</p>
          </div>
          <button
            type="button"
            onClick={() => setShowCharts((v) => !v)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            aria-expanded={showCharts}
          >
            <span>{showCharts ? "Ocultar gráficos" : "Mostrar gráficos"}</span>
            <span className={`select-none text-slate-500 transition-transform ${showCharts ? "rotate-90" : ""}`}>
              ›
            </span>
          </button>
        </div>

        <CollapsiblePanel open={showCharts} className="pt-4">
          {showCharts ? (
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-medium text-slate-800">
                      {tipo === "endividamento" ? "Evolução do saldo restante" : "Pagamentos acumulados"}
                    </h3>
                    <p className="text-xs text-slate-500">
                      {tipo === "endividamento"
                        ? "Soma do saldo devedor ao fim de cada mês (eixo Y ajustado à faixa dos valores para destacar variações)"
                        : "Soma acumulada dos pagamentos registrados"}
                    </p>
                  </div>
                  {tipo === "endividamento" && saldoPeriodDelta != null && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-right">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Variação no período</p>
                      <p
                        className={`text-sm font-semibold tabular-nums ${
                          saldoPeriodDelta < 0
                            ? "text-emerald-700"
                            : saldoPeriodDelta > 0
                              ? "text-amber-800"
                              : "text-slate-700"
                        }`}
                      >
                        {saldoPeriodDelta > 0 ? "+" : ""}
                        {formatBRL(saldoPeriodDelta)}
                      </p>
                    </div>
                  )}
                </div>
                <div className="mt-3 h-[260px]">
                  {lineData.length === 0 ? (
                    <p className="flex h-full items-center justify-center text-sm text-slate-500">Sem dados.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={lineData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis dataKey="mes" tick={{ fontSize: 10 }} />
                        <YAxis
                          tick={{ fontSize: 10 }}
                          tickFormatter={(v) =>
                            Math.abs(v) >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : `${(v / 1000).toFixed(0)}k`
                          }
                          width={48}
                          domain={tipo === "endividamento" && saldoLineYDomain ? saldoLineYDomain : undefined}
                          allowDataOverflow
                        />
                        <Tooltip formatter={(v: number) => formatBRL(v)} />
                        <Legend />
                        {tipo === "endividamento" ? (
                          <Line
                            type="monotone"
                            dataKey="saldo"
                            name="Saldo restante"
                            stroke="#4F46E5"
                            strokeWidth={2}
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            dot={{ r: 3, fill: "#4F46E5", strokeWidth: 0 }}
                            activeDot={{ r: 5, stroke: "#fff", strokeWidth: 2 }}
                          />
                        ) : (
                          <Line
                            type="monotone"
                            dataKey="acumulado"
                            name="Acumulado"
                            stroke="#059669"
                            strokeWidth={2}
                            dot={false}
                          />
                        )}
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="text-sm font-medium text-slate-800">Pagamentos por mês</h3>
                <p className="text-xs text-slate-500">Soma de todos os itens no mês</p>
                <div className="mt-3 h-[260px]">
                  {barData.length === 0 ? (
                    <p className="flex h-full items-center justify-center text-sm text-slate-500">Sem dados.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={barData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis dataKey="mes" tick={{ fontSize: 10 }} />
                        <YAxis
                          tick={{ fontSize: 10 }}
                          tickFormatter={(v) =>
                            Math.abs(v) >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : `${(v / 1000).toFixed(0)}k`
                          }
                          width={40}
                        />
                        <Tooltip formatter={(v: number) => formatBRL(v)} />
                        <Bar dataKey="pagamentos" fill="#6366F1" radius={[4, 4, 0, 0]} name="Pagamentos" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </CollapsiblePanel>
      </section>

      <CollapsiblePanel
        open={showCreateForm}
        className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 shadow-sm"
      >
        <h2 className="text-sm font-medium text-slate-800">Novo item</h2>
        <form onSubmit={handleCreate} className="mt-3 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          {tipo === "custo_fixo" && (
            <label className="flex w-full min-w-[220px] flex-col gap-1 text-sm sm:w-56">
              <span className="text-slate-600">Tipo</span>
              <select
                value={draftItemType}
                onChange={(e) => setDraftItemType(e.target.value as "MANUAL" | "COLABORADOR_MATRIZ")}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2"
                disabled={financeReadOnly}
              >
                <option value="MANUAL">Manual</option>
                <option value="COLABORADOR_MATRIZ">Colaborador</option>
              </select>
            </label>
          )}

          <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-sm">
            <span className="text-slate-600">Nome</span>
            <input
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
              placeholder="Ex.: Financiamento veículos"
              required
              disabled={financeReadOnly || (tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ")}
            />
          </label>
          <label className="flex w-full min-w-[160px] flex-col gap-1 text-sm sm:w-48">
            <span className="text-slate-600">
              {tipo === "endividamento" ? "Valor total da dívida" : "Valor mensal esperado"}
            </span>
            <input
              value={
                tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ"
                  ? formatCurrencyInputFromApi(calculatedRef)
                  : draftRef
              }
              onChange={(e) => setDraftRef(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
              placeholder="0,00"
              inputMode="decimal"
              disabled={financeReadOnly || (tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ")}
            />
          </label>
          <label className="flex w-full min-w-[160px] flex-col gap-1 text-sm sm:w-48">
            <span className="text-slate-600">Categoria</span>
            <input
              value={draftCategory}
              onChange={(e) => setDraftCategory(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
              disabled={financeReadOnly}
            />
          </label>
          <label className="flex w-full min-w-[160px] flex-col gap-1 text-sm sm:w-48">
            <span className="text-slate-600">Centro de custo *</span>
            <CostCenterSelect
              value={draftCostCenterRef}
              onChange={setDraftCostCenterRef}
              projects={projectOptions}
              disabled={financeReadOnly || (tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ")}
            />
          </label>
          <label className="flex w-full min-w-[160px] flex-col gap-1 text-sm sm:w-48">
            <span className="text-slate-600">Recorrência</span>
            <select
              value={draftRecurrence}
              onChange={(e) => setDraftRecurrence(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2"
              disabled={financeReadOnly}
            >
              <option value="MONTHLY">Mensal</option>
              <option value="INSTALLMENTS">Parcelada</option>
              <option value="UNIQUE">Única</option>
              <option value="VARIABLE">Variável</option>
            </select>
          </label>
          <label className="flex w-full flex-col gap-1 text-sm">
            <span className="text-slate-600">Descrição</span>
            <textarea
              value={draftDescription}
              onChange={(e) => setDraftDescription(e.target.value)}
              rows={2}
              className="rounded-lg border border-slate-300 px-3 py-2"
              disabled={financeReadOnly}
            />
          </label>

          {tipo === "custo_fixo" && (
            <label className="flex w-full items-start gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={draftIsMonthlyRequired}
                onChange={(e) => setDraftIsMonthlyRequired(e.target.checked)}
                disabled={financeReadOnly}
                className="mt-0.5 h-4 w-4 rounded border-slate-300"
              />
              <span>
                Obrigatório mensal
                <span className="ml-2 text-xs text-slate-500">
                  Sinaliza pendência quando a competência ficar sem valor (não cria lançamento).
                </span>
              </span>
            </label>
          )}

          {tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ" && (
            <div className="grid w-full gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-slate-600">Colaborador</span>
                <div className="relative">
                  <input
                    value={draftEmployeeQuery}
                    onChange={(e) => {
                      setDraftEmployeeQuery(e.target.value);
                      setDraftEmployeeOpen(true);
                    }}
                    onFocus={() => setDraftEmployeeOpen(true)}
                    onBlur={() => window.setTimeout(() => setDraftEmployeeOpen(false), 150)}
                    placeholder={selectedEmployee ? selectedEmployee.full_name : "Digite para buscar…"}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2"
                    disabled={financeReadOnly}
                  />
                  {draftEmployeeOpen ? (
                    <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
                      <div className="px-3 py-2 text-xs text-slate-500">
                        {draftEmployeeLoading
                          ? "Buscando…"
                          : draftEmployeeOptions.length === 0
                            ? "Nenhum colaborador encontrado."
                            : "Selecione um colaborador"}
                      </div>
                      <div className="max-h-56 overflow-auto">
                        {draftEmployeeOptions.map((em) => (
                          <button
                            key={em.id}
                            type="button"
                            onMouseDown={(ev) => {
                              ev.preventDefault();
                              setDraftEmployeeId(em.id);
                              setDraftEmployeeQuery("");
                              setDraftEmployeeOpen(false);
                              setDraftName(em.full_name);
                            }}
                            className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50"
                          >
                            <span className="truncate text-slate-900">{em.full_name}</span>
                            <span className="ml-2 shrink-0 rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">
                              {em.employment_type}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
                {selectedEmployee ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Base: <span className="font-medium text-slate-700">{formatBRL(selectedEmployee.total_cost)}</span>
                  </p>
                ) : null}
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-slate-600">Percentual (%)</span>
                <input
                  value={draftPercentual}
                  onChange={(e) => setDraftPercentual(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                  inputMode="decimal"
                  disabled={financeReadOnly}
                />
              </label>
              <div className="flex flex-col justify-end">
                <p className="text-xs text-slate-500">
                  Centro de custo: <span className="font-medium text-slate-700">Administrativo</span>
                </p>
              </div>
            </div>
          )}

          {tipo === "endividamento" && (
            <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-end">
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={draftHasLegalProcess}
                  onChange={(e) => setDraftHasLegalProcess(e.target.checked)}
                  disabled={financeReadOnly}
                  className="h-4 w-4 rounded border-slate-300"
                />
                <span>Possui processo judicial</span>
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={draftHasRenegotiation}
                  onChange={(e) => setDraftHasRenegotiation(e.target.checked)}
                  disabled={financeReadOnly}
                  className="h-4 w-4 rounded border-slate-300"
                />
                <span>Possui renegociação</span>
              </label>
            </div>
          )}

          {tipo === "endividamento" && draftHasRenegotiation && (
            <div className="grid w-full gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-slate-600">Valor renegociado</span>
                <input
                  value={draftRenegotiatedAmount}
                  onChange={(e) => setDraftRenegotiatedAmount(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="0,00"
                  inputMode="decimal"
                  disabled={financeReadOnly}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-slate-600">Tipo de renegociação</span>
                <select
                  value={draftRenegotiationType}
                  onChange={(e) => setDraftRenegotiationType(e.target.value as RenegotiationType)}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2"
                  disabled={financeReadOnly}
                >
                  <option value="UNIQUE">Única</option>
                  <option value="INSTALLMENTS">Parcelada</option>
                </select>
              </label>

              {draftRenegotiationType === "INSTALLMENTS" && (
                <>
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-slate-600">Quantidade de parcelas</span>
                    <input
                      value={draftInstallmentCount}
                      onChange={(e) => setDraftInstallmentCount(e.target.value)}
                      className="rounded-lg border border-slate-300 px-3 py-2"
                      placeholder="Ex.: 12"
                      inputMode="numeric"
                      disabled={financeReadOnly}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-slate-600">Valor da parcela</span>
                    <input
                      value={draftInstallmentValue}
                      onChange={(e) => setDraftInstallmentValue(e.target.value)}
                      className="rounded-lg border border-slate-300 px-3 py-2"
                      placeholder="0,00"
                      inputMode="decimal"
                      disabled={financeReadOnly}
                    />
                  </label>
                  <div className="sm:col-span-2 lg:col-span-4">
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Total calculado</p>
                      <p className="text-sm font-semibold tabular-nums text-slate-900">{formatBRL(totalCalculated)}</p>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {createValidationError && (
            <div className="w-full rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              {createValidationError}
            </div>
          )}

          <button
            type="submit"
            disabled={saving || financeReadOnly}
            title={financeReadOnlyTitle}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? "Salvando…" : "Adicionar"}
          </button>
        </form>
      </CollapsiblePanel>

      {/* Cards */}
      <section className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
          <h2 className="text-lg font-medium text-slate-900">Itens</h2>
          <label className="flex min-w-[min(100%,280px)] flex-1 flex-col gap-1 text-sm sm:max-w-md">
            <span className="font-medium text-slate-700">Buscar</span>
            <input
              type="search"
              value={itemSearch}
              onChange={(e) => setItemSearch(e.target.value)}
              placeholder="Buscar item, fornecedor ou descrição..."
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 shadow-sm"
            />
          </label>
        </div>
        {!loading && sortedFilteredItems.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50/80">
                <tr>
                  <SortableTh label="Nome" column="nome" variant="standard" {...headerSort} />
                  <SortableTh label="Categoria" column="category" variant="standard" {...headerSort} />
                  <SortableTh label="Centro de custo" column="cost_center" variant="standard" {...headerSort} />
                  <SortableTh label="Referência" column="valor_referencia" variant="standard" align="right" {...headerSort} />
                  <SortableTh label="Total pago" column="total_pago" variant="standard" align="right" {...headerSort} />
                  <SortableTh label="Pago no mês" column="pago_mes" variant="standard" align="right" {...headerSort} />
                  <SortableTh label="Status" column="status" variant="standard" {...headerSort} />
                </tr>
              </thead>
            </table>
          </div>
        ) : null}
        {loading && items.length === 0 ? (
          <p className="text-sm text-slate-500">Carregando…</p>
        ) : filteredItems.length === 0 ? (
          <p className="text-sm text-slate-500">
            {items.length === 0
              ? "Nenhum item cadastrado."
              : itemSearch.trim()
                ? "Nenhum item corresponde à busca."
                : "Nenhum item encontrado para este filtro."}
          </p>
        ) : (
          sortedFilteredItems.map((it) => (
            <FinanceItemCard
              key={it.id}
              item={it}
              tipo={tipo}
              competencia={competencia}
              expanded={expandedId === it.id}
              monthKeys={monthKeys}
              projectOptions={projectOptions}
              readOnly={financeReadOnly}
              onToggle={() => setExpandedId((prev) => (prev === it.id ? null : it.id))}
              onDelete={() => void handleDelete(it.id)}
              onSaved={loadAll}
            />
          ))
        )}
      </section>
        </>
      )}
    </div>
  );
}

function KpiCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-xl font-semibold tabular-nums text-slate-900 ${accent ?? ""}`}>{value}</p>
    </div>
  );
}

function PendingEntriesSection({
  pendencias,
  competencia,
  readOnly,
  readOnlyTitle,
  onPreencher,
}: {
  pendencias: PendenciaLancamento[];
  competencia: string;
  readOnly: boolean;
  readOnlyTitle?: string;
  onPreencher: (itemId: string) => void;
}) {
  if (pendencias.length === 0) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-medium text-slate-800">Pendências de Lançamento</h2>
            <p className="text-xs text-slate-500">
              Itens obrigatórios mensais sem valor lançado na competência selecionada.
            </p>
          </div>
          <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800">
            Tudo em dia
          </span>
        </div>
        <p className="mt-3 text-sm text-slate-500">
          Nenhuma pendência para {mesLabel(competencia)}/{competencia.split("-")[0]}.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-amber-200 bg-amber-50/40 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-amber-900">Pendências de Lançamento</h2>
          <p className="text-xs text-amber-800/80">
            Itens obrigatórios mensais sem valor lançado na competência selecionada. Apenas
            monitoramento — nenhum lançamento financeiro é criado automaticamente.
          </p>
        </div>
        <span className="rounded-full bg-amber-200 px-2.5 py-1 text-xs font-semibold text-amber-900">
          {pendencias.length} {pendencias.length === 1 ? "pendência" : "pendências"}
        </span>
      </div>
      <div className="mt-3 overflow-x-auto rounded-lg border border-amber-200 bg-white">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-amber-100 bg-amber-50/60 text-xs uppercase tracking-wide text-amber-900/70">
            <tr>
              <th className="px-3 py-2 font-medium">Item</th>
              <th className="px-3 py-2 font-medium">Competência</th>
              <th className="px-3 py-2 text-right font-medium">Último Valor</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {pendencias.map((p) => (
              <tr key={p.item_id} className="hover:bg-amber-50/40">
                <td className="px-3 py-2">
                  <span className="font-medium text-slate-900">{p.nome}</span>
                  {p.cost_center ? (
                    <span className="ml-2 text-xs text-slate-500">{p.cost_center}</span>
                  ) : null}
                </td>
                <td className="px-3 py-2 tabular-nums text-slate-700">
                  {mesLabel(p.competencia)}/{p.competencia.split("-")[0]}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                  {typeof p.ultimo_valor === "number" ? (
                    <span>
                      {formatBRL(p.ultimo_valor)}
                      {p.ultimo_mes ? (
                        <span className="ml-1 text-xs text-slate-400">
                          ({mesLabel(p.ultimo_mes)}/{p.ultimo_mes.split("-")[0]})
                        </span>
                      ) : null}
                    </span>
                  ) : (
                    <span className="text-slate-400">Sem histórico</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-900">
                    ⚠ Aguardando valor
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => onPreencher(p.item_id)}
                    disabled={readOnly}
                    title={readOnly ? readOnlyTitle : "Preencher valor na competência atual"}
                    className="rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-amber-600 disabled:opacity-50"
                  >
                    Preencher valor
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FinanceItemCard({
  item,
  tipo,
  competencia,
  expanded,
  monthKeys,
  projectOptions,
  readOnly,
  onToggle,
  onDelete,
  onSaved,
}: {
  item: CompanyFinancialItem;
  tipo: TipoFinanceiro;
  competencia: string;
  expanded: boolean;
  monthKeys: string[];
  projectOptions: Project[];
  readOnly: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onSaved: () => Promise<void>;
}) {
  const ref = item.valor_referencia;
  const ratio = item.progresso;
  const pct = Math.min(100, ratio * 100);
  const hasLegal = Boolean(item.has_legal_process);
  const hasReneg = Boolean(item.has_renegotiation);
  const isMatrixCollaborator = tipo === "custo_fixo" && item.item_type === "COLABORADOR_MATRIZ";
  const itemTypeLabel = tipo === "custo_fixo" ? (isMatrixCollaborator ? "Colaborador" : "Manual") : null;

  const [localPayments, setLocalPayments] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const p of item.pagamentos) {
      m[p.mes] = p.valor > 0 ? formatCurrencyInputFromApi(p.valor) : "";
    }
    return m;
  });
  const [editingStructure, setEditingStructure] = useState(false);
  const [structureSaving, setStructureSaving] = useState(false);
  const [structureName, setStructureName] = useState(item.nome);
  const [structureRef, setStructureRef] = useState(formatCurrencyInputFromApi(item.valor_referencia));
  const [structureCategory, setStructureCategory] = useState(item.category ?? defaultCategory(tipo));
  const [structureCostCenterRef, setStructureCostCenterRef] = useState(() =>
    itemCostCenterRef(item, tipo, projectOptions),
  );
  const [structureDescription, setStructureDescription] = useState(item.description ?? "");
  const [structureRecurrence, setStructureRecurrence] = useState(item.recurrence ?? defaultRecurrence(tipo));
  const [structureIsMonthlyRequired, setStructureIsMonthlyRequired] = useState(
    Boolean(item.is_monthly_required),
  );
  const [structurePercentual, setStructurePercentual] = useState(
    typeof item.percentual === "number" ? String(item.percentual).replace(".", ",") : "",
  );
  const [structureHasLegal, setStructureHasLegal] = useState(Boolean(item.has_legal_process));
  const [structureHasReneg, setStructureHasReneg] = useState(Boolean(item.has_renegotiation));
  const [structureRenegAmount, setStructureRenegAmount] = useState(
    typeof item.renegotiated_amount === "number" ? formatCurrencyInputFromApi(item.renegotiated_amount) : "",
  );
  const [structureRenegType, setStructureRenegType] = useState<RenegotiationType>(
    item.renegotiation_type ?? "UNIQUE",
  );
  const [structureInstallments, setStructureInstallments] = useState(
    typeof item.installment_count === "number" ? String(item.installment_count) : "",
  );
  const [structureInstallmentValue, setStructureInstallmentValue] = useState(
    typeof item.installment_value === "number" ? formatCurrencyInputFromApi(item.installment_value) : "",
  );
  const [structureError, setStructureError] = useState<string | null>(null);
  const [structureSuccess, setStructureSuccess] = useState<string | null>(null);

  const paymentsSyncKey = JSON.stringify(
    item.pagamentos.map((p) => ({ mes: p.mes, valor: p.valor })).sort((a, b) => a.mes.localeCompare(b.mes)),
  );
  useEffect(() => {
    const m: Record<string, string> = {};
    for (const p of item.pagamentos) {
      m[p.mes] = p.valor > 0 ? formatCurrencyInputFromApi(p.valor) : "";
    }
    setLocalPayments(m);
  }, [item.id, paymentsSyncKey]);

  useEffect(() => {
    if (editingStructure) return;
    setStructureName(item.nome);
    setStructureRef(formatCurrencyInputFromApi(item.valor_referencia));
    setStructureCategory(item.category ?? defaultCategory(tipo));
    setStructureCostCenterRef(itemCostCenterRef(item, tipo, projectOptions));
    setStructureDescription(item.description ?? "");
    setStructureRecurrence(item.recurrence ?? defaultRecurrence(tipo));
    setStructureIsMonthlyRequired(Boolean(item.is_monthly_required));
    setStructurePercentual(typeof item.percentual === "number" ? String(item.percentual).replace(".", ",") : "");
    setStructureHasLegal(Boolean(item.has_legal_process));
    setStructureHasReneg(Boolean(item.has_renegotiation));
    setStructureRenegAmount(
      typeof item.renegotiated_amount === "number" ? formatCurrencyInputFromApi(item.renegotiated_amount) : "",
    );
    setStructureRenegType(item.renegotiation_type ?? "UNIQUE");
    setStructureInstallments(typeof item.installment_count === "number" ? String(item.installment_count) : "");
    setStructureInstallmentValue(
      typeof item.installment_value === "number" ? formatCurrencyInputFromApi(item.installment_value) : "",
    );
    setStructureError(null);
    setStructureSuccess(null);
  }, [item, tipo, projectOptions, editingStructure]);

  const [paymentsError, setPaymentsError] = useState<string | null>(null);
  const [paymentsSuccess, setPaymentsSuccess] = useState<string | null>(null);
  const [paymentsSaving, setPaymentsSaving] = useState(false);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const persist = useCallback(async () => {
    if (readOnly) {
      setPaymentsError(GESTOR_GLOBAL_EDIT_TOOLTIP);
      return;
    }
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
      debounceTimer.current = null;
    }
    setPaymentsError(null);
    setPaymentsSuccess(null);
    const pagamentos = buildPagamentosPayload(monthKeys, localPayments, item.pagamentos);
    if (pagamentos.length === 0) {
      setPaymentsError("Informe um valor em pelo menos um mês antes de salvar.");
      return;
    }
    if (import.meta.env.DEV) {
      console.info("[company-finance] Salvar agora clique", {
        item_id: item.id,
        competencia,
        pagamentos,
      });
    }
    setPaymentsSaving(true);
    try {
      const saved = await replaceCompanyFinancePayments(item.id, pagamentos, competencia);
      const m: Record<string, string> = {};
      for (const p of saved.pagamentos) {
        m[p.mes] = p.valor > 0 ? formatCurrencyInputFromApi(p.valor) : "";
      }
      setLocalPayments(m);
      await onSaved();
      setPaymentsSuccess("Pagamentos salvos. Contas a Pagar será atualizado nos meses já gerados.");
      if (import.meta.env.DEV) {
        console.info("[company-finance] Salvar agora OK", saved);
      }
    } catch (e) {
      if (import.meta.env.DEV) {
        console.error("[company-finance] Salvar agora erro", e);
      }
      if (isAxiosError(e)) {
        const detail = e.response?.data?.detail;
        setPaymentsError(typeof detail === "string" ? detail : "Não foi possível salvar os pagamentos.");
      } else {
        setPaymentsError("Não foi possível salvar os pagamentos.");
      }
    } finally {
      setPaymentsSaving(false);
    }
  }, [readOnly, monthKeys, localPayments, item.id, item.pagamentos, competencia, onSaved]);

  const persistRef = useRef(persist);
  persistRef.current = persist;

  function updateMonth(mes: string, raw: string) {
    if (readOnly) return;
    setLocalPayments((prev) => ({ ...prev, [mes]: raw }));
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => void persistRef.current(), 450);
  }

  async function saveStructure() {
    if (readOnly) return;
    const nome = structureName.trim();
    if (!nome) {
      setStructureError("Informe o nome do item.");
      return;
    }
    if (!structureCostCenterRef) {
      setStructureError("Selecione o centro de custo.");
      return;
    }
    const payload: Parameters<typeof updateCompanyFinanceItem>[1] = {
      nome,
      valor_referencia: parseBRLInput(structureRef),
      category: structureCategory.trim() || defaultCategory(tipo),
      cost_center_ref: structureCostCenterRef,
      description: structureDescription.trim() || null,
      recurrence: structureRecurrence || defaultRecurrence(tipo),
    };
    if (isMatrixCollaborator) {
      payload.percentual = Number(String(structurePercentual || "0").replace(",", "."));
    }
    if (tipo === "custo_fixo") {
      payload.is_monthly_required = structureIsMonthlyRequired;
    }
    if (tipo === "endividamento") {
      payload.has_legal_process = structureHasLegal;
      payload.has_renegotiation = structureHasReneg;
      payload.renegotiated_amount = structureHasReneg ? parseBRLInput(structureRenegAmount) : null;
      payload.renegotiation_type = structureHasReneg ? structureRenegType : null;
      if (structureHasReneg && structureRenegType === "INSTALLMENTS") {
        payload.installment_count = Number.parseInt(structureInstallments || "0", 10);
        payload.installment_value = parseBRLInput(structureInstallmentValue);
      }
    }

    setStructureSaving(true);
    setStructureError(null);
    setStructureSuccess(null);
    try {
      const saved = await updateCompanyFinanceItem(item.id, payload, competencia);
      setStructureSuccess("Estrutura salva. Contas a Pagar será atualizado para meses em aberto.");
      setEditingStructure(false);
      await onSaved();
      if (import.meta.env.DEV) {
        console.info("[company-finance] estrutura salva no card", {
          sent: payload,
          received: saved,
        });
      }
    } catch (err) {
      if (isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        setStructureError(typeof detail === "string" ? detail : "Não foi possível salvar a estrutura.");
        if (import.meta.env.DEV) {
          console.error("[company-finance] PATCH estrutura falhou", err.response?.status, err.response?.data);
        }
      } else {
        setStructureError("Não foi possível salvar a estrutura.");
      }
    } finally {
      setStructureSaving(false);
    }
  }

  return (
    <article
      id={`cf-item-${item.id}`}
      className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full flex-col gap-3 p-4 text-left transition hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-slate-900">{item.nome}</h3>
            {tipo === "custo_fixo" && item.is_monthly_required && (
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
                Obrigatório mensal
              </span>
            )}
            {tipo === "endividamento" && item.status === "quitado" && (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">Quitado</span>
            )}
            {tipo === "endividamento" && hasLegal && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">⚖️ Em processo</span>
            )}
            {tipo === "endividamento" && hasReneg && (
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-900">🔁 Renegociado</span>
            )}
          </div>
          <dl className="mt-2 grid gap-2 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-xs text-slate-500">Referência</dt>
              <dd className="font-medium text-slate-900">{formatBRL(ref)}</dd>
            </div>
            {tipo === "custo_fixo" && (
              <div>
                <dt className="text-xs text-slate-500">Tipo</dt>
                <dd className="font-medium text-slate-900">{itemTypeLabel}</dd>
              </div>
            )}
            {isMatrixCollaborator && (
              <div>
                <dt className="text-xs text-slate-500">Percentual</dt>
                <dd className="font-medium text-slate-900">{typeof item.percentual === "number" ? `${item.percentual}%` : "—"}</dd>
              </div>
            )}
            <div>
              <dt className="text-xs text-slate-500">{tipo === "endividamento" ? "Total pago" : "Total pago (hist.)"}</dt>
              <dd className="font-medium text-slate-900">{formatBRL(item.total_pago)}</dd>
            </div>
            {tipo === "endividamento" && item.restante != null && (
              <div>
                <dt className="text-xs text-slate-500">Restante</dt>
                <dd className="font-medium text-slate-900">{formatBRL(item.restante)}</dd>
              </div>
            )}
            <div>
              <dt className="text-xs text-slate-500">Pago no mês</dt>
              <dd className="font-medium text-slate-900">{formatBRL(item.pago_mes)}</dd>
            </div>
          </dl>
          <div className="mt-3">
            <div className="flex justify-between text-xs text-slate-500">
              <span>Progresso</span>
              <span className="font-medium tabular-nums text-slate-800">{pct.toFixed(1)}%</span>
            </div>
            <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-all ${progressBarClass(ratio)}`}
                style={{ width: `${Math.min(100, pct)}%` }}
              />
            </div>
          </div>
        </div>
        <span className="text-slate-400">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50/90 p-4">
          <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Estrutura do item</p>
                <p className="mt-1 text-xs text-slate-500">
                  Alterações estruturais atualizam meses futuros e snapshots abertos; lançamentos já pagos ficam preservados.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditingStructure((v) => !v)}
                disabled={readOnly || structureSaving}
                title={readOnly ? GESTOR_GLOBAL_EDIT_TOOLTIP : undefined}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
              >
                {editingStructure ? "Fechar edição" : "Editar estrutura"}
              </button>
            </div>
            {!editingStructure ? (
              <dl className="mt-3 grid gap-3 text-sm text-slate-700 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="text-xs text-slate-500">Categoria</dt>
                  <dd className="font-medium text-slate-900">{item.category ?? defaultCategory(tipo)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Centro de custo</dt>
                  <dd className="font-medium text-slate-900">{item.cost_center}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Recorrência</dt>
                  <dd className="font-medium text-slate-900">{item.recurrence ?? defaultRecurrence(tipo)}</dd>
                </div>
                {tipo === "custo_fixo" && (
                  <div>
                    <dt className="text-xs text-slate-500">Obrigatório mensal</dt>
                    <dd className="font-medium text-slate-900">{item.is_monthly_required ? "Sim" : "Não"}</dd>
                  </div>
                )}
                <div className="sm:col-span-2 lg:col-span-4">
                  <dt className="text-xs text-slate-500">Descrição</dt>
                  <dd className="whitespace-pre-wrap text-slate-900">{item.description?.trim() || "—"}</dd>
                </div>
              </dl>
            ) : (
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-slate-600">Nome</span>
                  <input
                    value={structureName}
                    onChange={(e) => setStructureName(e.target.value)}
                    className="rounded border border-slate-300 px-2 py-1.5"
                    disabled={readOnly || structureSaving}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-slate-600">Valor base</span>
                  <input
                    value={structureRef}
                    onChange={(e) => setStructureRef(e.target.value)}
                    className="rounded border border-slate-300 px-2 py-1.5"
                    inputMode="decimal"
                    disabled={readOnly || structureSaving}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-slate-600">Categoria</span>
                  <input
                    value={structureCategory}
                    onChange={(e) => setStructureCategory(e.target.value)}
                    className="rounded border border-slate-300 px-2 py-1.5"
                    disabled={readOnly || structureSaving}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-slate-600">Centro de custo *</span>
                  <CostCenterSelect
                    value={structureCostCenterRef}
                    onChange={setStructureCostCenterRef}
                    projects={projectOptions}
                    disabled={readOnly || structureSaving || isMatrixCollaborator}
                    className="rounded border border-slate-300 bg-white px-2 py-1.5"
                    legacyLabel={item.cost_center}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-slate-600">Recorrência</span>
                  <select
                    value={structureRecurrence}
                    onChange={(e) => setStructureRecurrence(e.target.value)}
                    className="rounded border border-slate-300 bg-white px-2 py-1.5"
                    disabled={readOnly || structureSaving}
                  >
                    <option value="MONTHLY">Mensal</option>
                    <option value="INSTALLMENTS">Parcelada</option>
                    <option value="UNIQUE">Única</option>
                    <option value="VARIABLE">Variável</option>
                  </select>
                </label>
                {tipo === "custo_fixo" && (
                  <label className="flex items-center gap-2 pt-6 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={structureIsMonthlyRequired}
                      onChange={(e) => setStructureIsMonthlyRequired(e.target.checked)}
                      disabled={readOnly || structureSaving}
                    />
                    <span>Obrigatório mensal</span>
                  </label>
                )}
                {isMatrixCollaborator && (
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-slate-600">Percentual (%)</span>
                    <input
                      value={structurePercentual}
                      onChange={(e) => setStructurePercentual(e.target.value)}
                      className="rounded border border-slate-300 px-2 py-1.5"
                      inputMode="decimal"
                      disabled={readOnly || structureSaving}
                    />
                  </label>
                )}
                {tipo === "endividamento" && (
                  <>
                    <label className="flex items-center gap-2 pt-6 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={structureHasLegal}
                        onChange={(e) => setStructureHasLegal(e.target.checked)}
                        disabled={readOnly || structureSaving}
                      />
                      <span>Processo judicial</span>
                    </label>
                    <label className="flex items-center gap-2 pt-6 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={structureHasReneg}
                        onChange={(e) => setStructureHasReneg(e.target.checked)}
                        disabled={readOnly || structureSaving}
                      />
                      <span>Renegociação</span>
                    </label>
                  </>
                )}
                {tipo === "endividamento" && structureHasReneg && (
                  <>
                    <label className="flex flex-col gap-1 text-sm">
                      <span className="text-slate-600">Valor renegociado</span>
                      <input
                        value={structureRenegAmount}
                        onChange={(e) => setStructureRenegAmount(e.target.value)}
                        className="rounded border border-slate-300 px-2 py-1.5"
                        inputMode="decimal"
                        disabled={readOnly || structureSaving}
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-sm">
                      <span className="text-slate-600">Tipo renegociação</span>
                      <select
                        value={structureRenegType}
                        onChange={(e) => setStructureRenegType(e.target.value as RenegotiationType)}
                        className="rounded border border-slate-300 bg-white px-2 py-1.5"
                        disabled={readOnly || structureSaving}
                      >
                        <option value="UNIQUE">Única</option>
                        <option value="INSTALLMENTS">Parcelada</option>
                      </select>
                    </label>
                    {structureRenegType === "INSTALLMENTS" && (
                      <>
                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-slate-600">Parcelas</span>
                          <input
                            value={structureInstallments}
                            onChange={(e) => setStructureInstallments(e.target.value)}
                            className="rounded border border-slate-300 px-2 py-1.5"
                            inputMode="numeric"
                            disabled={readOnly || structureSaving}
                          />
                        </label>
                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-slate-600">Valor parcela</span>
                          <input
                            value={structureInstallmentValue}
                            onChange={(e) => setStructureInstallmentValue(e.target.value)}
                            className="rounded border border-slate-300 px-2 py-1.5"
                            inputMode="decimal"
                            disabled={readOnly || structureSaving}
                          />
                        </label>
                      </>
                    )}
                  </>
                )}
                <label className="flex flex-col gap-1 text-sm sm:col-span-2 lg:col-span-4">
                  <span className="text-slate-600">Descrição</span>
                  <textarea
                    value={structureDescription}
                    onChange={(e) => setStructureDescription(e.target.value)}
                    rows={3}
                    className="rounded border border-slate-300 px-2 py-1.5"
                    disabled={readOnly || structureSaving}
                  />
                </label>
                {structureError ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 sm:col-span-2 lg:col-span-4">
                    {structureError}
                  </div>
                ) : null}
                {structureSuccess ? (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 sm:col-span-2 lg:col-span-4">
                    {structureSuccess}
                  </div>
                ) : null}
                <div className="flex gap-2 sm:col-span-2 lg:col-span-4">
                  <button
                    type="button"
                    onClick={() => void saveStructure()}
                    disabled={readOnly || structureSaving}
                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {structureSaving ? "Salvando…" : "Salvar estrutura"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingStructure(false)}
                    disabled={structureSaving}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </div>

          {tipo === "endividamento" && (hasLegal || hasReneg) && (
            <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Status e renegociação</p>
              <dl className="mt-2 grid gap-3 text-sm text-slate-700 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="text-xs text-slate-500">Processo judicial</dt>
                  <dd className="font-medium text-slate-900">{hasLegal ? "Sim" : "Não"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Renegociação</dt>
                  <dd className="font-medium text-slate-900">{hasReneg ? "Sim" : "Não"}</dd>
                </div>
                {hasReneg && (
                  <>
                    <div>
                      <dt className="text-xs text-slate-500">Valor renegociado</dt>
                      <dd className="font-medium text-slate-900">
                        {typeof item.renegotiated_amount === "number" ? formatBRL(item.renegotiated_amount) : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-slate-500">Tipo</dt>
                      <dd className="font-medium text-slate-900">{item.renegotiation_type ?? "—"}</dd>
                    </div>
                    {item.renegotiation_type === "INSTALLMENTS" && (
                      <>
                        <div>
                          <dt className="text-xs text-slate-500">Parcelas</dt>
                          <dd className="font-medium text-slate-900">{item.installment_count ?? "—"}</dd>
                        </div>
                        <div>
                          <dt className="text-xs text-slate-500">Valor da parcela</dt>
                          <dd className="font-medium text-slate-900">
                            {typeof item.installment_value === "number" ? formatBRL(item.installment_value) : "—"}
                          </dd>
                        </div>
                      </>
                    )}
                  </>
                )}
              </dl>
            </div>
          )}
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Pagamentos por mês (12 meses)</p>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {monthKeys.map((mes) => (
              <label key={mes} className="flex flex-col gap-1 text-xs">
                <span className="font-medium text-slate-600">
                  {mesLabel(mes)} <span className="font-normal text-slate-400">({mes})</span>
                </span>
                <input
                  value={localPayments[mes] ?? ""}
                  onChange={(e) => updateMonth(mes, e.target.value)}
                  onBlur={() => void persistRef.current()}
                  className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                  placeholder="0"
                  inputMode="decimal"
                  disabled={readOnly}
                  title={readOnly ? GESTOR_GLOBAL_EDIT_TOOLTIP : undefined}
                />
              </label>
            ))}
          </div>
          {(paymentsError || paymentsSuccess) && (
            <div className="mt-3 text-sm">
              {paymentsError ? <p className="text-red-700">{paymentsError}</p> : null}
              {paymentsSuccess ? <p className="text-emerald-700">{paymentsSuccess}</p> : null}
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                if (import.meta.env.DEV) console.info("[company-finance] botão Salvar agora");
                void persist();
              }}
              disabled={readOnly || paymentsSaving}
              title={readOnly ? GESTOR_GLOBAL_EDIT_TOOLTIP : undefined}
              className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
            >
              {paymentsSaving ? "Salvando…" : "Salvar agora"}
            </button>
            <button
              type="button"
              onClick={onDelete}
              disabled={readOnly}
              title={readOnly ? GESTOR_GLOBAL_EDIT_TOOLTIP : undefined}
              className="rounded-lg px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              Excluir item
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
