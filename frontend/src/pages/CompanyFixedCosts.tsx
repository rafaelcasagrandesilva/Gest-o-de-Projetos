import { CompanyFinanceExecutive } from "@/components/company-finance/CompanyFinanceExecutive";

export function CompanyFixedCosts() {
  return (
    <CompanyFinanceExecutive
      tipo="custo_fixo"
      title="Custos Indiretos"
      subtitle="Custos da empresa que não estão ligados diretamente a um projeto (administrativo, RH, fornecedores e mão de obra indireta), com valor mensal esperado e pagamentos por competência."
    />
  );
}
