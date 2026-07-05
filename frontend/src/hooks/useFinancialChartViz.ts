import { useCallback, useState } from "react";

/** Visibilidade por série, chaveada pelo id estável da série. */
export type SeriesVisibility = Record<string, boolean>;

/**
 * Estado de visualização do gráfico de Evolução Financeira, controlado pelo React
 * (nunca pelo estado interno do ECharts). Preserva a configuração do usuário
 * — séries ocultas/exibidas e o modo de exibição de valores — através de qualquer
 * reconstrução do gráfico (checkbox, zoom, resize, modal, etc.).
 */
export function useFinancialChartViz(seriesIds: readonly string[]) {
  const [selectedSeries, setSelectedSeries] = useState<SeriesVisibility>(
    () => Object.fromEntries(seriesIds.map((id) => [id, true])),
  );
  const [showAllValues, setShowAllValues] = useState(false);

  /** Liga/desliga uma série (checkbox externo, se houver). */
  const setSeriesVisible = useCallback((id: string, visible: boolean) => {
    setSelectedSeries((prev) => ({ ...prev, [id]: visible }));
  }, []);

  /** Aplica uma seleção inteira (ex.: vinda do evento legendselectchanged). */
  const applySelection = useCallback((next: SeriesVisibility) => {
    setSelectedSeries((prev) => ({ ...prev, ...next }));
  }, []);

  return {
    selectedSeries,
    showAllValues,
    setShowAllValues,
    setSeriesVisible,
    applySelection,
  };
}
