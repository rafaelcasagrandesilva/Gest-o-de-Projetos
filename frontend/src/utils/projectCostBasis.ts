import type { AnticipationSource, TaxRegime } from "@/services/dashboard";
import { formatCurrencyOrDash } from "@/utils/currency";

/**
 * Rótulos e explicações do motor de custos dos projetos (regime tributário, folha/frota reais,
 * origem e divisão da antecipação). Fonte única para o Dashboard Operacional e o Resultado da Empresa.
 */

export const LABOR_REAL_TITLE =
  "Mês fechado: salário, VR/VT e componentes efetivamente pagos no Contas a Pagar. INSS/FGTS recolhidos em guia ficam nos custos indiretos.";

export const VEHICLE_REAL_TITLE =
  "Frota real: parte do projeto na fatura de locação do Contas a Pagar (valor devido) — ou, sem fatura lançada, no custo mensal dos veículos ativos do cadastro — mais o custo adicional da frota (seguro), rateados pelo centro de custo dos veículos.";

/** Nota da origem do custo de antecipação (rodapé do detalhamento). */
export const ANTICIPATION_SOURCE_NOTE: Record<AnticipationSource, string> = {
  REAL: "Custo real das operações do mês seguinte (sem repasse).",
  PARCIAL: "Operações do mês seguinte ainda em andamento — o valor pode subir.",
  MEDIA: "Projeção pela média ponderada dos meses já fechados.",
  FIXA: "Percentual fixo das Configurações (sem divisão por instituição).",
  MISTO: "Período com meses de origens diferentes.",
};

/** Divisão por instituição, válida e ordenada por valor (desc). Ausente/vazia → []. */
export function anticipationInstitutions(
  byInstitution: Record<string, number> | null | undefined,
): Array<[string, number]> {
  if (!byInstitution) return [];
  return Object.entries(byInstitution)
    .filter((e): e is [string, number] => typeof e[1] === "number" && Number.isFinite(e[1]))
    .sort((a, b) => b[1] - a[1]);
}

export const LUCRO_REAL_PROFIT_TAX_NOTE =
  "IRPJ/CSLL do Lucro Real incidem sobre o lucro da empresa e aparecem só no Resultado da Empresa.";

/** "Lucro Presumido" · "Lucro Real" · "regimes mistos" · "percentual de reserva" (sem regime). */
export function taxRegimeName(regime: TaxRegime | null | undefined): string {
  if (regime === "LUCRO_PRESUMIDO") return "Lucro Presumido";
  if (regime === "LUCRO_REAL") return "Lucro Real";
  if (regime === "MISTO") return "regimes mistos";
  return "percentual de reserva";
}

/** Rótulo do item de impostos: "Impostos — Lucro Real" / "Impostos (percentual de reserva)". */
export function taxLabel(regime: TaxRegime | null | undefined): string {
  return regime ? `Impostos — ${taxRegimeName(regime)}` : "Impostos (percentual de reserva)";
}

export interface TaxBreakdown {
  tax_regime?: TaxRegime | null;
  tax_pis?: number | null;
  tax_cofins?: number | null;
  tax_iss?: number | null;
  tax_irpj?: number | null;
  tax_csll?: number | null;
}

/** Linhas "PIS: R$ …" (sem regime cadastrado: explicação do percentual de reserva). */
export function taxBreakdownLines(t: TaxBreakdown): string[] {
  if (!t.tax_regime) return ["Sem regime tributário cadastrado: percentual de reserva sobre a receita."];
  return [
    `PIS: ${formatCurrencyOrDash(t.tax_pis)}`,
    `COFINS: ${formatCurrencyOrDash(t.tax_cofins)}`,
    `ISS: ${formatCurrencyOrDash(t.tax_iss)}`,
    `IRPJ: ${formatCurrencyOrDash(t.tax_irpj)}`,
    `CSLL: ${formatCurrencyOrDash(t.tax_csll)}`,
  ];
}
