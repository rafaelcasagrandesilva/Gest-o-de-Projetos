/**
 * Tokens visuais compartilhados dos gráficos do produto.
 * Fonte única para alinhar Dashboard Financeiro e módulo Indicadores.
 */

export const CHART_COLORS = {
  /** Receita / Faturamento = azul */
  faturamento: "#2563eb",
  /** Custo total = vermelho */
  custos: "#dc2626",
  /** Lucro / Caixa positivo = verde */
  caixaPos: "#16a34a",
  /** Lucro / Caixa negativo = vermelho escuro */
  caixaNeg: "#b91c1c",
  /** ROI (%) = azul claro (linha pontilhada, eixo secundário) */
  roi: "#38bdf8",
  /** Linha de equilíbrio (R$ 0) */
  zeroLine: "#0f172a",
  /** Grade */
  grid: "#E5E7EB",
} as const;

/** Preenchimento da região abaixo de zero (déficit). */
export const NEGATIVE_AREA_FILL = "#fecaca";
export const NEGATIVE_AREA_OPACITY = 0.25;

/** Formata valores do eixo financeiro (R$). Ex.: 1.500.000 → "R$ 1.5M"; -2300 → "-R$ 2k". */
export function formatBRLAxis(value: unknown): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "R$ 0";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}R$ ${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1000) return `${sign}R$ ${Math.round(abs / 1000)}k`;
  return `${sign}R$ ${Math.round(abs)}`;
}
