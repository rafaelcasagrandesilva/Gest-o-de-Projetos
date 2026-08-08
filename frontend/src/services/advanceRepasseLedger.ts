import { api } from "./api";

// Extrato de Repasse (append-only). O usuário vê apenas "Entradas/Saídas" e o "Saldo" — nunca
// precisa entender Ledger. Tudo vem pronto do backend.

export type LedgerDirection = "CREDIT" | "DEBIT";
export type LedgerSourceType = "OPERATION" | "SETTLEMENT" | "WITHDRAWAL" | "ADJUSTMENT";
export type WithdrawalPurpose = "DEBT_REDUCTION" | "OTHER";

export const DIRECTION_LABELS: Record<LedgerDirection, string> = {
  CREDIT: "Entrada",
  DEBIT: "Saída",
};

export const SOURCE_LABELS: Record<LedgerSourceType, string> = {
  OPERATION: "Operação de antecipação",
  SETTLEMENT: "Liquidação de NF",
  WITHDRAWAL: "Retirada de Repasse",
  ADJUSTMENT: "Ajuste",
};

// Destino estruturado da retirada — rótulo próprio (nunca dentro da descrição livre).
export const WITHDRAWAL_PURPOSE_LABELS: Record<WithdrawalPurpose, string> = {
  DEBT_REDUCTION: "Abatimento de dívida",
  OTHER: "Outros",
};

export interface LedgerEntry {
  id: string;
  institution_id: string;
  direction: LedgerDirection;
  amount: number;
  source_type: LedgerSourceType;
  withdrawal_purpose: WithdrawalPurpose | null;
  source_batch_id: string | null;
  source_movement_id: string | null;
  occurred_at: string;
  description: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
  created_at: string;
}

export interface LedgerStatement {
  institution_id: string | null;
  balance: number;
  entries: LedgerEntry[];
}

export async function fetchRepasseLedger(
  institutionId?: string | null,
  includeReversed = true,
): Promise<LedgerStatement> {
  const params: Record<string, string | boolean> = { include_reversed: includeReversed };
  if (institutionId) params.institution_id = institutionId;
  const { data } = await api.get<LedgerStatement>("/invoices/advance-repasse-ledger", { params });
  return data;
}

export interface WithdrawalInput {
  institution_id: string;
  amount: number;
  occurred_at: string; // YYYY-MM-DD
  purpose: WithdrawalPurpose;
  description?: string | null;
}

/** Registra uma Retirada de Repasse (DÉBITO append-only). Reduz apenas o saldo do Repasse. */
export async function createRepasseWithdrawal(input: WithdrawalInput): Promise<LedgerEntry> {
  const { data } = await api.post<LedgerEntry>(
    "/invoices/advance-repasse-ledger/withdrawals",
    input,
  );
  return data;
}
