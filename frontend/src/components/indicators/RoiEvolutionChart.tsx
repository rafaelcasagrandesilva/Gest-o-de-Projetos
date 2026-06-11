import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RoiEvolutionPoint } from "@/services/indicators";
import { formatCurrency } from "@/utils/currency";
import { monthLabel } from "@/utils/roiFormat";
import {
  CHART_COLORS,
  NEGATIVE_AREA_FILL,
  NEGATIVE_AREA_OPACITY,
  formatBRLAxis,
} from "@/utils/chartTheme";

type Row = {
  label: string;
  receita: number;
  custo: number;
  lucro: number;
  roi: number | null;
};

const cardClass = "rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6";

function formatPctAxis(value: unknown): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "0%";
  return `${Math.round(n)}%`;
}

function formatPctTooltip(n: number): string {
  return Number.isFinite(n) ? `${n.toFixed(1).replace(".", ",")}%` : "—";
}

/** Domínio do eixo financeiro (R$) das séries ligadas; inclui 0. */
function computeMoneyDomain(
  rows: Row[],
  keys: { receita: boolean; custo: boolean; lucro: boolean },
): [number, number] {
  const vals: number[] = [0];
  for (const r of rows) {
    if (keys.receita) vals.push(r.receita);
    if (keys.custo) vals.push(r.custo);
    if (keys.lucro) vals.push(r.lucro);
  }
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || Math.max(Math.abs(max), Math.abs(min), 1);
  const pad = Math.max(span * 0.12, 500);
  return [min - pad, max + pad];
}

function SeriesToggle({
  checked,
  onChange,
  color,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  color: string;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2 w-4 rounded-sm" style={{ backgroundColor: color }} />
        {label}
      </span>
    </label>
  );
}

/** 1) Evolução do ROI (%) — gráfico independente, eixo único em %. */
function RoiPercentChart({ data }: { data: Row[] }) {
  const pctDomain = useMemo<[(min: number) => number, (max: number) => number]>(
    () => [(min: number) => Math.min(0, min), (max: number) => Math.max(0, max)],
    [],
  );

  return (
    <div className={cardClass}>
      <h3 className="text-sm font-semibold text-slate-900">Evolução do ROI (%)</h3>
      <p className="text-xs text-slate-600">ROI Operacional por período (Lucro ÷ Custo).</p>
      <div className="mt-4 h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 16, right: 24, left: 8, bottom: 24 }}>
            <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" strokeOpacity={0.35} />
            <ReferenceLine y={0} stroke={CHART_COLORS.zeroLine} strokeWidth={1.5} strokeOpacity={0.6} />
            <XAxis
              dataKey="label"
              padding={{ left: 16, right: 16 }}
              tickMargin={8}
              minTickGap={16}
              interval="preserveStartEnd"
              tick={{ fontSize: 12, fill: "#6B7280" }}
            />
            <YAxis
              width={52}
              domain={pctDomain}
              tickFormatter={formatPctAxis}
              tick={{ fontSize: 12, fill: "#6B7280" }}
            />
            <Tooltip formatter={(value: number | string) => [formatPctTooltip(Number(value)), "ROI"]} />
            <Line
              type="monotone"
              dataKey="roi"
              name="ROI (%)"
              stroke={CHART_COLORS.roi}
              strokeWidth={2.5}
              strokeDasharray="5 4"
              dot={{ r: 3, strokeWidth: 2, fill: "#fff" }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** 2) Evolução Financeira — Receita, Custos e Lucro; eixo R$, linha de equilíbrio e região negativa. */
function FinancialEvolutionChart({ data }: { data: Row[] }) {
  const [showReceita, setShowReceita] = useState(true);
  const [showCusto, setShowCusto] = useState(true);
  const [showLucro, setShowLucro] = useState(true);

  const anyMoney = showReceita || showCusto || showLucro;
  const moneyDomain = useMemo(
    () => computeMoneyDomain(data, { receita: showReceita, custo: showCusto, lucro: showLucro }),
    [data, showReceita, showCusto, showLucro],
  );

  return (
    <div className={cardClass}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Evolução Financeira</h3>
          <p className="text-xs text-slate-600">Linha grossa = equilíbrio (R$ 0).</p>
        </div>
        <div className="flex flex-wrap gap-3 text-sm text-slate-700">
          <SeriesToggle checked={showReceita} onChange={setShowReceita} color={CHART_COLORS.faturamento} label="Receita" />
          <SeriesToggle checked={showCusto} onChange={setShowCusto} color={CHART_COLORS.custos} label="Custos" />
          <SeriesToggle checked={showLucro} onChange={setShowLucro} color={CHART_COLORS.caixaPos} label="Lucro" />
        </div>
      </div>

      <div className="mt-4 h-[320px]">
        {!anyMoney ? (
          <p className="flex h-full items-center justify-center text-sm text-slate-500">
            Selecione ao menos uma série para exibir.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 16, right: 24, left: 8, bottom: 24 }}>
              <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" strokeOpacity={0.35} />
              {moneyDomain[0] < 0 && (
                <ReferenceArea
                  y1={moneyDomain[0]}
                  y2={0}
                  fill={NEGATIVE_AREA_FILL}
                  fillOpacity={NEGATIVE_AREA_OPACITY}
                  ifOverflow="extendDomain"
                />
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
                dataKey="label"
                padding={{ left: 16, right: 16 }}
                tickMargin={8}
                minTickGap={16}
                interval="preserveStartEnd"
                tick={{ fontSize: 12, fill: "#6B7280" }}
              />
              <YAxis
                width={80}
                domain={moneyDomain}
                tickFormatter={formatBRLAxis}
                tickCount={6}
                tick={{ fontSize: 12, fill: "#6B7280" }}
              />
              <Tooltip formatter={(value: number | string, name: string) => [formatCurrency(Number(value)), name]} />
              <Legend verticalAlign="bottom" height={28} wrapperStyle={{ fontSize: 12 }} />
              {showReceita && (
                <Line
                  type="monotone"
                  dataKey="receita"
                  name="Receita"
                  stroke={CHART_COLORS.faturamento}
                  strokeWidth={3}
                  dot={{ r: 4, strokeWidth: 2, fill: "#fff" }}
                  activeDot={{ r: 6 }}
                />
              )}
              {showCusto && (
                <Line
                  type="monotone"
                  dataKey="custo"
                  name="Custos"
                  stroke={CHART_COLORS.custos}
                  strokeWidth={3}
                  dot={{ r: 4, strokeWidth: 2, fill: "#fff" }}
                  activeDot={{ r: 6 }}
                />
              )}
              {showLucro && (
                <Line
                  type="monotone"
                  dataKey="lucro"
                  name="Lucro"
                  stroke={CHART_COLORS.caixaPos}
                  strokeWidth={3}
                  dot={(props) => {
                    const { cx, cy, payload } = props;
                    const v = (payload as Row)?.lucro ?? 0;
                    const fill = v < -0.01 ? CHART_COLORS.caixaNeg : CHART_COLORS.caixaPos;
                    return <circle cx={cx} cy={cy} r={4} fill={fill} stroke="#fff" strokeWidth={2} />;
                  }}
                  activeDot={{ r: 6 }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export function RoiEvolutionChart({ points }: { points: RoiEvolutionPoint[] }) {
  const data: Row[] = useMemo(
    () =>
      points.map((p) => ({
        label: monthLabel(p.competencia),
        receita: p.revenue,
        custo: p.cost,
        lucro: p.operational_profit,
        roi: p.roi_pct,
      })),
    [points],
  );

  return (
    <div className="space-y-5">
      <RoiPercentChart data={data} />
      <FinancialEvolutionChart data={data} />
    </div>
  );
}
