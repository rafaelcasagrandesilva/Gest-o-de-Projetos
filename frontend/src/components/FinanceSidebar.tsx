import { NavLink } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
    isActive
      ? "bg-indigo-600 text-white shadow-sm"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;

const items: { to: string; label: string; end: boolean; perm: string }[] = [
  { to: "/finance/dashboard", label: "Dashboard", end: true, perm: "billing.view" },
  { to: "/finance/payables", label: "Contas a pagar", end: false, perm: "payables.view" },
  { to: "/finance/receivables", label: "Contas a receber", end: false, perm: "receivables.view" },
  { to: "/finance/invoices", label: "Notas fiscais (NFs)", end: false, perm: "invoices.view" },
  { to: "/finance/debt", label: "Endividamento", end: false, perm: "debts.view" },
  { to: "/finance/fixed-costs", label: "Custos Fixos - Matriz", end: false, perm: "company_finance.view" },
  { to: "/finance/reports", label: "Relatórios", end: false, perm: "reports.view" },
  { to: "/settings", label: "Configurações", end: false, perm: "settings.view" },
];

export function FinanceSidebar() {
  const { user } = useAuth();
  const perms = user?.permission_names;
  const visible = items.filter((i) => hasPermission(perms, i.perm));

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-5">
        <div className="text-lg font-semibold tracking-tight text-indigo-600">SGC</div>
        <p className="mt-0.5 text-xs text-slate-500">Workspace: Financeiro</p>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 p-3">
        {visible.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

