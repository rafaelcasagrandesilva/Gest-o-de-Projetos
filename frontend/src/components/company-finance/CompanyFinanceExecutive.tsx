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
  listCompanyFinanceItems,
  replaceCompanyFinancePayments,
  updateCompanyFinanceItem,
  type ChartPoint,
  type CompanyFinancialItem,
  type RenegotiationType,
  type TipoFinanceiro,
} from "@/services/companyFinance";
import { listEmployees, type Employee } from "@/services/employees";
import { isAxiosError } from "axios";
import { GESTOR_GLOBAL_EDIT_TOOLTIP, useGestorGlobalReadOnly } from "@/hooks/useGestorGlobalReadOnly";
import { usePermission } from "@/hooks/usePermission";

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
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function parseBRLInput(raw: string): number {
  const t = raw.replace(/\s/g, "").replace(/R\$\s?/i, "");
  const normalized = t.replace(/\./g, "").replace(",", ".");
  const n = Number.parseFloat(normalized);
  return Number.isFinite(n) ? Math.max(0, n) : 0;
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

function defaultCostCenter(tipo: TipoFinanceiro): string {
  return tipo === "endividamento" ? "Financeiro" : "Administrativo";
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
  const [chartPoints, setChartPoints] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [creditorFilter, setCreditorFilter] = useState<DebtCreditorFilter>("ALL");
  const [draftName, setDraftName] = useState("");
  const [draftRef, setDraftRef] = useState("");
  const [draftCategory, setDraftCategory] = useState(() => defaultCategory(tipo));
  const [draftCostCenter, setDraftCostCenter] = useState(() => defaultCostCenter(tipo));
  const [draftDescription, setDraftDescription] = useState("");
  const [draftRecurrence, setDraftRecurrence] = useState(() => defaultRecurrence(tipo));
  const [draftItemType, setDraftItemType] = useState<"MANUAL" | "COLABORADOR_MATRIZ">("MANUAL");
  const [draftEmployeeQuery, setDraftEmployeeQuery] = useState("");
  const [draftEmployeeOptions, setDraftEmployeeOptions] = useState<Employee[]>([]);
  const [draftEmployeeOpen, setDraftEmployeeOpen] = useState(false);
  const [draftEmployeeLoading, setDraftEmployeeLoading] = useState(false);
  const [draftEmployeeId, setDraftEmployeeId] = useState("");
  const [draftPercentual, setDraftPercentual] = useState("100");
  const [draftHasLegalProcess, setDraftHasLegalProcess] = useState(false);
  const [draftHasRenegotiation, setDraftHasRenegotiation] = useState(false);
  const [draftRenegotiatedAmount, setDraftRenegotiatedAmount] = useState("");
  const [draftRenegotiationType, setDraftRenegotiationType] = useState<RenegotiationType>("UNIQUE");
  const [draftInstallmentCount, setDraftInstallmentCount] = useState("");
  const [draftInstallmentValue, setDraftInstallmentValue] = useState("");
  const [saving, setSaving] = useState(false);

  const monthKeys = useMemo(() => rollingMonthKeys(competencia), [competencia]);

  useEffect(() => {
    setDraftCategory(defaultCategory(tipo));
    setDraftCostCenter(defaultCostCenter(tipo));
    setDraftRecurrence(defaultRecurrence(tipo));
  }, [tipo]);

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
      } else {
        const k = await fetchKpiCustosFixos(competencia);
        setKpiFixed(k);
        setKpiDebt(null);
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
    if (tipo !== "endividamento") return items;
    return items.filter((it) => {
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
  }, [tipo, items, creditorFilter]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (financeReadOnly) return;
    const nome =
      tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ"
        ? (selectedEmployee?.full_name ?? "").trim()
        : draftName.trim();
    const ref = calculatedRef;
    if (!nome || ref < 0) return;
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
        cost_center: draftCostCenter.trim() || defaultCostCenter(tipo),
        description: draftDescription.trim() || null,
        recurrence: draftRecurrence.trim() || defaultRecurrence(tipo),
        item_type: tipo === "custo_fixo" ? draftItemType : "MANUAL",
        employee_id: tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ" ? draftEmployeeId : null,
        percentual: tipo === "custo_fixo" && draftItemType === "COLABORADOR_MATRIZ" ? percentualN : null,
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
      setDraftName("");
      setDraftRef("");
      setDraftCategory(defaultCategory(tipo));
      setDraftCostCenter(defaultCostCenter(tipo));
      setDraftDescription("");
      setDraftRecurrence(defaultRecurrence(tipo));
      setDraftItemType("MANUAL");
      setDraftEmployeeQuery("");
      setDraftEmployeeOptions([]);
      setDraftEmployeeId("");
      setDraftPercentual("100");
      setDraftHasLegalProcess(false);
      setDraftHasRenegotiation(false);
      setDraftRenegotiatedAmount("");
      setDraftRenegotiationType("UNIQUE");
      setDraftInstallmentCount("");
      setDraftInstallmentValue("");
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

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 border-b border-slate-200 pb-6 sm:flex-row sm:items-end sm:justify-between">
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
          </>
        )}
        {loading && !kpiDebt && !kpiFixed && (
          <p className="col-span-full text-sm text-slate-500">Carregando indicadores…</p>
        )}
      </section>

      {/* Gráficos */}
      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="text-sm font-medium text-slate-800">
                {tipo === "endividamento" ? "Evolução do saldo restante" : "Pagamentos acumulados"}
              </h2>
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
                    saldoPeriodDelta < 0 ? "text-emerald-700" : saldoPeriodDelta > 0 ? "text-amber-800" : "text-slate-700"
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
                    <Line type="monotone" dataKey="acumulado" name="Acumulado" stroke="#059669" strokeWidth={2} dot={false} />
                  )}
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-medium text-slate-800">Pagamentos por mês</h2>
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
      </section>

      {/* Novo item */}
      <section className="rounded-xl border border-slate-200 bg-slate-50/80 p-4">
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
                  ? String(calculatedRef).replace(".", ",")
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
            <span className="text-slate-600">Centro de custo</span>
            <input
              value={draftCostCenter}
              onChange={(e) => setDraftCostCenter(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
              disabled={financeReadOnly}
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
      </section>

      {/* Cards */}
      <section className="space-y-4">
        <h2 className="text-lg font-medium text-slate-900">Itens</h2>
        {loading && items.length === 0 ? (
          <p className="text-sm text-slate-500">Carregando…</p>
        ) : filteredItems.length === 0 ? (
          <p className="text-sm text-slate-500">Nenhum item encontrado para este filtro.</p>
        ) : (
          filteredItems.map((it) => (
            <FinanceItemCard
              key={it.id}
              item={it}
              tipo={tipo}
              competencia={competencia}
              expanded={expandedId === it.id}
              monthKeys={monthKeys}
              readOnly={financeReadOnly}
              onToggle={() => setExpandedId((prev) => (prev === it.id ? null : it.id))}
              onDelete={() => void handleDelete(it.id)}
              onSaved={loadAll}
            />
          ))
        )}
      </section>
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

function FinanceItemCard({
  item,
  tipo,
  competencia,
  expanded,
  monthKeys,
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
      m[p.mes] = p.valor > 0 ? String(p.valor).replace(".", ",") : "";
    }
    return m;
  });
  const [editingStructure, setEditingStructure] = useState(false);
  const [structureSaving, setStructureSaving] = useState(false);
  const [structureName, setStructureName] = useState(item.nome);
  const [structureRef, setStructureRef] = useState(String(item.valor_referencia).replace(".", ","));
  const [structureCategory, setStructureCategory] = useState(item.category ?? defaultCategory(tipo));
  const [structureCostCenter, setStructureCostCenter] = useState(item.cost_center ?? defaultCostCenter(tipo));
  const [structureDescription, setStructureDescription] = useState(item.description ?? "");
  const [structureRecurrence, setStructureRecurrence] = useState(item.recurrence ?? defaultRecurrence(tipo));
  const [structurePercentual, setStructurePercentual] = useState(
    typeof item.percentual === "number" ? String(item.percentual).replace(".", ",") : "",
  );
  const [structureHasLegal, setStructureHasLegal] = useState(Boolean(item.has_legal_process));
  const [structureHasReneg, setStructureHasReneg] = useState(Boolean(item.has_renegotiation));
  const [structureRenegAmount, setStructureRenegAmount] = useState(
    typeof item.renegotiated_amount === "number" ? String(item.renegotiated_amount).replace(".", ",") : "",
  );
  const [structureRenegType, setStructureRenegType] = useState<RenegotiationType>(
    item.renegotiation_type ?? "UNIQUE",
  );
  const [structureInstallments, setStructureInstallments] = useState(
    typeof item.installment_count === "number" ? String(item.installment_count) : "",
  );
  const [structureInstallmentValue, setStructureInstallmentValue] = useState(
    typeof item.installment_value === "number" ? String(item.installment_value).replace(".", ",") : "",
  );

  const paymentsSyncKey = JSON.stringify(
    item.pagamentos.map((p) => ({ mes: p.mes, valor: p.valor })).sort((a, b) => a.mes.localeCompare(b.mes)),
  );
  useEffect(() => {
    const m: Record<string, string> = {};
    for (const p of item.pagamentos) {
      m[p.mes] = p.valor > 0 ? String(p.valor).replace(".", ",") : "";
    }
    setLocalPayments(m);
  }, [item.id, paymentsSyncKey]);

  useEffect(() => {
    setStructureName(item.nome);
    setStructureRef(String(item.valor_referencia).replace(".", ","));
    setStructureCategory(item.category ?? defaultCategory(tipo));
    setStructureCostCenter(item.cost_center ?? defaultCostCenter(tipo));
    setStructureDescription(item.description ?? "");
    setStructureRecurrence(item.recurrence ?? defaultRecurrence(tipo));
    setStructurePercentual(typeof item.percentual === "number" ? String(item.percentual).replace(".", ",") : "");
    setStructureHasLegal(Boolean(item.has_legal_process));
    setStructureHasReneg(Boolean(item.has_renegotiation));
    setStructureRenegAmount(
      typeof item.renegotiated_amount === "number" ? String(item.renegotiated_amount).replace(".", ",") : "",
    );
    setStructureRenegType(item.renegotiation_type ?? "UNIQUE");
    setStructureInstallments(typeof item.installment_count === "number" ? String(item.installment_count) : "");
    setStructureInstallmentValue(
      typeof item.installment_value === "number" ? String(item.installment_value).replace(".", ",") : "",
    );
  }, [item, tipo]);

  const persist = useCallback(async () => {
    if (readOnly) return;
    const pagamentos = monthKeys.map((mes) => ({
      mes,
      valor: parseBRLInput(localPayments[mes] ?? ""),
    }));
    await replaceCompanyFinancePayments(item.id, pagamentos, competencia);
    await onSaved();
  }, [readOnly, monthKeys, localPayments, item.id, competencia, onSaved]);

  const persistRef = useRef(persist);
  persistRef.current = persist;
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function updateMonth(mes: string, raw: string) {
    if (readOnly) return;
    setLocalPayments((prev) => ({ ...prev, [mes]: raw }));
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => void persistRef.current(), 450);
  }

  async function saveStructure() {
    if (readOnly) return;
    const nome = structureName.trim();
    if (!nome) return;
    setStructureSaving(true);
    try {
      await updateCompanyFinanceItem(
        item.id,
        {
          nome,
          valor_referencia: parseBRLInput(structureRef),
          category: structureCategory.trim() || defaultCategory(tipo),
          cost_center: structureCostCenter.trim() || defaultCostCenter(tipo),
          description: structureDescription.trim() || null,
          recurrence: structureRecurrence || defaultRecurrence(tipo),
          percentual: isMatrixCollaborator ? Number(String(structurePercentual || "0").replace(",", ".")) : null,
          has_legal_process: tipo === "endividamento" ? structureHasLegal : false,
          has_renegotiation: tipo === "endividamento" ? structureHasReneg : false,
          renegotiated_amount: tipo === "endividamento" && structureHasReneg ? parseBRLInput(structureRenegAmount) : null,
          renegotiation_type: tipo === "endividamento" && structureHasReneg ? structureRenegType : null,
          installment_count:
            tipo === "endividamento" && structureHasReneg && structureRenegType === "INSTALLMENTS"
              ? Number.parseInt(structureInstallments || "0", 10)
              : null,
          installment_value:
            tipo === "endividamento" && structureHasReneg && structureRenegType === "INSTALLMENTS"
              ? parseBRLInput(structureInstallmentValue)
              : null,
        },
        competencia,
      );
      setEditingStructure(false);
      await onSaved();
    } finally {
      setStructureSaving(false);
    }
  }

  return (
    <article className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full flex-col gap-3 p-4 text-left transition hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-slate-900">{item.nome}</h3>
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
                  <dd className="font-medium text-slate-900">{item.cost_center ?? defaultCostCenter(tipo)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Recorrência</dt>
                  <dd className="font-medium text-slate-900">{item.recurrence ?? defaultRecurrence(tipo)}</dd>
                </div>
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
                  <span className="text-slate-600">Centro de custo</span>
                  <input
                    value={structureCostCenter}
                    onChange={(e) => setStructureCostCenter(e.target.value)}
                    className="rounded border border-slate-300 px-2 py-1.5"
                    disabled={readOnly || structureSaving}
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
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void persist()}
              disabled={readOnly}
              title={readOnly ? GESTOR_GLOBAL_EDIT_TOOLTIP : undefined}
              className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
            >
              Salvar agora
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
