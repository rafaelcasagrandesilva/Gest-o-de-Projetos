import { NavLink } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
    isActive
      ? "bg-indigo-600 text-white shadow-sm"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;

const items: { to: string; label: string; end: boolean; adminOnly?: boolean }[] = [
  { to: "/", label: "Dashboard financeiro", end: true },
  { to: "/reports", label: "Relatórios", end: false },
  { to: "/projects", label: "Projetos", end: false },
  { to: "/users", label: "Usuários", end: false, adminOnly: true },
  { to: "/employees", label: "Colaboradores", end: false },
  { to: "/vehicles", label: "Veículos", end: false },
  { to: "/revenue", label: "Faturamento", end: false },
  { to: "/invoices", label: "Notas fiscais", end: false },
  { to: "/company-debt", label: "Endividamento", end: false },
  { to: "/company-fixed-costs", label: "Custos fixos (empresa)", end: false },
  { to: "/settings", label: "Configurações", end: false, adminOnly: true },
];

export function Sidebar() {
  const { user } = useAuth();
  const isAdmin = user?.role_names?.includes("ADMIN") ?? false;
  const visible = items.filter((i) => !i.adminOnly || isAdmin);

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
