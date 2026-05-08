import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  fetchFinancialDashboardBreakdown,
  type FinancialDashboardBreakdown,
  type FinancialDashboardBreakdownType,
  fetchFinancialDashboard,
} from "@/services/financialDashboard";
import {
  CartesianGrid,
  Line,
  LineChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatBRLAxis(value: unknown): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "R$ 0";
  if (n >= 1000) return `R$ ${Math.round(n / 1000)}k`;
  return `R$ ${Math.round(n)}`;
}

function monthToYm(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function parseYm(ym: string): { year: number; month: number } | null {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return null;
  return { year: y, month: m };
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

  const chartData = useMemo(() => {
    return series.map((p) => ({
      month: p.month.slice(0, 7),
      faturamento: Number(p.faturamento ?? 0),
      pago: Number(p.pago ?? 0),
      caixa: Number(p.caixa ?? 0),
    }));
  }, [series]);

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

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Dashboard Financeiro</h1>
          <p className="mt-1 text-sm text-slate-600">Resumo, evolução e detalhamento por mês.</p>
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
        <Kpi label="Caixa (recebido - pago)" value={summary ? formatBRL(summary.caixa) : "—"} />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">Evolução (mensal)</p>
            <p className="text-xs text-slate-600">Clique em um ponto do gráfico para detalhar.</p>
          </div>

          <div className="flex flex-wrap gap-3 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={showRevenue} onChange={(e) => setShowRevenue(e.target.checked)} />
              <span>Faturamento</span>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={showCost} onChange={(e) => setShowCost(e.target.checked)} />
              <span>Custos</span>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={showProfit} onChange={(e) => setShowProfit(e.target.checked)} />
              <span>Caixa</span>
            </label>
          </div>
        </div>

        <div className="mt-4 h-[360px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 24 }}>
              <CartesianGrid stroke="#E5E7EB" strokeDasharray="3 3" strokeOpacity={0.4} />
              <XAxis
                dataKey="month"
                padding={{ left: 10, right: 10 }}
                tickMargin={8}
                minTickGap={16}
                interval="preserveStartEnd"
                tick={{ fontSize: 12, fill: "#6B7280" }}
              />
              <YAxis
                width={72}
                domain={[0, "auto"]}
                tickFormatter={formatBRLAxis}
                tickCount={5}
                tick={{ fontSize: 12, fill: "#6B7280" }}
              />
              <Tooltip
                formatter={(v: any) => formatBRL(Number(v ?? 0))}
                labelFormatter={(l) => `Mês: ${String(l)}`}
              />
              <Legend verticalAlign="bottom" height={24} />
              {showRevenue && (
                <Line
                  type="monotone"
                  dataKey="faturamento"
                  stroke="#2563eb"
                  name="Faturamento"
                  strokeWidth={3}
                  dot={{ r: 2 }}
                  activeDot={{
                    r: 5,
                    onClick: (_e: any, payload: any) =>
                      void openBreakdown("faturamento", String(payload?.payload?.month ?? "")),
                  }}
                />
              )}
              {showCost && (
                <Line
                  type="monotone"
                  dataKey="pago"
                  stroke="#dc2626"
                  name="Custos"
                  strokeWidth={3}
                  dot={{ r: 2 }}
                  activeDot={{
                    r: 5,
                    onClick: (_e: any, payload: any) =>
                      void openBreakdown("custos", String(payload?.payload?.month ?? "")),
                  }}
                />
              )}
              {showProfit && (
                <Line
                  type="monotone"
                  dataKey="caixa"
                  stroke="#16a34a"
                  name="Caixa"
                  strokeWidth={3}
                  dot={{ r: 2 }}
                  activeDot={{
                    r: 5,
                    onClick: (_e: any, payload: any) =>
                      void openBreakdown("caixa", String(payload?.payload?.month ?? "")),
                  }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
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

                        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
                          <span className="font-semibold">CAIXA (recebido - pago):</span>{" "}
                          <span className="tabular-nums">{formatBRL(breakdown.total)}</span>
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

function Kpi({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-lg font-semibold tabular-nums text-slate-900 ${accent ?? ""}`}>{value}</p>
    </div>
  );
}

