import type {
  AssetDashboardCostCenterRow,
  AssetDashboardGroupRow,
  AssetDashboardPhysicalRow,
} from "@/services/assetsDashboard";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const CHART_CARD = "rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6 min-h-[300px] flex flex-col";

const CATEGORY_COLORS: Record<string, string> = {
  Tecnologia: "#4F46E5",
  EPI: "#22C55E",
  EPC: "#14B8A6",
  Ferramenta: "#F59E0B",
  Operacional: "#64748B",
  Instrumentação: "#8B5CF6",
  Veículos: "#EC4899",
  Uniformes: "#A855F7",
};

const CC_COLORS = ["#4F46E5", "#22C55E", "#F59E0B", "#14B8A6"];

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatAxis(n: unknown): string {
  const v = Number(n ?? 0);
  if (!Number.isFinite(v)) return "0";
  if (v >= 1_000_000) return `${Math.round(v / 1_000_000)}M`;
  if (v >= 1000) return `${Math.round(v / 1000)}k`;
  return String(Math.round(v));
}

function formatBRLAxis(value: unknown): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "R$ 0";
  if (n >= 1_000_000) return `R$ ${(n / 1_000_000).toFixed(1).replace(".", ",")}M`;
  if (n >= 1000) return `R$ ${Math.round(n / 1000)}k`;
  return `R$ ${Math.round(n).toLocaleString("pt-BR")}`;
}

type Props = {
  byCategory: AssetDashboardGroupRow[];
  byCostCenter: AssetDashboardCostCenterRow[];
  physicalCondition: AssetDashboardPhysicalRow[];
};

export function AssetsDashboardCharts({ byCategory, byCostCenter, physicalCondition }: Props) {
  const categoryData = byCategory.map((r) => ({
    name: r.label,
    count: r.count,
    value: r.value,
  }));

  const physicalData = physicalCondition.map((r) => ({
    name: r.label,
    count: r.count,
    value: r.value,
    condition: r.condition,
  }));

  const ccData = byCostCenter.map((r) => ({
    key: r.key,
    name: r.label,
    asset_count: r.asset_count,
    amount_total: r.amount_total,
    average_value: r.average_value,
  }));

  const ccChartHeight = Math.max(280, ccData.length * 44);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className={CHART_CARD}>
        <p className="text-sm font-semibold text-slate-900">Categoria de ativos</p>
        <p className="mt-0.5 text-xs text-slate-500">Quantidade e valor patrimonial</p>
        <div className="mt-4 flex flex-1 flex-col gap-4 md:flex-row">
          <div className="h-[220px] min-w-0 flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={categoryData}
                  dataKey="count"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={48}
                  outerRadius={72}
                  paddingAngle={2}
                >
                  {categoryData.map((d) => (
                    <Cell key={d.name} fill={CATEGORY_COLORS[d.name] ?? "#94a3b8"} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number, _n, p) => [
                    `${v} itens · ${formatBRL(Number((p?.payload as { value?: number })?.value ?? 0))}`,
                    String(p?.name ?? ""),
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="flex flex-col gap-2 text-sm text-slate-700 md:max-w-[14rem]">
            {categoryData.map((d) => (
              <li key={d.name} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: CATEGORY_COLORS[d.name] ?? "#94a3b8" }}
                  />
                  {d.name}
                </span>
                <span className="tabular-nums text-slate-500">
                  {d.count} · {formatBRL(d.value)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className={CHART_CARD}>
        <p className="text-sm font-semibold text-slate-900">Estado físico</p>
        <p className="mt-0.5 text-xs text-slate-500">Quantidade por condição</p>
        <div className="mt-4 h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={physicalData} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" strokeOpacity={0.5} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} interval={0} />
              <YAxis tickFormatter={formatAxis} tick={{ fontSize: 11, fill: "#64748b" }} />
              <Tooltip
                formatter={(v: number, key) => {
                  if (key === "value") return [formatBRL(Number(v)), "Valor"];
                  return [v, "Quantidade"];
                }}
              />
              <Legend />
              <Bar dataKey="count" name="Quantidade" fill="#4F46E5" radius={[4, 4, 0, 0]} />
              <Bar dataKey="value" name="Valor (R$)" fill="#22C55E" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className={`${CHART_CARD} lg:col-span-2`}>
        <p className="text-sm font-semibold text-slate-900">Valor patrimonial por centro de custo</p>
        <p className="mt-0.5 text-xs text-slate-500">Soma do valor de aquisição por centro ou projeto</p>
        <div className="mt-4" style={{ height: ccChartHeight }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={ccData} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" strokeOpacity={0.5} />
              <XAxis
                type="number"
                tickFormatter={formatBRLAxis}
                tick={{ fontSize: 11, fill: "#64748b" }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={160}
                tick={{ fontSize: 11, fill: "#64748b" }}
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const row = payload[0]?.payload as {
                    asset_count?: number;
                    amount_total?: number;
                    average_value?: number;
                  };
                  const count = row.asset_count ?? 0;
                  const total = Number(row.amount_total ?? 0);
                  const avg = Number(row.average_value ?? 0);
                  return (
                    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-md">
                      <p className="font-medium text-slate-900">{label}</p>
                      <p className="mt-1 text-base font-semibold tabular-nums text-slate-900">
                        {formatBRL(total)}
                      </p>
                      <p className="tabular-nums text-slate-600">
                        {count} ativo{count === 1 ? "" : "s"}
                      </p>
                      <p className="tabular-nums text-slate-500">
                        Média {formatBRL(avg)}
                      </p>
                    </div>
                  );
                }}
              />
              <Legend />
              <Bar dataKey="amount_total" name="Valor patrimonial" fill="#4F46E5" radius={[0, 4, 4, 0]}>
                {ccData.map((d, i) => (
                  <Cell key={d.key} fill={CC_COLORS[i % CC_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="px-2 py-2">Centro</th>
                <th className="px-2 py-2 text-right">Qtd.</th>
                <th className="px-2 py-2 text-right">Valor total</th>
                <th className="px-2 py-2 text-right">Ticket médio</th>
              </tr>
            </thead>
            <tbody>
              {ccData.map((r) => (
                <tr key={r.key} className="border-t border-slate-100">
                  <td className="px-2 py-2 font-medium text-slate-800">{r.name}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{r.asset_count}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatBRL(r.amount_total)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatBRL(r.average_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
