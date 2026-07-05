import { useCallback, useMemo } from "react";
import type { EChartsOption, EChartsType, LineSeriesOption } from "echarts";
import type { FinancialEvolutionPoint } from "@/services/indicators";
import type { SeriesVisibility } from "@/hooks/useFinancialChartViz";
import { EChart } from "@/components/dashboard/executive/EChart";
import { formatCurrency, formatCurrencyShort } from "@/utils/currency";
import { CHART_COLORS } from "@/utils/chartTheme";
import { monthLabel } from "@/utils/roiFormat";
import { createSmartLabelLayout } from "@/utils/smartLabelLayout";

/**
 * Gráfico principal do Dashboard Executivo (Apache ECharts).
 *
 * Séries: Faturamento, Custos de M.O., Custos de Veículos (laranja; só aparece se
 * houver custo no período) e Lucro Operacional. Comportamento profissional:
 * visibilidade das séries controlada pelo React (preserva o estado do usuário),
 * legenda clicável, layout inteligente de rótulos (helper) recalculado a cada
 * interação, e modo `expanded` com zoom (dataZoom). Não reseta o gráfico ao mudar
 * opções: usa merge (notMerge=false) para preservar o zoom, e legenda/labels vêm
 * do estado React.
 */

const TOL = 0.005;
/** Custos de Veículos — laranja, mantendo a identidade visual do mockup original. */
const VEHICLE_COLOR = "#f59e0b";

/** Metadados estáveis das séries do gráfico principal. */
export const MAIN_SERIES = [
  { id: "faturamento", name: "Faturamento", field: "faturamento", color: CHART_COLORS.faturamento },
  { id: "maoObra", name: "Custos de M.O.", field: "custo_mo", color: CHART_COLORS.custos },
  { id: "veiculos", name: "Custos de Veículos", field: "custo_veiculos", color: VEHICLE_COLOR },
  { id: "lucroOperacional", name: "Lucro Operacional", field: "lucro_operacional", color: CHART_COLORS.caixaPos },
] as const satisfies ReadonlyArray<{
  id: string;
  name: string;
  field: keyof FinancialEvolutionPoint;
  color: string;
}>;

export const MAIN_SERIES_IDS = MAIN_SERIES.map((s) => s.id);
const NAME_TO_ID = Object.fromEntries(MAIN_SERIES.map((s) => [s.name, s.id]));

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  return `rgba(${parseInt(h.slice(0, 2), 16)}, ${parseInt(h.slice(2, 4), 16)}, ${parseInt(h.slice(4, 6), 16)}, ${alpha})`;
}

/** Variação percentual mês a mês; null quando não há base (1º ponto ou base ~0). */
function momPct(arr: number[], i: number): number | null {
  if (i <= 0) return null;
  const prev = arr[i - 1];
  if (Math.abs(prev) < TOL) return null;
  return ((arr[i] - prev) / Math.abs(prev)) * 100;
}

export function FinancialEvolutionMainChart({
  points,
  showAllValues,
  selectedSeries,
  onSelectedSeriesChange,
  expanded = false,
  onReady,
  height = 380,
}: {
  points: FinancialEvolutionPoint[];
  showAllValues: boolean;
  /** visibilidade por id de série (controlada pelo React) */
  selectedSeries: SeriesVisibility;
  /** chamado quando o usuário liga/desliga séries na legenda */
  onSelectedSeriesChange: (next: SeriesVisibility) => void;
  expanded?: boolean;
  onReady?: (instance: EChartsType) => void;
  height?: number | string;
}) {
  const option = useMemo<EChartsOption>(() => {
    const months = points.map((p) => monthLabel(p.competencia));
    const last = points.length - 1;
    const numsById: Record<string, number[]> = Object.fromEntries(
      MAIN_SERIES.map((s) => [s.id, points.map((p) => Number(p[s.field]))]),
    );
    const hasVehicle = numsById.veiculos.some((v) => Math.abs(v) > TOL);
    const isVisibleInCatalog = (id: string) => id !== "veiculos" || hasVehicle;

    const smartLayout = createSmartLabelLayout({ expanded });

    const series = MAIN_SERIES.map((s) => {
      const nums = numsById[s.id];
      const present = isVisibleInCatalog(s.id);
      return {
        name: s.name,
        type: "line" as const,
        smooth: true,
        smoothMonotone: "x" as const,
        symbol: "circle",
        symbolSize: 7,
        // Série ausente do catálogo (ex.: veículos sem custo) → sem dados (não renderiza).
        data: present
          ? nums.map((v, i) =>
              i === last
                ? {
                    value: v,
                    symbolSize: 12,
                    itemStyle: {
                      color: s.color,
                      borderColor: "#fff",
                      borderWidth: 2,
                      shadowBlur: 12,
                      shadowColor: hexToRgba(s.color, 0.55),
                    },
                  }
                : v,
            )
          : [],
        itemStyle: { color: s.color },
        lineStyle: { width: 3, color: s.color },
        emphasis: { focus: "series" as const },
        labelLine: expanded ? { show: true, lineStyle: { color: "#cbd5e1", width: 1 } } : { show: false },
        labelLayout: smartLayout as unknown as LineSeriesOption["labelLayout"],
        label: {
          show: true,
          position: "top" as const,
          distance: 10,
          formatter: (p: { dataIndex: number; value?: unknown }) => {
            const i = p.dataIndex;
            const valTag = i === last ? "valLast" : "val";
            const valStr = `{${valTag}|${formatCurrencyShort(Number(p.value))}}`;
            const pct = momPct(nums, i);
            const pill = pct === null ? "" : pct >= 0 ? `{up|▲ +${Math.round(pct)}%}` : `{down|▼ ${Math.round(pct)}%}`;
            const showValue = showAllValues || i === last;
            // Badge + valor tratados como um ÚNICO bloco (label único, multi-linha).
            if (showValue && pill) return `${pill}\n${valStr}`;
            if (showValue) return valStr;
            return pill;
          },
          rich: {
            up: { color: "#15803d", backgroundColor: "#dcfce7", borderRadius: 4, padding: [2, 5], fontSize: 10, fontWeight: "bold" as const, lineHeight: 15 },
            down: { color: "#b91c1c", backgroundColor: "#fee2e2", borderRadius: 4, padding: [2, 5], fontSize: 10, fontWeight: "bold" as const, lineHeight: 15 },
            val: { color: "#64748b", fontSize: 10, lineHeight: 15 },
            valLast: { color: s.color, fontSize: 12, fontWeight: "bold" as const, lineHeight: 17 },
          },
        },
      };
    });

    const legendNames = MAIN_SERIES.filter((s) => isVisibleInCatalog(s.id)).map((s) => s.name);
    const legendSelected: Record<string, boolean> = Object.fromEntries(
      MAIN_SERIES.filter((s) => isVisibleInCatalog(s.id)).map((s) => [s.name, selectedSeries[s.id] !== false]),
    );

    return {
      grid: { top: 64, right: 40, bottom: expanded ? 78 : 40, left: 68 },
      legend: {
        top: 8,
        icon: "roundRect",
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: "#475569", fontSize: 12 },
        data: legendNames,
        selected: legendSelected,
      },
      tooltip: {
        trigger: "axis",
        borderColor: "#e2e8f0",
        textStyle: { color: "#0f172a" },
        formatter: (params: unknown) => {
          const arr = (params as Array<{ axisValue: string; seriesName: string; dataIndex: number; color: string; value: number }>)
            .filter((s) => s.value != null && Number.isFinite(s.value));
          if (!arr.length) return "";
          const idx = arr[0].dataIndex;
          const rows = arr
            .map((s) => {
              const nums = numsById[NAME_TO_ID[s.seriesName]] ?? [];
              const pct = momPct(nums, idx);
              const variação =
                pct === null
                  ? ""
                  : `<span style="margin-left:8px;font-weight:600;color:${pct >= 0 ? "#16a34a" : "#dc2626"}">${pct >= 0 ? "▲ +" : "▼ "}${Math.round(pct)}%</span>`;
              return `<div style="display:flex;align-items:center;gap:6px;margin-top:3px">
                <span style="width:8px;height:8px;border-radius:2px;background:${s.color}"></span>
                <span style="color:#475569">${s.seriesName}</span>
                <span style="margin-left:auto;font-weight:600;color:#0f172a">${formatCurrency(s.value)}</span>${variação}
              </div>`;
            })
            .join("");
          return `<div style="min-width:250px"><div style="font-weight:600;color:#0f172a">${arr[0].axisValue}</div>${rows}</div>`;
        },
      },
      dataZoom: expanded
        ? [
            { type: "inside", xAxisIndex: 0 },
            { type: "slider", xAxisIndex: 0, bottom: 12, height: 22 },
          ]
        : undefined,
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: months,
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisTick: { show: false },
        axisLabel: { color: "#64748b", fontSize: 12 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: CHART_COLORS.grid, type: "dashed" } },
        axisLabel: { color: "#64748b", fontSize: 12, formatter: (v: number) => formatCurrencyShort(v) },
      },
      series,
    };
  }, [points, showAllValues, expanded, selectedSeries]);

  const onEvents = useMemo(
    () => ({
      legendselectchanged: (params: unknown) => {
        const p = params as { selected: Record<string, boolean> };
        const next: SeriesVisibility = {};
        for (const [name, on] of Object.entries(p.selected)) {
          const id = NAME_TO_ID[name];
          if (id) next[id] = on;
        }
        onSelectedSeriesChange(next);
      },
    }),
    [onSelectedSeriesChange],
  );

  const handleReady = useCallback((inst: EChartsType) => onReady?.(inst), [onReady]);

  // notMerge=false: preserva o zoom interno do ECharts entre atualizações de opção.
  return <EChart option={option} height={height} notMerge={false} onEvents={onEvents} onReady={handleReady} />;
}
