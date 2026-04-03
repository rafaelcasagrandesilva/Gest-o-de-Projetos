import { CompanyFinanceExecutive } from "@/components/company-finance/CompanyFinanceExecutive";

export function CompanyDebt() {
  return (
    <CompanyFinanceExecutive
      tipo="endividamento"
      title="Endividamento da empresa"
      subtitle="Controle de dívidas com valor total de referência e pagamentos registrados mês a mês."
    />
  );
}
