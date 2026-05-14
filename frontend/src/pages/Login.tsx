import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { API_BASE, getStoredToken } from "@/services/api";
import { isAxiosError } from "axios";

export function Login() {
  const { login, user, loading } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { workspace, setWorkspace } = useWorkspace();
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "";
  const fallback = workspace === "projects" ? "/projects/dashboard" : "/finance/dashboard";
  const target = from && from !== "/" ? from : fallback;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (loading && getStoredToken()) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  if (!loading && getStoredToken() && user) {
    return <Navigate to={target} replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const me = await login(email.trim(), password);
      const loginWorkspace = me.current_workspace ?? me.default_workspace ?? workspace;
      setWorkspace(loginWorkspace);
      const workspaceTarget = loginWorkspace === "projects" ? "/projects/dashboard" : "/finance/dashboard";
      navigate(from && from !== "/" ? target : workspaceTarget, { replace: true });
    } catch (err) {
      if (isAxiosError(err)) {
        const status = err.response?.status;
        const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail;
        if (!err.response) {
          let msg = `Não foi possível conectar à API (${API_BASE}). Verifique se o backend está rodando e acessível.`;
          if (import.meta.env.PROD && API_BASE.includes("localhost")) {
            msg +=
              " Em produção, defina a variável VITE_API_BASE no painel do host com a URL HTTPS do backend e faça um novo build.";
          }
          setError(msg);
        } else if (typeof detail === "string" && detail.trim()) {
          setError(detail);
        } else if (status === 401) {
          setError("Credenciais inválidas. Verifique email e senha.");
        } else {
          setError(`Falha no login (HTTP ${status ?? "?"}).`);
        }
      } else {
        setError("Erro inesperado.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-100 to-indigo-50 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200/80 bg-white p-8 shadow-xl shadow-slate-200/50">
        <div className="mb-8 text-center">
          <h1 className="text-xl font-semibold leading-snug tracking-tight text-slate-900 sm:text-2xl">
            Sistema de Gestão de Contratos
          </h1>
          <p className="mt-1 text-sm text-slate-500">Entre com sua conta</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-5">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
          )}
          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none ring-indigo-500/0 transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
              placeholder="admin@admin.com"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700">
              Senha
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            />
          </div>
          <button
            type="submit"
            disabled={submitting || loading}
            className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:opacity-60"
          >
            {submitting ? "Entrando…" : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
