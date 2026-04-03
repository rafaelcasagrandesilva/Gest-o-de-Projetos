import { useEffect, useState } from "react";
import { createUser, listUsers, patchUser, resetUserPassword, type UserRow } from "@/services/users";
import { listProjects, type Project } from "@/services/projects";
import { isAxiosError } from "axios";

const ROLES = ["ADMIN", "GESTOR", "CONSULTA"] as const;
type RoleName = (typeof ROLES)[number];

export function Users() {
  const [items, setItems] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [roleName, setRoleName] = useState<RoleName>("CONSULTA");
  const [projectIds, setProjectIds] = useState<Set<string>>(new Set());
  const [allProjects, setAllProjects] = useState<Project[]>([]);
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [resetFor, setResetFor] = useState<UserRow | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetting, setResetting] = useState(false);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [editRole, setEditRole] = useState<RoleName>("CONSULTA");
  const [editProjectIds, setEditProjectIds] = useState<Set<string>>(new Set());
  const [savingEdit, setSavingEdit] = useState(false);

  async function loadProjects() {
    try {
      const p = await listProjects();
      setAllProjects(p);
    } catch {
      setAllProjects([]);
    }
  }

  async function load() {
    setError(null);
    try {
      const data = await listUsers();
      setItems(data);
    } catch (e) {
      if (isAxiosError(e) && e.response?.status === 403) {
        setError("Sem permissão para listar usuários (apenas ADMIN).");
      } else {
        setError("Erro ao listar usuários.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (showForm || editing) {
      void loadProjects();
    }
  }, [showForm, editing]);

  function toggleCreateProject(id: string) {
    setProjectIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function toggleEditProject(id: string) {
    setEditProjectIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function openEdit(u: UserRow) {
    setEditing(u);
    const r = (u.role_names?.[0] as RoleName) || "CONSULTA";
    setEditRole(ROLES.includes(r) ? r : "CONSULTA");
    setEditProjectIds(new Set(u.project_ids || []));
    setError(null);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await createUser({
        email: email.trim(),
        full_name: fullName.trim(),
        password,
        role_name: roleName,
        project_ids: roleName === "GESTOR" ? Array.from(projectIds) : undefined,
      });
      setEmail("");
      setFullName("");
      setPassword("");
      setRoleName("CONSULTA");
      setProjectIds(new Set());
      setShowForm(false);
      await load();
    } catch (err) {
      if (isAxiosError(err)) {
        const d = err.response?.data?.detail;
        setError(typeof d === "string" ? d : "Não foi possível criar o usuário.");
      } else {
        setError("Erro inesperado.");
      }
    } finally {
      setCreating(false);
    }
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setSavingEdit(true);
    setError(null);
    try {
      const body: Parameters<typeof patchUser>[1] = { role_name: editRole };
      if (editRole === "GESTOR") {
        body.project_ids = Array.from(editProjectIds);
      }
      await patchUser(editing.id, body);
      setEditing(null);
      await load();
    } catch (err) {
      if (isAxiosError(err)) {
        const d = err.response?.data?.detail;
        setError(typeof d === "string" ? d : "Não foi possível atualizar o usuário.");
      } else {
        setError("Erro inesperado.");
      }
    } finally {
      setSavingEdit(false);
    }
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!resetFor || resetPassword.length < 6) return;
    setResetting(true);
    setError(null);
    try {
      await resetUserPassword(resetFor.id, resetPassword);
      setResetFor(null);
      setResetPassword("");
    } catch (err) {
      if (isAxiosError(err)) {
        const d = err.response?.data?.detail;
        if (Array.isArray(d)) {
          setError(d.map((x: { msg?: string }) => x.msg).filter(Boolean).join(" ") || "Erro de validação.");
        } else {
          setError(typeof d === "string" ? d : "Não foi possível resetar a senha.");
        }
      } else {
        setError("Erro inesperado.");
      }
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Usuários</h2>
          <p className="text-sm text-slate-500">Lista e cadastro (perfil e projetos do gestor)</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            {showForm ? "Fechar formulário" : "Novo usuário"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-200 bg-white p-6 shadow-lg"
          >
            <h3 className="text-lg font-semibold text-slate-900">Editar usuário</h3>
            <p className="mt-1 text-sm text-slate-500">
              {editing.full_name} ({editing.email})
            </p>
            <form onSubmit={handleSaveEdit} className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-sm text-slate-600">Perfil</label>
                <select
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value as RoleName)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
              {editRole === "GESTOR" && (
                <div>
                  <p className="mb-2 text-sm font-medium text-slate-700">Projetos permitidos</p>
                  <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-slate-100 p-3">
                    {allProjects.length === 0 ? (
                      <p className="text-sm text-slate-500">Nenhum projeto listado.</p>
                    ) : (
                      allProjects.map((p) => (
                        <label key={p.id} className="flex cursor-pointer items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={editProjectIds.has(p.id)}
                            onChange={() => toggleEditProject(p.id)}
                          />
                          <span>{p.name}</span>
                        </label>
                      ))
                    )}
                  </div>
                </div>
              )}
              {editRole === "CONSULTA" && (
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Acesso somente leitura</p>
              )}
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditing(null)}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
                >
                  {savingEdit ? "Salvando…" : "Salvar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {resetFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-password-title"
            className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-lg"
          >
            <h3 id="reset-password-title" className="text-lg font-semibold text-slate-900">
              Resetar senha
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Usuário: <span className="font-medium text-slate-700">{resetFor.full_name}</span> ({resetFor.email})
            </p>
            <form onSubmit={handleResetPassword} className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-sm text-slate-600">Nova senha (mín. 6 caracteres)</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  autoComplete="new-password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setResetFor(null);
                    setResetPassword("");
                  }}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={resetting || resetPassword.length < 6}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
                >
                  {resetting ? "Salvando…" : "Confirmar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="max-w-lg space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h3 className="font-medium text-slate-900">Criar usuário</h3>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Nome completo</label>
            <input
              required
              minLength={2}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Email</label>
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Senha</label>
            <input
              required
              type="password"
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Perfil</label>
            <select
              value={roleName}
              onChange={(e) => setRoleName(e.target.value as RoleName)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          {roleName === "GESTOR" && (
            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Projetos permitidos</p>
              <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-slate-100 p-3">
                {allProjects.length === 0 ? (
                  <p className="text-sm text-slate-500">Nenhum projeto listado.</p>
                ) : (
                  allProjects.map((p) => (
                    <label key={p.id} className="flex cursor-pointer items-center gap-2 text-sm">
                      <input type="checkbox" checked={projectIds.has(p.id)} onChange={() => toggleCreateProject(p.id)} />
                      <span>{p.name}</span>
                    </label>
                  ))
                )}
              </div>
            </div>
          )}
          {roleName === "CONSULTA" && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Acesso somente leitura</p>
          )}
          <button
            type="submit"
            disabled={creating}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {creating ? "Salvando…" : "Salvar"}
          </button>
        </form>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
          Carregando…
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/80">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-600">Nome</th>
                <th className="px-4 py-3 font-medium text-slate-600">Email</th>
                <th className="px-4 py-3 font-medium text-slate-600">Perfil</th>
                <th className="px-4 py-3 font-medium text-slate-600">Projetos (gestor)</th>
                <th className="px-4 py-3 font-medium text-slate-600">Ativo</th>
                <th className="px-4 py-3 font-medium text-slate-600 w-44" />
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                    Nenhum usuário ou sem permissão para listar.
                  </td>
                </tr>
              ) : (
                items.map((u) => {
                  const primaryRole = u.role_names?.[0] || "—";
                  return (
                    <tr key={u.id} className="border-b border-slate-50 last:border-0">
                      <td className="px-4 py-3 font-medium text-slate-900">{u.full_name}</td>
                      <td className="px-4 py-3 text-slate-600">{u.email}</td>
                      <td className="px-4 py-3 text-slate-600">
                        <span className="inline-flex flex-wrap items-center gap-1">
                          {primaryRole}
                          {primaryRole === "CONSULTA" && (
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">somente leitura</span>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {primaryRole === "GESTOR" ? (u.project_ids?.length ? `${u.project_ids.length} vínculo(s)` : "—") : "—"}
                      </td>
                      <td className="px-4 py-3">{u.is_active ? "Sim" : "Não"}</td>
                      <td className="px-4 py-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => openEdit(u)}
                          className="text-sm font-medium text-slate-700 hover:underline"
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setResetFor(u);
                            setResetPassword("");
                            setError(null);
                          }}
                          className="text-sm font-medium text-indigo-600 hover:underline"
                        >
                          Resetar senha
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
