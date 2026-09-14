import { api } from "./api";
import type { TaxRegime } from "./dashboard";

/**
 * Resultado da Empresa (módulo Indicadores).
 *
 * Junta o resultado dos PROJETOS (motor do Dashboard Operacional) com o que a EMPRESA
 * precisa pagar (Custos Indiretos + Endividamento). Valores monetários chegam como
 * `number | null` — `null` = redigido pelo backend (sem permissão de dados sensíveis).
 * Frações (`anticipation_rate`, `available_margin`, `coverage`) vão de 0 a 1.
 */

export type CompanyResultScenario = "REALIZADO" | "PREVISTO";

/**
 * Base dos custos no Resultado da Empresa:
 * - "PAGO" (REALIZADO): o que já aconteceu — custos só pelo valor efetivamente pago no Contas a Pagar até agora;
 *   o lançado e não pago vai para os campos `*_open_cost` ("a pagar").
 * - "LANCADO" (PREVISTO): simulação se todas as contas lançadas forem pagas (ou estimativa/projeção quando
 *   as contas do mês ainda não foram geradas); `*_open_cost` = 0.
 */
export type CompanyResultBasis = "PAGO" | "LANCADO";

export interface CompanyResultMonth {
  /** "YYYY-MM-DD" (primeiro dia do mês); null em `totals`. */
  competencia: string | null;
  // Projetos
  revenue: number | null;
  /** labor + vehicle + system + fixed_operational */
  direct_cost: number | null;
  labor_cost: number | null;
  vehicle_cost: number | null;
  system_cost: number | null;
  fixed_operational_cost: number | null;
  /** Sem significado nesta tela (backend envia false); o Dashboard Operacional tem o próprio. */
  labor_real?: boolean;
  /** Sem significado nesta tela (backend envia false); o Dashboard Operacional tem o próprio. */
  vehicle_real?: boolean;
  /** REALIZADO: custos diretos lançados e ainda não pagos ("a pagar", fora do resultado). 0 no PREVISTO. */
  direct_open_cost?: number | null;
  /** revenue − direct_cost */
  contribution_margin: number | null;
  /** null = percentual de reserva (sem regime cadastrado); "MISTO" só em totais */
  tax_regime?: TaxRegime | null;
  /** fração 0–1: tax_amount / revenue */
  tax_rate?: number | null;
  tax_pis?: number | null;
  tax_cofins?: number | null;
  tax_iss?: number | null;
  tax_irpj?: number | null;
  tax_csll?: number | null;
  tax_amount: number | null;
  /** Lepta + Daycoval, custo das operações do mês seguinte */
  anticipation_amount: number | null;
  /** fração 0–1 sobre a receita */
  anticipation_rate: number | null;
  /** true = operações do mês seguinte ainda em andamento (valor pode subir) */
  anticipation_partial: boolean;
  /** Custo da antecipação (R$) por instituição; soma = anticipation_amount. Vazio/null = taxa fixa (sem divisão). */
  anticipation_by_institution?: Record<string, number> | null;
  /** revenue − direct − tax − anticipation */
  operational_profit: number | null;
  /** Retenção 10% (retida pelo cliente, não disponível) */
  retention: number | null;
  /** operational_profit − retention */
  available_profit: number | null;
  // Empresa
  indirect_cost: number | null;
  indirect_labor_cost: number | null;
  indirect_supplier_cost: number | null;
  /** REALIZADO: custos indiretos lançados e ainda não pagos ("a pagar", fora do resultado). 0 no PREVISTO. */
  indirect_open_cost: number | null;
  /** PREVISTO: mês(es) ainda não gerados no Contas a Pagar → projeção pelo cadastro */
  indirect_projected: boolean;
  debt_cost: number | null;
  /** REALIZADO: parcelas de dívida lançadas e ainda não pagas ("a pagar", fora do resultado). 0 no PREVISTO. */
  debt_open_cost: number | null;
  debt_projected: boolean;
  /** REALIZADO: o mês de pagamento (seguinte ao trabalhado) ainda está em curso — mais pagamentos podem entrar. */
  company_costs_partial?: boolean;
  /** true = mês(es) fechado(s): custos indiretos e endividamento pelo VALOR PAGO no Contas a Pagar */
  paid_basis: boolean;
  /** IRPJ/CSLL do Lucro Real sobre o lucro da empresa (0 com prejuízo ou no Presumido). */
  profit_tax_amount?: number | null;
  /** available_profit − indirect_cost − profit_tax_amount − debt_cost */
  company_result: number | null;
  /** fração: available_profit / revenue */
  available_margin: number | null;
  /** fração: available_profit / (indirect_cost + profit_tax_amount + debt_cost) */
  coverage: number | null;
  /**
   * fração: margem que teria que sobrar como lucro disponível para pagar custos indiretos,
   * IRPJ/CSLL e dívidas e fechar em zero = (indirect_cost + profit_tax_amount + debt_cost) / revenue.
   * null quando a receita é 0.
   */
  required_margin: number | null;
  /**
   * Receita necessária no mês/período para o resultado da empresa fechar em ZERO — existe sempre
   * que há receita, inclusive com resultado negativo:
   * (direct + indirect + debts) ÷ (1 − (taxes + anticipation + retention) / revenue).
   */
  break_even_revenue: number | null;
  /** break_even_revenue − revenue: positivo = receita que faltou; negativo = resultado já positivo. */
  revenue_gap: number | null;
}

export interface CompanyResultIndirectCategory {
  category: string;
  amount: number | null;
}

export interface CompanyResultIndirectItem {
  item_id: string;
  name: string;
  category: string;
  is_labor: boolean;
  amount: number | null;
}

export interface CompanyResultDebtItem {
  item_id: string;
  name: string;
  amount: number | null;
}

export interface CompanyResult {
  scenario: CompanyResultScenario;
  /** REALIZADO → "PAGO", PREVISTO → "LANCADO". Ausente em backends antigos: derivar de `scenario`. */
  basis?: CompanyResultBasis;
  period_start: string;
  period_end: string;
  month_count: number;
  /** somas do período; frações recalculadas sobre os totais; booleanos = qualquer mês */
  totals: CompanyResultMonth;
  /** cronológico */
  months: CompanyResultMonth[];
  /** período, desc por valor */
  indirect_by_category: CompanyResultIndirectCategory[];
  /** período, desc por valor (todos os itens) */
  indirect_items: CompanyResultIndirectItem[];
  /** período, desc por valor */
  debt_items: CompanyResultDebtItem[];
}

/** GET /api/v1/indicators/company-result (perm: company_result.read). */
export async function fetchCompanyResult(params: {
  data_inicial: string;
  data_final: string;
  scenario: CompanyResultScenario;
}): Promise<CompanyResult> {
  const { data } = await api.get<CompanyResult>("/indicators/company-result", {
    params: {
      data_inicial: params.data_inicial,
      data_final: params.data_final,
      scenario: params.scenario,
    },
  });
  return data;
}
