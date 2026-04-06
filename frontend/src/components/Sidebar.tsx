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
  { to: "/", label: "Dashboard financeiro", end: true, perm: "dashboard.view" },
  { to: "/reports", label: "Relatórios", end: false, perm: "reports.view" },
  { to: "/projects", label: "Projetos", end: false, perm: "projects.view" },
  { to: "/users", label: "Usuários", end: false, perm: "users.manage" },
  { to: "/employees", label: "Colaboradores", end: false, perm: "employees.view" },
  { to: "/vehicles", label: "Veículos", end: false, perm: "vehicles.view" },
  { to: "/revenue", label: "Faturamento", end: false, perm: "billing.view" },
  { to: "/invoices", label: "Notas fiscais", end: false, perm: "invoices.view" },
  { to: "/company-debt", label: "Endividamento", end: false, perm: "debts.view" },
  { to: "/company-fixed-costs", label: "Custos fixos (empresa)", end: false, perm: "company_finance.view" },
  { to: "/settings", label: "Configurações", end: false, perm: "settings.view" },
];

export function Sidebar() {
  const { user } = useAuth();
  const perms = user?.permission_names;
  const visible = items.filter((i) => hasPermission(perms, i.perm));

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-5">
        <div className="text-lg font-semibold tracking-tight text-indigo-600">SGC</div>
        <p className="mt-0.5 text-xs text-slate-500">Gestão de projetos</p>
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
