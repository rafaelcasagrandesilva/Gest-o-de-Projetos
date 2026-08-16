import type { LegalCase, LegalPerson } from "@/services/legal";
import { LEGAL_STATUS_LABELS, LEGAL_TYPE_LABELS } from "@/services/legal";
import { compareText } from "@/utils/sortComparators";
import type { SortColumnDef } from "@/utils/sortTableRows";

/** Ordem de negócio dos status (ciclo de vida) — espelha STATUS_ORDER no backend. */
const STATUS_ORDER: Record<string, number> = {
  EM_ANDAMENTO: 0,
  COM_DECISAO: 1,
  ACORDO: 2,
  ACORDO_FINALIZADO: 3,
  SUSPENSO: 4,
  ENCERRADO: 5,
  SEM_PROCESSO: 6,
};

export type LegalCaseSortColumn =
  | "case_number"
  | "person"
  | "cpf"
  | "company"
  | "project"
  | "uf"
  | "status"
  | "considered"
  | "claimed"
  | "last_movement";

export const LEGAL_CASE_SORT_COLUMNS: Record<LegalCaseSortColumn, SortColumnDef<LegalCase>> = {
  case_number: { kind: "documentNumber", getValue: (c) => c.case_number },
  person: { kind: "text", getValue: (c) => c.person_name ?? c.claimant_name ?? "" },
  cpf: { kind: "text", getValue: (c) => c.person_cpf ?? "" },
  company: { kind: "text", getValue: (c) => c.company ?? "" },
  project: { kind: "text", getValue: (c) => c.project ?? "" },
  uf: { kind: "text", getValue: (c) => c.uf ?? "" },
  status: { kind: "status", getValue: (c) => c.status, statusOrder: STATUS_ORDER },
  considered: { kind: "money", getValue: (c) => c.amount_considered ?? 0 },
  claimed: { kind: "money", getValue: (c) => c.amount_claimed ?? 0 },
  last_movement: { kind: "date", getValue: (c) => c.last_movement_date ?? "" },
};

/** Sem coluna escolhida: maior passivo primeiro (é a leitura padrão do Painel de Passivo). */
export function defaultLegalCaseSort(a: LegalCase, b: LegalCase): number {
  const byValue = (b.amount_considered ?? 0) - (a.amount_considered ?? 0);
  if (byValue !== 0) return byValue;
  return compareText(a.case_number, b.case_number);
}

export type LegalPersonSortColumn =
  | "name"
  | "cpf"
  | "company"
  | "project"
  | "case_count"
  | "claimed"
  | "considered";

export const LEGAL_PERSON_SORT_COLUMNS: Record<LegalPersonSortColumn, SortColumnDef<LegalPerson>> = {
  name: { kind: "text", getValue: (p) => p.full_name },
  cpf: { kind: "text", getValue: (p) => p.cpf ?? "" },
  company: { kind: "text", getValue: (p) => p.company ?? "" },
  project: { kind: "text", getValue: (p) => p.project ?? "" },
  case_count: { kind: "number", getValue: (p) => p.case_count },
  claimed: { kind: "money", getValue: (p) => p.total_claimed ?? 0 },
  considered: { kind: "money", getValue: (p) => p.total_considered ?? 0 },
};

export function defaultLegalPersonSort(a: LegalPerson, b: LegalPerson): number {
  return compareText(a.full_name, b.full_name);
}

export const LEGAL_STATUS_LABEL_LIST = LEGAL_STATUS_LABELS;
export const LEGAL_TYPE_LABEL_LIST = LEGAL_TYPE_LABELS;
