import type { AssetPhysicalCondition, AssetStatus, ExpirationAlertLevel } from "@/services/assets";

export const ASSET_STATUS_LABELS: Record<AssetStatus, string> = {
  AVAILABLE: "Disponível",
  IN_USE: "Em uso",
  MAINTENANCE: "Manutenção",
  EXPIRED: "Vencido",
  LOST: "Extraviado",
  DISCARDED: "Baixado",
};

export const PHYSICAL_CONDITION_LABELS: Record<AssetPhysicalCondition, string> = {
  NEW: "Novo",
  GOOD: "Bom estado",
  FAIR: "Mau estado",
  DAMAGED: "Quebrado",
};

export const EXPIRATION_SHORT_LABELS: Record<ExpirationAlertLevel, string> = {
  NORMAL: "Inspeção em dia",
  YELLOW: "Vence em 30 dias",
  ORANGE: "Vence em 7 dias",
  TOMORROW: "Vence amanhã",
  RED: "Vencido",
};

export type AssignmentListShape = {
  delivered_by_name: string | null;
  employee_name: string;
  delivery_date: string;
  return_date: string | null;
  returned_to_name: string | null;
  returned_condition: AssetPhysicalCondition | null;
};

export function formatAssignmentDeliveryLine(a: AssignmentListShape): string {
  const from = a.delivered_by_name ?? "—";
  return `${from} → ${a.employee_name} — entrega ${a.delivery_date}`;
}

export function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export { formatMoneyFieldBr, moneyFieldFromNumber, parseBRLInput } from "@/components/assets/assetMoney";
