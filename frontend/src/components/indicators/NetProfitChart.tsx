import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { FinancialEvolutionPoint } from "@/services/indicators";
import { EChart } from "@/components/dashboard/executive/EChart";
import { formatCurrencyOrDash, formatCurrencyShort } from "@/utils/currency";
import { CHART_COLORS } from "@/utils/chartTheme";
import { monthLabel } from "@/utils/roiFormat";

/**
 * Gráfico secundário do Dashboard Executivo (Apache ECharts): Lucro Líquido.
 * Barras verdes (positivo) e coral (negativo), com escala própria, linha zero
 * destacada e rótulos posicionados conforme o sinal (evita sobreposição).
 */
export function NetProfitChart({
  points,
  height = 240,
}: {
  points: FinancialEvolutionPoint[];
  height?: number;
}) {
  const option = useMemo<EChartsOption>(() => {
    const months = points.map((p) => monthLabel(p.competencia));
    const data = points.map((p) => {
      const neg = p.lucro_liquido < 0;
      return {
        value: p.lucro_liquido,
        itemStyle: {
          color: neg ? CHART_COLORS.caixaNeg : CHART_COLORS.caixaPos,
          borderRadius: neg ? [0, 0, 3, 3] : [3, 3, 0, 0],
        },
        // Positivo: rótulo acima da barra; negativo: abaixo — sem colidir com o eixo.
        label: { position: neg ? ("bottom" as const) : ("top" as const) },
      };
    });

    return {
      grid: { top: 24, right: 18, bottom: 26, left: 60 },
      tooltip: {
        trigger: "axis",
        borderColor: "#e2e8f0",
        textStyle: { color: "#0f172a" },
        formatter: (params: unknown) => {
          const arr = params as Array<{ axisValue: string; value: number; color: string }>;
          if (!arr.length) return "";
          const s = arr[0];
          return `<div style="font-weight:600;color:#0f172a">${s.axisValue}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:3px">
              <span style="width:8px;height:8px;border-radius:2px;background:${s.color}"></span>
              <span style="color:#475569">Lucro Líquido</span>
              <span style="margin-left:auto;font-weight:600;color:#0f172a">${formatCurrencyOrDash(s.value == null ? null : Number(s.value))}</span>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: months,
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisTick: { show: false },
        axisLabel: { color: "#64748b", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: CHART_COLORS.grid, type: "dashed" } },
        axisLabel: { color: "#64748b", fontSize: 11, formatter: (v: number) => formatCurrencyShort(v) },
      },
      series: [
        {
          name: "Lucro Líquido",
          type: "bar",
          barMaxWidth: 30,
          data,
          label: {
            show: true,
            distance: 6,
            fontSize: 10,
            fontWeight: "bold",
            color: "#475569",
            formatter: (p: { value?: unknown }) => (p.value == null ? "—" : formatCurrencyShort(Number(p.value))),
          },
          labelLayout: { hideOverlap: true },
          // Linha zero em destaque (referência de equilíbrio do resultado).
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#0f172a", width: 1.5, type: "solid", opacity: 0.55 },
            data: [{ yAxis: 0 }],
            label: { show: false },
          },
        },
      ],
    };
  }, [points]);

  return <EChart option={option} height={height} />;
}
