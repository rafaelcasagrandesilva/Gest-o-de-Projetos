import { useMemo, useState } from "react";
import type { MonthlyPoint } from "@/services/dashboard";
import type { ScenarioKind } from "@/context/ScenarioContext";
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

const CHART_COLORS = {
  receita: "#2563eb",
  custo: "#dc2626",
  lucroPos: "#16a34a",
  lucroNeg: "#b91c1c",
  zeroLine: "#0f172a",
  grid: "#E5E7EB",
} as const;

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

function formatBRLAxis(value: unknown): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "R$ 0";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}R$ ${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1000) return `${sign}R$ ${Math.round(abs / 1000)}k`;
  return `${sign}R$ ${Math.round(abs)}`;
}

function formatPct(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return `${n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function formatMonthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  const mon = MONTH_SHORT_PT[m - 1] ?? String(m);
  return `${mon}/${y}`;
}

type ChartRow = {
  month: string;
  monthLabel: string;
  receita: number;
  custo: number;
  lucro: number;
};

type SingleBarRow = {
  name: string;
  valor: number;
  color: string;
};

function monthlyPointsToRows(points: MonthlyPoint[]): ChartRow[] {
  return [...points]
    .map((p) => {
      const ym = p.competencia.slice(0, 7);
      return {
        month: ym,
        monthLabel: formatMonthLabel(ym),
        receita: Number(p.total_revenue ?? p.revenue_total ?? 0),
        custo: Number(p.total_cost ?? p.cost_total ?? 0),
        lucro: Number(p.net_profit ?? p.profit ?? 0),
      };
    })
    .sort((a, b) => a.month.localeCompare(b.month));
}

function computeYDomain(
  rows: ChartRow[],
  keys: { receita: boolean; custo: boolean; lucro: boolean },
): [number, number] {
  const vals: number[] = [0];
  for (const p of rows) {
    if (keys.receita) vals.push(p.receita);
    if (keys.custo) vals.push(p.custo);
    if (keys.lucro) vals.push(p.lucro);
  }
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || Math.max(Math.abs(max), Math.abs(min), 1);
  const pad = Math.max(span * 0.12, 500);
  return [min - pad, max + pad];
}

function EvolutionTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as ChartRow | undefined;
  if (!row) return null;
  const margem = row.receita > 0 ? (row.lucro / row.receita) * 100 : 0;
  const lucroNeg = row.lucro < -0.01;

  return (
    <div className="min-w-[220px] rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs shadow-lg">
      <p className="font-semibold text-slate-900">Mês: {row.monthLabel}</p>
      <dl className="mt-2 space-y-1.5 text-slate-700">
        <div className="flex justify-between gap-4">
          <dt>Receita</dt>
          <dd className="font-medium tabular-nums text-slate-900">{formatBRL(row.receita)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Custo total</dt>
          <dd className="font-medium tabular-nums text-slate-900">{formatBRL(row.custo)}</dd>
        </div>
        <div className="flex justify-between gap-4 border-t border-slate-100 pt-1.5">
          <dt className={lucroNeg ? "font-medium text-red-800" : ""}>Lucro líquido</dt>
          <dd className={`font-semibold tabular-nums ${lucroNeg ? "text-red-700" : "text-emerald-700"}`}>
            {formatBRL(row.lucro)}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Margem líquida</dt>
          <dd className={`font-medium tabular-nums ${lucroNeg ? "text-red-700" : "text-slate-900"}`}>
            {formatPct(margem)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function SingleMonthBarTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as SingleBarRow | undefined;
  if (!row) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold text-slate-900">{row.name}</p>
      <p className="mt-1 font-medium tabular-nums text-slate-800">{formatBRL(row.valor)}</p>
    </div>
  );
}

type Props = {
  monthlySeries: MonthlyPoint[];
  scenario: ScenarioKind;
  multiMonth?: boolean;
};

export function FinancialEvolutionProjectChart({ monthlySeries, scenario, multiMonth = false }: Props) {
  const [showReceita, setShowReceita] = useState(true);
  const [showCusto, setShowCusto] = useState(true);
  const [showLucro, setShowLucro] = useState(true);

  const scenarioLabel = scenario === "PREVISTO" ? "previsto" : "realizado";

  const chartData = useMemo(() => monthlyPointsToRows(monthlySeries), [monthlySeries]);
  const isSinglePeriod = chartData.length === 1;

  const yDomain = useMemo(
    () =>
      computeYDomain(chartData, {
        receita: showReceita,
        custo: showCusto,
        lucro: showLucro,
      }),
    [chartData, showReceita, showCusto, showLucro],
  );

  const singleMonthBars = useMemo((): SingleBarRow[] => {
    if (!isSinglePeriod || !chartData[0]) return [];
    const p = chartData[0];
    const rows: SingleBarRow[] = [];
    if (showReceita) rows.push({ name: "Receita", valor: p.receita, color: CHART_COLORS.receita });
    if (showCusto) rows.push({ name: "Custo total", valor: p.custo, color: CHART_COLORS.custo });
    if (showLucro) {
      rows.push({
        name: "Lucro líquido",
        valor: p.lucro,
        color: p.lucro < -0.01 ? CHART_COLORS.lucroNeg : CHART_COLORS.lucroPos,
      });
    }
    return rows;
  }, [chartData, isSinglePeriod, showReceita, showCusto, showLucro]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900">Evolução financeira</p>
          <p className="text-xs text-slate-600">
            Cenário <strong>{scenarioLabel}</strong>
            {multiMonth ? " — série mensal no período selecionado" : " — comparativo do mês"}
          </p>
        </div>

        <div className="flex flex-wrap gap-3 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={showReceita} onChange={(e) => setShowReceita(e.target.checked)} />
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-sm" style={{ backgroundColor: CHART_COLORS.receita }} />
              Receita
            </span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={showCusto} onChange={(e) => setShowCusto(e.target.checked)} />
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-sm" style={{ backgroundColor: CHART_COLORS.custo }} />
              Custo total
            </span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={showLucro} onChange={(e) => setShowLucro(e.target.checked)} />
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-sm" style={{ backgroundColor: CHART_COLORS.lucroPos }} />
              Lucro líquido
            </span>
          </label>
        </div>
      </div>

      <div className="mt-4 h-[380px]">
        {chartData.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-slate-500">Sem dados no período.</p>
        ) : isSinglePeriod ? (
          <div className="flex h-full flex-col">
            <div className="mb-2 text-center text-sm font-medium text-slate-800">{chartData[0]?.monthLabel}</div>
            <div className="min-h-0 flex-1">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={singleMonthBars} margin={{ top: 28, right: 24, left: 12, bottom: 8 }} barCategoryGap="28%">
                  <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" strokeOpacity={0.45} vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#475569" }} tickMargin={8} />
                  <YAxis tickFormatter={formatBRLAxis} tick={{ fontSize: 12, fill: "#6B7280" }} width={80} />
                  <Tooltip content={<SingleMonthBarTooltip />} />
                  <Bar dataKey="valor" radius={[6, 6, 0, 0]} maxBarSize={88}>
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
                    row.name === "Lucro líquido" && row.valor < -0.01
                      ? "border-red-200 bg-red-50"
                      : "border-slate-200 bg-slate-50"
                  }`}
                >
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{row.name}</span>
                  <p
                    className={`mt-1 font-semibold tabular-nums ${
                      row.name === "Lucro líquido" && row.valor < -0.01 ? "text-red-700" : "text-slate-900"
                    }`}
                  >
                    {formatBRL(row.valor)}
                  </p>
                  {row.name === "Lucro líquido" && chartData[0] && chartData[0].receita > 0 && (
                    <p className="mt-0.5 text-xs text-slate-600">
                      Margem: {formatPct((row.valor / chartData[0].receita) * 100)}
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
              {showReceita && (
                <Line
                  type="monotone"
                  dataKey="receita"
                  stroke={CHART_COLORS.receita}
                  name="Receita"
                  strokeWidth={3}
                  dot={{ r: 4, strokeWidth: 2, fill: "#fff" }}
                />
              )}
              {showCusto && (
                <Line
                  type="monotone"
                  dataKey="custo"
                  stroke={CHART_COLORS.custo}
                  name="Custo total"
                  strokeWidth={3}
                  dot={{ r: 4, strokeWidth: 2, fill: "#fff" }}
                />
              )}
              {showLucro && (
                <Line
                  type="monotone"
                  dataKey="lucro"
                  stroke={CHART_COLORS.lucroPos}
                  name="Lucro líquido"
                  strokeWidth={3}
                  dot={(props) => {
                    const { cx, cy, payload } = props;
                    const v = (payload as ChartRow)?.lucro ?? 0;
                    const fill = v < -0.01 ? CHART_COLORS.lucroNeg : CHART_COLORS.lucroPos;
                    return <circle cx={cx} cy={cy} r={4} fill={fill} stroke="#fff" strokeWidth={2} />;
                  }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
