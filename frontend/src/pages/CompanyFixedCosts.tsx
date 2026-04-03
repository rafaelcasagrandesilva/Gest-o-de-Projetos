import { CompanyFinanceExecutive } from "@/components/company-finance/CompanyFinanceExecutive";

export function CompanyFixedCosts() {
  return (
    <CompanyFinanceExecutive
      tipo="custo_fixo"
      title="Custos fixos da empresa"
      subtitle="Custos recorrentes com valor mensal esperado e pagamentos por competência."
    />
  );
}
