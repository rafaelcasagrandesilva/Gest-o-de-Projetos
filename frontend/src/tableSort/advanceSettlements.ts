import type { Obligation, SituacaoLiquidacao } from "@/services/advanceSettlements";
import { compareDateIso } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

export type ObligationSortColumn =
  | "situacao"
  | "invoice_number"
  | "client"
  | "sgc"
  | "institution"
  | "valor"
  | "liquidado"
  | "residual"
  | "origens"
  | "vencimento"
  | "atraso";

// Ordem por urgência: vencidas primeiro, liquidadas por último.
const SITUACAO_ORDER: Record<SituacaoLiquidacao, number> = {
  VENCIDA: 0,
  PARCIALMENTE_LIQUIDADA: 1,
  EM_ABERTO: 2,
  LIQUIDADA: 3,
};

export const OBLIGATION_SORT_COLUMNS: Record<ObligationSortColumn, SortColumnDef<Obligation>> = {
  situacao: { kind: "status", getValue: (o) => o.situacao, statusOrder: SITUACAO_ORDER },
  invoice_number: { kind: "documentNumber", getValue: (o) => o.invoice_number ?? "" },
  client: { kind: "text", getValue: (o) => o.client_name ?? "" },
  sgc: { kind: "number", getValue: (o) => Number(o.sgc_number ?? 0) },
  institution: { kind: "text", getValue: (o) => o.institution ?? "" },
  valor: { kind: "money", getValue: (o) => Number(o.valor_total ?? 0) },
  liquidado: { kind: "money", getValue: (o) => Number(o.valor_liquidado ?? 0) },
  residual: { kind: "money", getValue: (o) => Number(o.valor_residual ?? 0) },
  origens: { kind: "text", getValue: (o) => o.origens_resumo ?? "" },
  vencimento: { kind: "date", getValue: (o) => o.vencimento ?? "" },
  atraso: { kind: "number", getValue: (o) => Number(o.dias_em_atraso ?? 0) },
};

/** Ordem padrão: vencimento mais antigo primeiro (mais urgente no topo). */
export function defaultObligationSort(a: Obligation, b: Obligation): number {
  return compareDateIso(a.vencimento ?? "", b.vencimento ?? "");
}
