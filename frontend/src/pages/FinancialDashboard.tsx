import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  fetchFinancialDashboardBreakdown,
  type FinancialDashboardBreakdown,
  type FinancialDashboardBreakdownType,
  fetchFinancialDashboard,
} from "@/services/financialDashboard";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  LabelList,
} from "recharts";
import type { TooltipProps } from "recharts";
import { CHART_COLORS, formatBRLAxis } from "@/utils/chartTheme";

const MONTH_SHORT_PT = [
  "Jan",
  "Fev",
  "Mar",
  "Abr",
  "Mai",
  "Jun",
  "Jul",
  "Ago",
  "Set",
  "Out",
  "Nov",
  "Dez",
] as const;

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatPct(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return `${n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function monthToYm(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function parseYm(ym: string): { year: number; month: number } | null {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return null;
  return { year: y, month: m };
}

function formatMonthLabel(ym: string): string {
  const parsed = parseYm(ym.length >= 7 ? ym.slice(0, 7) : ym);
  if (!parsed) return ym;
  const mon = MONTH_SHORT_PT[parsed.month - 1] ?? String(parsed.month);
  return `${mon}/${parsed.year}`;
}

type ChartRow = {
  month: string;
  monthLabel: string;
  faturamento: number;
  pago: number;
  caixa: number;
};

type SingleBarRow = {
  name: string;
  valor: number;
  color: string;
  breakdownType: FinancialDashboardBreakdownType;
};

function computeYDomain(
  rows: ChartRow[],
  keys: { faturamento: boolean; pago: boolean; caixa: boolean },
): [number, number] {
  const vals: number[] = [0];
  for (const p of rows) {
    if (keys.faturamento) vals.push(p.faturamento);
    if (keys.pago) vals.push(p.pago);
    if (keys.caixa) vals.push(p.caixa);
  }
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || Math.max(Math.abs(max), Math.abs(min), 1);
  const pad = Math.max(span * 0.12, 500);
  return [min - pad, max + pad];
}

function EvolutionTooltip({
  active,
  payload,
}: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as ChartRow | undefined;
  if (!row) return null;
  const margem = row.faturamento > 0 ? (row.caixa / row.faturamento) * 100 : 0;
  const caixaNeg = row.caixa < -0.01;

  return (
    <div className="min-w-[220px] rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs shadow-lg">
      <p className="font-semibold text-slate-900">Mês: {row.monthLabel}</p>
      <dl className="mt-2 space-y-1.5 text-slate-700">
        <div className="flex justify-between gap-4">
          <dt>Faturamento</dt>
          <dd className="font-medium tabular-nums text-slate-900">{formatBRL(row.faturamento)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Custos</dt>
          <dd className="font-medium tabular-nums text-slate-900">{formatBRL(row.pago)}</dd>
        </div>
        <div className="flex justify-between gap-4 border-t border-slate-100 pt-1.5">
          <dt className={caixaNeg ? "font-medium text-red-800" : ""}>Resultado Caixa</dt>
          <dd className={`font-semibold tabular-nums ${caixaNeg ? "text-red-700" : "text-emerald-700"}`}>
            {formatBRL(row.caixa)}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Margem</dt>
          <dd className={`font-medium tabular-nums ${caixaNeg ? "text-red-700" : "text-slate-900"}`}>
            {formatPct(margem)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function SingleMonthBarTooltip({
  active,
  payload,
}: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as SingleBarRow | undefined;
  if (!row) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold text-slate-900">{row.name}</p>
      <p className="mt-1 tabular-nums font-medium text-slate-800">{formatBRL(row.valor)}</p>
    </div>
  );
}

export function FinancialDashboard() {
  const [month, setMonth] = useState(() => monthToYm(new Date()));
  const [monthsBack, setMonthsBack] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showRevenue, setShowRevenue] = useState(true);
  const [showCost, setShowCost] = useState(true);
  const [showProfit, setShowProfit] = useState(true);

  const [summary, setSummary] = useState<Awaited<ReturnType<typeof fetchFinancialDashboard>>["summary"] | null>(null);
  const [series, setSeries] = useState<Awaited<ReturnType<typeof fetchFinancialDashboard>>["timeseries"]>([]);

  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [breakdownLoading, setBreakdownLoading] = useState(false);
  const [breakdown, setBreakdown] = useState<FinancialDashboardBreakdown | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFinancialDashboard({ month, months: monthsBack });
      setSummary(data.summary);
      setSeries(data.timeseries);
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível carregar o dashboard financeiro.");
    } finally {
      setLoading(false);
    }
  }, [month, monthsBack]);

  useEffect(() => {
    void load();
  }, [load]);

  const chartData = useMemo((): ChartRow[] => {
    return series.map((p) => {
      const ym = p.month.slice(0, 7);
      return {
        month: ym,
        monthLabel: formatMonthLabel(ym),
        faturamento: Number(p.faturamento ?? 0),
        pago: Number(p.pago ?? 0),
        caixa: Number(p.caixa ?? 0),
      };
    });
  }, [series]);

  const isSinglePeriod = chartData.length === 1;

  const yDomain = useMemo(
    () =>
      computeYDomain(chartData, {
        faturamento: showRevenue,
        pago: showCost,
        caixa: showProfit,
      }),
    [chartData, showRevenue, showCost, showProfit],
  );

  const hasNegativeCaixa = useMemo(() => chartData.some((p) => p.caixa < -0.01), [chartData]);

  const singleMonthBars = useMemo((): SingleBarRow[] => {
    if (!isSinglePeriod || !chartData[0]) return [];
    const p = chartData[0];
    const rows: SingleBarRow[] = [];
    if (showRevenue) {
      rows.push({
        name: "Faturamento",
        valor: p.faturamento,
        color: CHART_COLORS.faturamento,
        breakdownType: "faturamento",
      });
    }
    if (showCost) {
      rows.push({
        name: "Custos",
        valor: p.pago,
        color: CHART_COLORS.custos,
        breakdownType: "custos",
      });
    }
    if (showProfit) {
      rows.push({
        name: "Caixa",
        valor: p.caixa,
        color: p.caixa < -0.01 ? CHART_COLORS.caixaNeg : CHART_COLORS.caixaPos,
        breakdownType: "caixa",
      });
    }
    return rows;
  }, [chartData, isSinglePeriod, showRevenue, showCost, showProfit]);

  const singleMonthYm = chartData[0]?.month ?? month;

  async function openBreakdown(type: FinancialDashboardBreakdownType, ym: string) {
    const parsed = parseYm(ym);
    if (!parsed) return;
    setBreakdownOpen(true);
    setBreakdownLoading(true);
    setBreakdown(null);
    setError(null);
    try {
      const b = await fetchFinancialDashboardBreakdown({ type, month: ym });
      setBreakdown(b);
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível carregar o detalhamento.");
      setBreakdownOpen(false);
    } finally {
      setBreakdownLoading(false);
    }
  }

  if (loading && !summary) {
    return (
      <div className="flex items-center gap-3 text-slate-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        Carregando…
      </div>
    );
  }

  const summaryCaixaNeg = (summary?.caixa ?? 0) < -0.01;

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Dashboard Financeiro</h1>
          <p className="mt-1 text-sm text-slate-600">Resumo, evolução e detalhamento por mês.</p>
          <p className="mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <span className="font-medium text-slate-900">Caixa</span> = Faturamento recebido − Pagamentos realizados
            no período. Valores acima da linha de <span className="font-medium">R$ 0</span> indicam superávit; abaixo,
            déficit operacional.
          </p>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Mês</span>
            <input
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Histórico</span>
            <select
              value={monthsBack}
              onChange={(e) => setMonthsBack(Number(e.target.value))}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value={1}>1 mês</option>
              <option value={3}>3 meses</option>
              <option value={6}>6 meses</option>
              <option value={12}>12 meses</option>
              <option value={18}>18 meses</option>
              <option value={24}>24 meses</option>
            </select>
          </label>

          <button
            type="button"
            onClick={() => void load()}
            className="h-[42px] rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            Atualizar
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Kpi label="Faturamento (recebido)" value={summary ? formatBRL(summary.faturamento) : "—"} />
        <Kpi label="Pago no período" value={summary ? formatBRL(summary.pago) : "—"} accent="text-red-800" />
        <Kpi
          label="Caixa (recebido - pago)"
          value={summary ? formatBRL(summary.caixa) : "—"}
          negative={summaryCaixaNeg}
        />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">
              {isSinglePeriod ? "Comparativo do mês" : "Evolução (mensal)"}
            </p>
            <p className="text-xs text-slate-600">
              {isSinglePeriod
                ? "Análise por indicador — clique em uma barra para detalhar."
                : "Série temporal — clique em um ponto para detalhar. Linha grossa = equilíbrio (R$ 0)."}
            </p>
          </div>

          <div className="flex flex-wrap gap-3 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={showRevenue} onChange={(e) => setShowRevenue(e.target.checked)} />
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-4 rounded-sm" style={{ backgroundColor: CHART_COLORS.faturamento }} />
                Faturamento
              </span>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={showCost} onChange={(e) => setShowCost(e.target.checked)} />
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-4 rounded-sm" style={{ backgroundColor: CHART_COLORS.custos }} />
                Custos
              </span>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={showProfit} onChange={(e) => setShowProfit(e.target.checked)} />
              <span className="inline-flex items-center gap-1.5">
                <span
                  className="h-2 w-4 rounded-sm"
                  style={{
                    backgroundColor: hasNegativeCaixa || summaryCaixaNeg ? CHART_COLORS.caixaNeg : CHART_COLORS.caixaPos,
                  }}
                />
                Caixa
              </span>
            </label>
          </div>
        </div>

        <div className="mt-4 h-[380px]">
          {chartData.length === 0 ? (
            <p className="flex h-full items-center justify-center text-sm text-slate-500">Sem dados no período.</p>
          ) : isSinglePeriod ? (
            <div className="flex h-full flex-col">
              <div className="mb-2 text-center text-sm font-medium text-slate-800">
                {chartData[0]?.monthLabel}
              </div>
              <div className="min-h-0 flex-1">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={singleMonthBars}
                    margin={{ top: 28, right: 24, left: 12, bottom: 8 }}
                    barCategoryGap="28%"
                  >
                    <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" strokeOpacity={0.45} vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#475569" }} tickMargin={8} />
                    <YAxis tickFormatter={formatBRLAxis} tick={{ fontSize: 12, fill: "#6B7280" }} width={80} />
                    <Tooltip content={<SingleMonthBarTooltip />} />
                    <Bar
                      dataKey="valor"
                      radius={[6, 6, 0, 0]}
                      maxBarSize={88}
                      cursor="pointer"
                      onClick={(bar) => {
                        const row = bar as unknown as SingleBarRow;
                        if (row?.breakdownType) void openBreakdown(row.breakdownType, singleMonthYm);
                      }}
                    >
                      {singleMonthBars.map((row) => (
                        <Cell key={row.name} fill={row.color} />
                      ))}
                      <LabelList
                        dataKey="valor"
                        position="top"
                        formatter={(v: number) => formatBRL(Number(v ?? 0))}
                        style={{ fontSize: 11, fill: "#334155", fontWeight: 600 }}
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <ul className="mt-3 grid gap-2 border-t border-slate-100 pt-3 sm:grid-cols-3">
                {singleMonthBars.map((row) => (
                  <li
                    key={row.name}
                    className={`rounded-lg border px-3 py-2 text-sm ${
                      row.name === "Caixa" && row.valor < -0.01
                        ? "border-red-200 bg-red-50"
                        : "border-slate-200 bg-slate-50"
                    }`}
                  >
                    <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{row.name}</span>
                    <p
                      className={`mt-1 font-semibold tabular-nums ${
                        row.name === "Caixa" && row.valor < -0.01 ? "text-red-700" : "text-slate-900"
                      }`}
                    >
                      {formatBRL(row.valor)}
                    </p>
                    {row.name === "Caixa" && chartData[0] && chartData[0].faturamento > 0 && (
                      <p className="mt-0.5 text-xs text-slate-600">
                        Margem: {formatPct((row.valor / chartData[0].faturamento) * 100)}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 16, right: 24, left: 8, bottom: 28 }}>
                <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" strokeOpacity={0.35} />
                {yDomain[0] < 0 && (
                  <ReferenceArea y1={yDomain[0]} y2={0} fill="#fecaca" fillOpacity={0.25} ifOverflow="extendDomain" />
                )}
                <ReferenceLine
                  y={0}
                  stroke={CHART_COLORS.zeroLine}
                  strokeWidth={2.5}
                  strokeDasharray="0"
                  label={{
                    value: "R$ 0 — equilíbrio",
                    position: "insideTopLeft",
                    fill: "#0f172a",
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                />
                <XAxis
                  dataKey="monthLabel"
                  padding={{ left: 16, right: 16 }}
                  tickMargin={8}
                  minTickGap={16}
                  interval="preserveStartEnd"
                  tick={{ fontSize: 12, fill: "#6B7280" }}
                />
                <YAxis
                  width={80}
                  domain={yDomain}
                  tickFormatter={formatBRLAxis}
                  tickCount={6}
                  tick={{ fontSize: 12, fill: "#6B7280" }}
                />
                <Tooltip content={<EvolutionTooltip />} />
                <Legend verticalAlign="bottom" height={28} wrapperStyle={{ fontSize: 12 }} />
                {showRevenue && (
                  <Line
                    type="monotone"
                    dataKey="faturamento"
                    stroke={CHART_COLORS.faturamento}
                    name="Faturamento"
                    strokeWidth={3}
                    dot={{ r: 4, strokeWidth: 2, fill: "#fff" }}
                    activeDot={{
                      r: 6,
                      onClick: (_e, payload) =>
                        void openBreakdown("faturamento", String((payload as { payload?: ChartRow })?.payload?.month ?? "")),
                    }}
                  />
                )}
                {showCost && (
                  <Line
                    type="monotone"
                    dataKey="pago"
                    stroke={CHART_COLORS.custos}
                    name="Custos"
                    strokeWidth={3}
                    dot={{ r: 4, strokeWidth: 2, fill: "#fff" }}
                    activeDot={{
                      r: 6,
                      onClick: (_e, payload) =>
                        void openBreakdown("custos", String((payload as { payload?: ChartRow })?.payload?.month ?? "")),
                    }}
                  />
                )}
                {showProfit && (
                  <Line
                    type="monotone"
                    dataKey="caixa"
                    stroke={CHART_COLORS.caixaPos}
                    name="Caixa"
                    strokeWidth={3}
                    dot={(props) => {
                      const { cx, cy, payload } = props;
                      const v = (payload as ChartRow)?.caixa ?? 0;
                      const fill = v < -0.01 ? CHART_COLORS.caixaNeg : CHART_COLORS.caixaPos;
                      return (
                        <circle
                          cx={cx}
                          cy={cy}
                          r={4}
                          fill={fill}
                          stroke="#fff"
                          strokeWidth={2}
                        />
                      );
                    }}
                    activeDot={{
                      r: 6,
                      onClick: (_e, payload) =>
                        void openBreakdown("caixa", String((payload as { payload?: ChartRow })?.payload?.month ?? "")),
                    }}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {breakdownOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-[1100px] rounded-xl bg-white shadow-xl">
            <div className="flex items-start justify-between gap-3 border-b border-slate-200 p-4">
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  Detalhamento: {breakdown?.type ?? "…"} ({breakdown?.month ? String(breakdown.month).slice(0, 7) : month})
                </p>
                {breakdown && (
                  <p className="mt-1 text-xs text-slate-600">
                    Total: {formatBRL(breakdown.total)}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setBreakdownOpen(false)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
              >
                Fechar
              </button>
            </div>

            <div className="max-h-[70vh] overflow-auto p-4">
              {breakdownLoading ? (
                <div className="text-sm text-slate-500">Carregando detalhamento…</div>
              ) : !breakdown ? (
                <div className="text-sm text-slate-500">Sem dados.</div>
              ) : (
                <div className="space-y-6">
                  <div>
                    {breakdown.type !== "caixa" ? (
                      <>
                        <p className="text-sm font-semibold text-slate-900">
                          {breakdown.type === "faturamento" ? "FATURAMENTO - MÊS" : "CUSTOS - MÊS"}
                        </p>
                        <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
                          <table className="min-w-[700px] w-full divide-y divide-slate-200 text-sm">
                            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                              <tr>
                                <th className="px-3 py-2">
                                  {breakdown.type === "custos" ? "Centro de custo" : "Projeto"}
                                </th>
                                <th className="px-3 py-2 text-right">Valor</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {breakdown.groups.map((g) => (
                                <tr key={g.label} className="hover:bg-slate-50/80">
                                  <td className="px-3 py-2 font-medium">{g.label}</td>
                                  <td className="px-3 py-2 text-right tabular-nums">{formatBRL(Number(g.value ?? 0))}</td>
                                </tr>
                              ))}
                              <tr className="bg-slate-50">
                                <td className="px-3 py-2 font-semibold">TOTAL</td>
                                <td className="px-3 py-2 text-right font-semibold tabular-nums">{formatBRL(breakdown.total)}</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </>
                    ) : (
                      <div className="space-y-6">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">RECEBIDO - MÊS (por projeto)</p>
                          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
                            <table className="min-w-[700px] w-full divide-y divide-slate-200 text-sm">
                              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                                <tr>
                                  <th className="px-3 py-2">Projeto</th>
                                  <th className="px-3 py-2 text-right">Valor</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-100">
                                {(breakdown.received_groups ?? []).map((g) => (
                                  <tr key={g.label} className="hover:bg-slate-50/80">
                                    <td className="px-3 py-2 font-medium">{g.label}</td>
                                    <td className="px-3 py-2 text-right tabular-nums">{formatBRL(Number(g.value ?? 0))}</td>
                                  </tr>
                                ))}
                                <tr className="bg-slate-50">
                                  <td className="px-3 py-2 font-semibold">TOTAL RECEBIDO</td>
                                  <td className="px-3 py-2 text-right font-semibold tabular-nums">
                                    {formatBRL(Number(breakdown.received_total ?? 0))}
                                  </td>
                                </tr>
                              </tbody>
                            </table>
                          </div>
                        </div>

                        <div>
                          <p className="text-sm font-semibold text-slate-900">PAGO - MÊS (por centro de custo)</p>
                          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
                            <table className="min-w-[700px] w-full divide-y divide-slate-200 text-sm">
                              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                                <tr>
                                  <th className="px-3 py-2">Centro de custo</th>
                                  <th className="px-3 py-2 text-right">Valor</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-100">
                                {(breakdown.paid_groups ?? []).map((g) => (
                                  <tr key={g.label} className="hover:bg-slate-50/80">
                                    <td className="px-3 py-2 font-medium">{g.label}</td>
                                    <td className="px-3 py-2 text-right tabular-nums">{formatBRL(Number(g.value ?? 0))}</td>
                                  </tr>
                                ))}
                                <tr className="bg-slate-50">
                                  <td className="px-3 py-2 font-semibold">TOTAL PAGO</td>
                                  <td className="px-3 py-2 text-right font-semibold tabular-nums">
                                    {formatBRL(Number(breakdown.paid_total ?? 0))}
                                  </td>
                                </tr>
                              </tbody>
                            </table>
                          </div>
                        </div>

                        <div
                          className={`rounded-lg border px-4 py-3 text-sm ${
                            breakdown.total < -0.01 ? "border-red-200 bg-red-50" : "border-slate-200 bg-slate-50"
                          }`}
                        >
                          <span className="font-semibold">CAIXA (recebido - pago):</span>{" "}
                          <span
                            className={`tabular-nums font-semibold ${
                              breakdown.total < -0.01 ? "text-red-700" : "text-slate-900"
                            }`}
                          >
                            {formatBRL(breakdown.total)}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  accent,
  negative,
}: {
  label: string;
  value: string;
  accent?: string;
  negative?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-4 shadow-sm ${
        negative ? "border-red-300 bg-red-50 ring-1 ring-red-200" : "border-slate-200 bg-white"
      }`}
    >
      <p className={`text-xs font-medium uppercase tracking-wide ${negative ? "text-red-800" : "text-slate-500"}`}>
        {label}
      </p>
      <p
        className={`mt-2 text-lg font-semibold tabular-nums ${
          negative ? "text-red-800" : accent ?? "text-slate-900"
        }`}
      >
        {value}
      </p>
      {negative && (
        <p className="mt-1 text-xs font-medium text-red-700">Prejuízo operacional no período</p>
      )}
    </div>
  );
}
