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
  type ChartPoint,
  type CompanyFinancialItem,
  type TipoFinanceiro,
} from "@/services/companyFinance";
import { isAxiosError } from "axios";
import { GESTOR_GLOBAL_EDIT_TOOLTIP, useGestorGlobalReadOnly } from "@/hooks/useGestorGlobalReadOnly";

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

type Props = {
  tipo: TipoFinanceiro;
  title: string;
  subtitle: string;
};

export function CompanyFinanceExecutive({ tipo, title, subtitle }: Props) {
  const gestorGlobalReadOnly = useGestorGlobalReadOnly();
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
  const [draftName, setDraftName] = useState("");
  const [draftRef, setDraftRef] = useState("");
  const [saving, setSaving] = useState(false);

  const monthKeys = useMemo(() => rollingMonthKeys(competencia), [competencia]);

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

  const barData = useMemo(
    () => chartPoints.map((p) => ({ mes: mesLabel(p.mes), pagamentos: p.pagamentos_mes })),
    [chartPoints],
  );

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (gestorGlobalReadOnly) return;
    const nome = draftName.trim();
    const ref = parseBRLInput(draftRef);
    if (!nome || ref < 0) return;
    setSaving(true);
    setError(null);
    try {
      await createCompanyFinanceItem({ tipo, nome, valor_referencia: ref });
      setDraftName("");
      setDraftRef("");
      await loadAll();
    } catch (err) {
      if (isAxiosError(err)) setError(String(err.response?.data?.detail ?? err.message));
      else setError("Não foi possível criar o item.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (gestorGlobalReadOnly) return;
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
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">Competência (mês de referência)</span>
          <input
            type="month"
            value={competencia}
            onChange={(e) => setCompetencia(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-slate-900 shadow-sm"
          />
        </label>
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
          <h2 className="text-sm font-medium text-slate-800">
            {tipo === "endividamento" ? "Evolução do saldo restante" : "Pagamentos acumulados"}
          </h2>
          <p className="text-xs text-slate-500">
            {tipo === "endividamento"
              ? "Soma do saldo devedor ao fim de cada mês"
              : "Soma acumulada dos pagamentos registrados"}
          </p>
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
                    width={40}
                  />
                  <Tooltip formatter={(v: number) => formatBRL(v)} />
                  <Legend />
                  {tipo === "endividamento" ? (
                    <Line type="monotone" dataKey="saldo" name="Saldo restante" stroke="#4F46E5" strokeWidth={2} dot={false} />
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
          <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-sm">
            <span className="text-slate-600">Nome</span>
            <input
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
              placeholder="Ex.: Financiamento veículos"
              required
              disabled={gestorGlobalReadOnly}
            />
          </label>
          <label className="flex w-full min-w-[160px] flex-col gap-1 text-sm sm:w-48">
            <span className="text-slate-600">
              {tipo === "endividamento" ? "Valor total da dívida" : "Valor mensal esperado"}
            </span>
            <input
              value={draftRef}
              onChange={(e) => setDraftRef(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
              placeholder="0,00"
              inputMode="decimal"
              disabled={gestorGlobalReadOnly}
            />
          </label>
          <button
            type="submit"
            disabled={saving || gestorGlobalReadOnly}
            title={gestorGlobalReadOnly ? GESTOR_GLOBAL_EDIT_TOOLTIP : undefined}
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
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-500">Nenhum item cadastrado.</p>
        ) : (
          items.map((it) => (
            <FinanceItemCard
              key={it.id}
              item={it}
              tipo={tipo}
              competencia={competencia}
              expanded={expandedId === it.id}
              monthKeys={monthKeys}
              readOnly={gestorGlobalReadOnly}
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

  const [localPayments, setLocalPayments] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const p of item.pagamentos) {
      m[p.mes] = p.valor > 0 ? String(p.valor).replace(".", ",") : "";
    }
    return m;
  });

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
          </div>
          <dl className="mt-2 grid gap-2 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-xs text-slate-500">Referência</dt>
              <dd className="font-medium text-slate-900">{formatBRL(ref)}</dd>
            </div>
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
