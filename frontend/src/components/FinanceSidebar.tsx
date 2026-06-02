import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";
import { AppSidebarShell } from "@/components/AppSidebarShell";
import { SidebarNavItem } from "@/components/SidebarNavItem";

const items: {
  to: string;
  label: string;
  end: boolean;
  perm: string;
}[] = [
  { to: "/finance/dashboard", label: "Dashboard", end: true, perm: "billing.view" },
  { to: "/finance/payables", label: "Contas a pagar", end: false, perm: "payables.view" },
  { to: "/finance/receivables", label: "Contas a receber", end: false, perm: "receivables.view" },
  { to: "/finance/invoices", label: "Notas fiscais (NFs)", end: false, perm: "invoices.view" },
  { to: "/finance/advance-batches", label: "Antecipações", end: false, perm: "invoices.view" },
  { to: "/finance/debt", label: "Endividamento", end: false, perm: "debts.view" },
  { to: "/finance/fixed-costs", label: "Custos Fixos - Matriz", end: false, perm: "company_finance.view" },
  { to: "/finance/reports", label: "Relatórios", end: false, perm: "reports.view" },
  { to: "/settings", label: "Configurações", end: false, perm: "settings.view" },
];

function visibleSidebarItems(perms: string[] | undefined) {
  return items.filter((i) => {
    if (i.to === "/settings") {
      return hasPermission(perms, "settings.view") || hasPermission(perms, "audit.export");
    }
    return hasPermission(perms, i.perm);
  });
}

export function FinanceSidebar() {
  const { user } = useAuth();
  const perms = user?.permission_names;
  const visible = visibleSidebarItems(perms);

  return (
    <AppSidebarShell subtitle="Workspace: Financeiro">
      {visible.map((item) => (
        <SidebarNavItem
          key={item.to}
          to={item.to}
          end={item.end}
          label={item.label}
        />
      ))}
    </AppSidebarShell>
  );
}
