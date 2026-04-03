import type { DirectorSummary, MonthlyPoint } from "@/services/dashboard";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function formatCurrency(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Cores por categoria (donut + legenda). */
const PIE_SLICE_COLORS: Record<string, string> = {
  "Mão de obra": "#4F46E5",
  Veículos: "#22C55E",
  Sistemas: "#F59E0B",
  "Custos fixos": "#64748B",
  Impostos: "#EF4444",
  Rateio: "#14B8A6",
  Antecipação: "#8B5CF6",
};

const BAR_COLORS: Record<string, string> = {
  Receita: "#4F46E5",
  "Custo total": "#EF4444",
  "Lucro operacional": "#22C55E",
  "Lucro líquido": "#14B8A6",
};

const LINE_COLORS = {
  receita: "#4F46E5",
  lucro: "#22C55E",
} as const;

const chartCardClass =
  "rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6 min-h-[300px] flex flex-col";

type Props = {
  summary: DirectorSummary;
  monthlySeries: MonthlyPoint[];
};

/** Fatia do donut: valores absolutos + % sobre a receita (não sobre a soma dos custos). */
type PieSlice = {
  name: string;
  value: number;
  percentOfRevenue: number;
};

function buildCostCompositionRows(s: DirectorSummary, receita: number): PieSlice[] {
  const base = [
    { name: "Mão de obra", value: Math.max(0, s.labor_cost ?? 0) },
    { name: "Veículos", value: Math.max(0, s.vehicle_cost ?? 0) },
    { name: "Sistemas", value: Math.max(0, s.system_cost ?? 0) },
    { name: "Custos fixos", value: Math.max(0, s.fixed_operational_cost ?? 0) },
    { name: "Impostos", value: Math.max(0, s.tax_amount ?? 0) },
    { name: "Rateio", value: Math.max(0, s.overhead_amount ?? 0) },
    { name: "Antecipação", value: Math.max(0, s.anticipation_amount ?? 0) },
  ];
  return base.map((d) => ({
    name: d.name,
    value: d.value,
    percentOfRevenue: receita > 0 ? d.value / receita : 0,
  }));
}

function CostCompositionLegend({ rows }: { rows: PieSlice[] }) {
  return (
    <ul
      className="flex w-full flex-col gap-2.5 text-sm text-slate-800 md:max-w-[min(100%,18rem)]"
      role="list"
      aria-label="Composição de custos — percentuais sobre a receita"
    >
      {rows.map((row) => (
        <li key={row.name} className="flex items-baseline gap-3" role="listitem">
          <span
            className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ring-1 ring-slate-200/80"
            style={{ backgroundColor: PIE_SLICE_COLORS[row.name] ?? "#94a3b8" }}
            aria-hidden
          />
          <span>
            {row.name} —{" "}
            <span className="font-medium tabular-nums text-slate-900">
              {(row.percentOfRevenue * 100).toFixed(1)}%
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function CostCompositionTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: PieSlice }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-md"
      style={chartTooltipStyle}
    >
      <p className="text-xs font-medium text-slate-800">{row.name}</p>
      <p className="mt-0.5 text-xs tabular-nums text-slate-600">{(row.percentOfRevenue * 100).toFixed(1)}%</p>
    </div>
  );
}

const chartTooltipStyle = {
  borderRadius: "0.5rem",
  border: "1px solid #e2e8f0",
  fontSize: "12px",
  boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.08)",
} as const;

type BarRow = { name: string; valor: number };

function BarChartLegend({ rows }: { rows: BarRow[] }) {
  return (
    <div
      className="mt-3 flex flex-wrap justify-center gap-x-6 gap-y-2 border-t border-slate-100 pt-3 text-xs text-slate-700"
      role="list"
    >
      {rows.map((row) => (
        <span key={row.name} className="inline-flex items-center gap-2" role="listitem">
          <span
            className="h-3 w-3 shrink-0 rounded-sm ring-1 ring-slate-200/80"
            style={{ backgroundColor: BAR_COLORS[row.name] ?? "#64748b" }}
            aria-hidden
          />
          {row.name}
        </span>
      ))}
    </div>
  );
}

export function FinancialDashboardCharts({ summary: s, monthlySeries }: Props) {
  const receita = s.total_revenue ?? s.revenue_total;
  const costCompositionAll = buildCostCompositionRows(s, receita);
  const costCompositionLegend = [...costCompositionAll].sort(
    (a, b) => b.percentOfRevenue - a.percentOfRevenue,
  );
  const pieData = costCompositionAll.filter((d) => d.value > 0);

  const barData: BarRow[] = [
    { name: "Receita", valor: s.total_revenue ?? s.revenue_total },
    { name: "Custo total", valor: s.total_cost ?? s.cost_total },
    { name: "Lucro operacional", valor: s.operational_profit ?? s.profit },
    { name: "Lucro líquido", valor: s.net_profit ?? s.profit },
  ];

  const lineData = monthlySeries.map((m) => ({
    mes: m.competencia.slice(0, 7),
    receita: m.revenue_total,
    lucro: m.net_profit ?? m.profit,
  }));

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className={chartCardClass}>
          <h3 className="text-sm font-medium text-slate-700">Composição de custos</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Proporção dos custos sobre a receita do mês — legenda com percentuais; passe o mouse sobre o gráfico para detalhes
          </p>
          <div className="mt-2 flex min-h-[280px] w-full flex-1 flex-col gap-5 md:flex-row md:items-center md:justify-between md:gap-6">
            <div className="flex min-h-[240px] w-full flex-1 items-center justify-center md:min-h-[280px] md:max-w-[min(100%,280px)] md:flex-[0_1_280px]">
              {pieData.length === 0 ? (
                <p className="text-center text-sm text-slate-500">Sem custos nesta competência.</p>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={52}
                      outerRadius={88}
                      paddingAngle={1}
                      label={false}
                      labelLine={false}
                    >
                      {pieData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={PIE_SLICE_COLORS[entry.name] ?? "#94a3b8"}
                          stroke="#fff"
                          strokeWidth={1}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<CostCompositionTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
            <CostCompositionLegend rows={costCompositionLegend} />
          </div>
        </div>

        <div className={chartCardClass}>
          <h3 className="text-sm font-medium text-slate-700">Resumo financeiro</h3>
          <p className="mt-0.5 text-xs text-slate-500">Receita, custo total e lucros</p>
          <div className="mt-2 w-full flex-1">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={barData} margin={{ top: 12, right: 12, left: 8, bottom: 56 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "#475569" }}
                  interval={0}
                  angle={-22}
                  textAnchor="end"
                  height={68}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#475569" }}
                  tickFormatter={(v) =>
                    Math.abs(v) >= 1_000_000
                      ? `${(v / 1_000_000).toFixed(1)}M`
                      : Math.abs(v) >= 1000
                        ? `${(v / 1000).toFixed(0)}k`
                        : String(v)
                  }
                  width={48}
                />
                <Tooltip
                  formatter={(value: number) => formatCurrency(value)}
                  contentStyle={chartTooltipStyle}
                />
                <Bar dataKey="valor" radius={[4, 4, 0, 0]} maxBarSize={56}>
                  {barData.map((row) => (
                    <Cell key={row.name} fill={BAR_COLORS[row.name] ?? "#64748b"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <BarChartLegend rows={barData} />
          </div>
        </div>
      </div>

      <div className={chartCardClass + " min-h-[320px]"}>
        <h3 className="text-sm font-medium text-slate-700">Evolução mensal</h3>
        <p className="mt-0.5 text-xs text-slate-500">Receita e lucro líquido por mês</p>
        <div className="mt-2 min-h-[280px] w-full flex-1">
          {lineData.length === 0 ? (
            <p className="flex h-full items-center justify-center text-sm text-slate-500">Sem série mensal.</p>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={lineData} margin={{ top: 12, right: 20, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="mes" tick={{ fontSize: 11, fill: "#475569" }} />
                <YAxis
                  tick={{ fontSize: 11, fill: "#475569" }}
                  tickFormatter={(v) =>
                    Math.abs(v) >= 1_000_000
                      ? `${(v / 1_000_000).toFixed(1)}M`
                      : Math.abs(v) >= 1000
                        ? `${(v / 1000).toFixed(0)}k`
                        : String(v)
                  }
                  width={48}
                />
                <Tooltip
                  formatter={(value: number) => formatCurrency(value)}
                  contentStyle={chartTooltipStyle}
                />
                <Legend
                  verticalAlign="top"
                  align="center"
                  wrapperStyle={{ fontSize: "12px", paddingBottom: "8px" }}
                  iconType="line"
                />
                <Line
                  type="monotone"
                  dataKey="receita"
                  name="Receita"
                  stroke={LINE_COLORS.receita}
                  strokeWidth={2.5}
                  dot={{ r: 3, strokeWidth: 1, fill: "#fff" }}
                  activeDot={{ r: 5 }}
                />
                <Line
                  type="monotone"
                  dataKey="lucro"
                  name="Lucro líquido"
                  stroke={LINE_COLORS.lucro}
                  strokeWidth={2.5}
                  dot={{ r: 3, strokeWidth: 1, fill: "#fff" }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
