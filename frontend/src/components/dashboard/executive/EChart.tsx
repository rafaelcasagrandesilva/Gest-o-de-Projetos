import ReactECharts from "echarts-for-react";
import type { EChartsOption, EChartsType } from "echarts";

/**
 * Wrapper padrão de Apache ECharts para os Dashboards Executivos do SGC.
 *
 * ECharts é a biblioteca padrão dos dashboards executivos. Centraliza tema,
 * renderer SVG e o comportamento responsivo. O `echarts-for-react` já observa o
 * container (size-sensor / `autoResize`), então o layout dos rótulos é recalculado
 * automaticamente quando o container muda de tamanho (ex.: abrir/fechar o modal).
 */

// Referência estável de `opts`: evita que o echarts-for-react descarte e recrie a
// instância a cada render (ele compara `opts` por igualdade profunda).
const ECHARTS_OPTS = { renderer: "svg" } as const;

export function EChart({
  option,
  height = 320,
  className,
  notMerge = true,
  onEvents,
  onReady,
}: {
  option: EChartsOption;
  height?: number | string;
  className?: string;
  /** false = merge (preserva estado interno como zoom); true = substitui (padrão) */
  notMerge?: boolean;
  /** mapa de eventos ECharts → handlers (ex.: legendselectchanged, datazoom) */
  onEvents?: Record<string, (params: unknown) => void>;
  /**
   * Recebe a instância ECharts quando ela está pronta (ex.: para dispatchAction /
   * resetar zoom). Usa o callback nativo `onChartReady` do echarts-for-react, que
   * dispara APÓS a inicialização assíncrona da instância.
   */
  onReady?: (instance: EChartsType) => void;
}) {
  return (
    <ReactECharts
      option={option}
      className={className}
      style={{ height, width: "100%" }}
      notMerge={notMerge}
      lazyUpdate
      opts={ECHARTS_OPTS}
      onEvents={onEvents}
      onChartReady={onReady}
    />
  );
}
