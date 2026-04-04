import { useAuth } from "@/context/AuthContext";

export function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-6">
        <h1 className="text-sm font-medium text-slate-500">Área logada</h1>
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
