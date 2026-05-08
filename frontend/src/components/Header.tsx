import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";
import { useWorkspace, type WorkspaceName } from "@/context/WorkspaceContext";
import { useNavigate } from "react-router-dom";

export function Header() {
  const { user, logout } = useAuth();
  const { workspace, setWorkspace } = useWorkspace();
  const navigate = useNavigate();
  const perms = user?.permission_names;

  const canProjects = hasPermission(perms, "workspace.projects.access");
  const canFinance = hasPermission(perms, "workspace.finance.access");

  function go(w: WorkspaceName) {
    if (w === workspace) return;
    setWorkspace(w);
    navigate(w === "projects" ? "/projects/dashboard" : "/finance/dashboard");
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-6">
        <h1 className="text-sm font-medium text-slate-500">Área logada</h1>
        {(canProjects || canFinance) && (
          <div className="inline-flex overflow-hidden rounded-lg border border-slate-200 bg-white">
            {canProjects && (
              <button
                type="button"
                onClick={() => go("projects")}
                className={`px-3 py-1.5 text-sm font-medium ${
                  workspace === "projects"
                    ? "bg-indigo-600 text-white"
                    : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                Projetos
              </button>
            )}
            {canFinance && (
              <button
                type="button"
                onClick={() => go("finance")}
                className={`px-3 py-1.5 text-sm font-medium ${
                  workspace === "finance"
                    ? "bg-indigo-600 text-white"
                    : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                Financeiro
              </button>
            )}
          </div>
        )}
      </div>
      <div className="flex items-center gap-4">
        {user?.role_names?.includes("CONSULTA") && (
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-900">
            Acesso somente leitura
          </span>
        )}
        <span className="text-sm text-slate-700">
          <span className="font-medium text-slate-900">{user?.full_name ?? "—"}</span>
          <span className="ml-2 text-slate-400">{user?.email}</span>
        </span>
        <button
          type="button"
          onClick={() => logout()}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
        >
          Sair
        </button>
      </div>
    </header>
  );
}
