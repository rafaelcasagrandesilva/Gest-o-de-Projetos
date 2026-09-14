import { api } from "./api";

export interface SystemSettings {
  id: string;
  created_at: string;
  updated_at: string;
  /** Reserva: usado só em meses sem regime tributário cadastrado. */
  tax_rate: number;
  overhead_rate: number;
  anticipation_rate: number;
  /** AUTOMATICO: custo real dos borderôs / média dos meses pagos. FIXO: usa anticipation_rate. */
  anticipation_mode: "AUTOMATICO" | "FIXO";
  clt_charges_rate: number;
  // Regime tributário (frações 0–1, exceto o limite mensal em R$)
  iss_rate: number;
  pis_presumido_rate: number;
  cofins_presumido_rate: number;
  irpj_presumption_rate: number;
  csll_presumption_rate: number;
  irpj_rate: number;
  irpj_additional_rate: number;
  irpj_additional_monthly_threshold: number;
  csll_rate: number;
  pis_real_rate: number;
  cofins_real_rate: number;
  /** Créditos estimados de PIS/COFINS no Lucro Real, como fração da receita. */
  pis_cofins_credit_rate: number;
  vehicle_light_cost: number;
  vehicle_pickup_cost: number;
  vehicle_sedan_cost: number;
  vr_value: number;
  fuel_ethanol: number;
  fuel_gasoline: number;
  fuel_diesel: number;
  consumption_light: number;
  consumption_pickup: number;
  consumption_sedan: number;
}

export type TaxRegime = "LUCRO_PRESUMIDO" | "LUCRO_REAL";

export interface TaxRegimePeriod {
  id: string;
  regime: TaxRegime;
  /** ISO date (YYYY-MM-DD), sempre o 1º dia do mês. */
  start_date: string;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export async function fetchSettings(): Promise<SystemSettings> {
  const { data } = await api.get<SystemSettings>("/settings/");
  return data;
}

export async function updateSettings(payload: Partial<SystemSettings>): Promise<SystemSettings> {
  const { data } = await api.put<SystemSettings>("/settings/", payload);
  return data;
}

export async function fetchTaxRegimes(): Promise<TaxRegimePeriod[]> {
  const { data } = await api.get<TaxRegimePeriod[]>("/settings/tax-regimes");
  return data;
}

export async function createTaxRegime(payload: {
  regime: TaxRegime;
  start_date: string;
  note?: string | null;
}): Promise<TaxRegimePeriod> {
  const { data } = await api.post<TaxRegimePeriod>("/settings/tax-regimes", payload);
  return data;
}

export async function deleteTaxRegime(periodId: string): Promise<void> {
  await api.delete(`/settings/tax-regimes/${periodId}`);
}
