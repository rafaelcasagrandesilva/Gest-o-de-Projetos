import type { ScenarioKind } from "@/context/ScenarioContext";
import type { ProjectBreakdownRow } from "@/services/dashboard";
import {
  Bar,
  BarChart,
  Cell,
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

/** Paleta cíclica para projetos (quantidade dinâmica). */
const PROJECT_PALETTE = [
  "#4F46E5",
  "#22C55E",
  "#F59E0B",
  "#EF4444",
  "#14B8A6",
  "#8B5CF6",
  "#EC4899",
  "#0EA5E9",
  "#84CC16",
  "#F97316",
  "#06B6D4",
  "#A855F7",
] as const;

function colorForIndex(i: number): string {
  return PROJECT_PALETTE[i % PROJECT_PALETTE.length];
}

const chartCardClass =
  "rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6 min-h-[300px] flex flex-col";

const chartTooltipStyle = {
  borderRadius: "0.5rem",
  border: "1px solid #e2e8f0",
  fontSize: "12px",
  boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.08)",
} as const;

type Props = {
  /** Quebra por projeto (cenário/período/competência já aplicados). */
  breakdown: ProjectBreakdownRow[];
  /** Carregando a quebra por projeto. */
  loading?: boolean;
  /** Mais de um mês: textos dos gráficos falam em “período”. */
  multiMonth?: boolean;
  /** Cenário ativo dos gráficos. */
  selectedScenario?: ScenarioKind;
};

/** Linha com participação relativa já calculada (fração 0–1). */
type ShareRow = {
  projectId: string;
  name: string;
  value: number;
  share: number;
  color: string;
};

/** Ordena desc por `pick`, filtra valores positivos e calcula participação. */
function buildShareRows(
  rows: ProjectBreakdownRow[],
  pick: (r: ProjectBreakdownRow) => number,
): ShareRow[] {
  const positives = rows
    .map((r) => ({ ...r, _v: pick(r) }))
    .filter((r) => r._v > 0)
    .sort((a, b) => b._v - a._v);
  const total = positives.reduce((acc, r) => acc + r._v, 0);
  return positives.map((r, i) => ({
    projectId: r.projectId,
    name: r.name,
    value: r._v,
    share: total > 0 ? r._v / total : 0,
    color: colorForIndex(i),
  }));
}

function RevenueShareLegend({ rows }: { rows: ShareRow[] }) {
  return (
    <ul
      className="flex w-full flex-col gap-2.5 text-sm text-slate-800 md:max-w-[min(100%,20rem)]"
      role="list"
      aria-label="Faturamento por projeto — valor e participação"
    >
      {rows.map((row) => (
        <li key={row.projectId} className="flex items-baseline gap-3" role="listitem">
          <span
            className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ring-1 ring-slate-200/80"
            style={{ backgroundColor: row.color }}
            aria-hidden
          />
          <span className="min-w-0">
            <span className="block truncate font-medium text-slate-900">{row.name}</span>
            <span className="tabular-nums text-slate-600">
              {formatCurrency(row.value)} · {(row.share * 100).toFixed(1)}%
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function RevenueShareTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: ShareRow }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-md" style={chartTooltipStyle}>
      <p className="text-xs font-medium text-slate-800">{row.name}</p>
      <p className="mt-0.5 text-xs tabular-nums text-slate-600">
        {formatCurrency(row.value)} · {(row.share * 100).toFixed(1)}%
      </p>
    </div>
  );
}

function OperationalCostTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: ShareRow }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-md" style={chartTooltipStyle}>
      <p className="text-xs font-medium text-slate-800">{row.name}</p>
      <p className="mt-0.5 text-xs tabular-nums text-slate-600">
        {formatCurrency(row.value)} · {(row.share * 100).toFixed(1)}%
      </p>
    </div>
  );
}

function compactCurrency(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1000) return `${(v / 1000).toFixed(0)}k`;
  return String(v);
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="flex min-h-[240px] flex-1 items-center justify-center">
      <p className="text-center text-sm text-slate-500">{message}</p>
    </div>
  );
}

export function FinancialDashboardCharts({
  breakdown,
  loading = false,
  multiMonth = false,
  selectedScenario = "REALIZADO",
}: Props) {
  const scLabel = selectedScenario === "PREVISTO" ? "previsto" : "realizado";
  const periodLabel = multiMonth ? "no período" : "do mês";

  const revenueRows = buildShareRows(breakdown, (r) => r.revenue);
  const costRows = buildShareRows(breakdown, (r) => r.operationalCost);

  // Altura proporcional ao nº de barras (responsivo a zoom e quantidade de projetos).
  const costChartHeight = Math.max(220, costRows.length * 40 + 48);

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {/* Faturamento por projeto — donut */}
      <div className={chartCardClass}>
        <h3 className="text-sm font-medium text-slate-700">Faturamento por projeto</h3>
        <p className="mt-0.5 text-xs text-slate-500">
          Cenário <strong>{scLabel}</strong> — participação de cada projeto na receita {periodLabel}
        </p>
        {loading ? (
          <EmptyChart message="Carregando faturamento por projeto…" />
        ) : revenueRows.length === 0 ? (
          <EmptyChart message={`Sem faturamento ${multiMonth ? "neste período" : "nesta competência"}.`} />
        ) : (
          <div className="mt-2 flex min-h-[280px] w-full flex-1 flex-col gap-5 md:flex-row md:items-center md:justify-between md:gap-5">
            <div className="flex min-h-[240px] w-full flex-1 items-center justify-center md:min-h-[280px] md:max-w-[min(100%,280px)] md:flex-[0_1_280px]">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                  <Pie
                    data={revenueRows}
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
                    {revenueRows.map((entry) => (
                      <Cell key={entry.projectId} fill={entry.color} stroke="#fff" strokeWidth={1} />
                    ))}
                  </Pie>
                  <Tooltip content={<RevenueShareTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <RevenueShareLegend rows={revenueRows} />
          </div>
        )}
      </div>

      {/* Custos operacionais por projeto — barras horizontais */}
      <div className={chartCardClass}>
        <h3 className="text-sm font-medium text-slate-700">Custos operacionais por projeto</h3>
        <p className="mt-0.5 text-xs text-slate-500">
          Cenário <strong>{scLabel}</strong> — custo operacional total de cada projeto {periodLabel}
        </p>
        {loading ? (
          <EmptyChart message="Carregando custos por projeto…" />
        ) : costRows.length === 0 ? (
          <EmptyChart message={`Sem custos operacionais ${multiMonth ? "neste período" : "nesta competência"}.`} />
        ) : (
          <div className="mt-2 w-full flex-1">
            <ResponsiveContainer width="100%" height={costChartHeight}>
              <BarChart
                data={costRows}
                layout="vertical"
                margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
              >
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fill: "#475569" }}
                  tickFormatter={compactCurrency}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11, fill: "#475569" }}
                  width={120}
                  interval={0}
                />
                <Tooltip content={<OperationalCostTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={28}>
                  {costRows.map((row) => (
                    <Cell key={row.projectId} fill={row.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <ul className="mt-3 flex flex-col gap-1.5 border-t border-slate-100 pt-3 text-xs text-slate-700" role="list">
              {costRows.map((row) => (
                <li key={row.projectId} className="flex items-baseline justify-between gap-3" role="listitem">
                  <span className="inline-flex min-w-0 items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-sm ring-1 ring-slate-200/80"
                      style={{ backgroundColor: row.color }}
                      aria-hidden
                    />
                    <span className="truncate">{row.name}</span>
                  </span>
                  <span className="shrink-0 tabular-nums text-slate-900">
                    {formatCurrency(row.value)} · {(row.share * 100).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
