import { NavLink } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
    isActive
      ? "bg-indigo-600 text-white shadow-sm"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;

export function AssetsSidebar() {
  const { user } = useAuth();
  const canView = hasPermission(user?.permission_names, "assets.view");

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-5">
        <div className="text-lg font-semibold tracking-tight text-indigo-600">SGC</div>
        <p className="mt-0.5 text-xs text-slate-500">Gestão de Ativos</p>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 p-3">
        {canView ? (
          <>
            <NavLink to="/assets/dashboard" className={linkClass}>
              Dashboard
            </NavLink>
            <NavLink to="/assets" end className={linkClass}>
              Patrimônio
            </NavLink>
          </>
        ) : null}
      </nav>
    </aside>
  );
}
