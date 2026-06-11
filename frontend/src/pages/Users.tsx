import { useEffect, useState } from "react";
import {
  activateUser,
  createUser,
  deactivateUser,
  listUsers,
  patchUser,
  resetUserPassword,
  softDeleteUser,
  type UserRow,
} from "@/services/users";
import { listProjects, type Project } from "@/services/projects";
import { isAxiosError } from "axios";
import { usePermission } from "@/hooks/usePermission";
import {
  ALL_PERMISSION_CODES,
  PERMISSION_LABELS,
  ROLE_PERMISSION_PRESET,
} from "@/permissions";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import { USER_SORT_COLUMNS, defaultUserSort } from "@/tableSort/users";

const ROLES = ["ADMIN", "GESTOR", "CONSULTA"] as const;
type RoleName = (typeof ROLES)[number];

export function Users() {
  const canManageUsers = usePermission("users.manage");
  const [items, setItems] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleted, setShowDeleted] = useState(false);
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
  const [editPerms, setEditPerms] = useState<Set<string>>(new Set());
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
      const data = await listUsers({ include_deleted: showDeleted });
      setItems(data);
    } catch (e) {
      if (isAxiosError(e) && e.response?.status === 403) {
        setError("Sem permissão para listar usuários.");
      } else {
        setError("Erro ao listar usuários.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [showDeleted]);

  function statusBadge(u: UserRow): { label: string; cls: string } {
    if (u.deleted_at) return { label: "Removido", cls: "bg-red-100 text-red-900 ring-red-200" };
    if (!u.is_active) return { label: "Inativo", cls: "bg-amber-100 text-amber-900 ring-amber-200" };
    return { label: "Ativo", cls: "bg-emerald-100 text-emerald-900 ring-emerald-200" };
  }

  async function toggleActive(u: UserRow, next: boolean) {
    if (!canManageUsers) return;
    setError(null);
    try {
      const updated = next ? await activateUser(u.id) : await deactivateUser(u.id);
      setItems((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível atualizar status.");
    }
  }

  async function handleSoftDelete(u: UserRow) {
    if (!canManageUsers) return;
    if (!window.confirm("Deseja realmente remover este usuário?")) return;
    setError(null);
    try {
      await softDeleteUser(u.id);
      setItems((prev) => prev.filter((x) => x.id !== u.id));
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível remover.");
    }
  }

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

  function toggleEditPerm(code: string) {
    setEditPerms((prev) => {
      const n = new Set(prev);
      if (n.has(code)) n.delete(code);
      else n.add(code);
      return n;
    });
  }

  function openEdit(u: UserRow) {
    setEditing(u);
    const r = (u.role_names?.[0] as RoleName) || "CONSULTA";
    const rn = ROLES.includes(r) ? r : "CONSULTA";
    setEditRole(rn);
    setEditProjectIds(new Set(u.project_ids || []));
    const perms =
      u.permission_names?.length > 0 ? u.permission_names : [...ROLE_PERMISSION_PRESET[rn]];
    setEditPerms(new Set(perms));
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
        project_ids: Array.from(projectIds),
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
      await patchUser(editing.id, {
        role_name: editRole,
        project_ids: Array.from(editProjectIds),
        permission_names: Array.from(editPerms),
      });
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

  const { sortedRows, headerSort } = useTableSort(items, USER_SORT_COLUMNS, {
    defaultCompare: defaultUserSort,
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Usuários</h2>
          <p className="text-sm text-slate-500">Perfis, permissões e escopo por projetos vinculados</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="mr-2 flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={showDeleted}
              onChange={(e) => setShowDeleted(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Mostrar removidos
          </label>
          <button
            type="button"
            disabled={!canManageUsers}
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
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
            className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-200 bg-white p-6 shadow-lg"
          >
            <h3 className="text-lg font-semibold text-slate-900">Editar usuário</h3>
            <p className="mt-1 text-sm text-slate-500">
              {editing.full_name} ({editing.email})
            </p>
            <form onSubmit={handleSaveEdit} className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-sm text-slate-600">Perfil (preset)</label>
                <select
                  value={editRole}
                  disabled={!canManageUsers}
                  onChange={(e) => {
                    const r = e.target.value as RoleName;
                    setEditRole(r);
                    setEditPerms(new Set(ROLE_PERMISSION_PRESET[r]));
                  }}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-60"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-slate-500">
                  Ao mudar o perfil, as permissões são preenchidas com o padrão; ajuste os itens abaixo se
                  necessário.
                </p>
              </div>
              <div>
                  <p className="mb-2 text-sm font-medium text-slate-700">Projetos vinculados (escopo de dados)</p>
                  <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-slate-100 p-3">
                    {allProjects.length === 0 ? (
                      <p className="text-sm text-slate-500">Nenhum projeto listado.</p>
                    ) : (
                      allProjects.map((p) => (
                        <label key={p.id} className="flex cursor-pointer items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            disabled={!canManageUsers}
                            checked={editProjectIds.has(p.id)}
                            onChange={() => toggleEditProject(p.id)}
                          />
                          <span>{p.name}</span>
                        </label>
                      ))
                    )}
                  </div>
                </div>
              <div>
                <p className="mb-2 text-sm font-medium text-slate-700">Permissões</p>
                <div className="max-h-64 space-y-2 overflow-y-auto rounded-lg border border-slate-100 p-3">
                  {ALL_PERMISSION_CODES.map((code) => (
                    <label key={code} className="flex cursor-pointer items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        disabled={!canManageUsers}
                        checked={editPerms.has(code)}
                        onChange={() => toggleEditPerm(code)}
                      />
                      <span>
                        <span className="font-mono text-xs text-slate-500">{code}</span>
                        <span className="ml-2 text-slate-700">
                          {PERMISSION_LABELS[code] ?? code}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
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
                  disabled={savingEdit || !canManageUsers}
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
                  disabled={resetting || resetPassword.length < 6 || !canManageUsers}
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
            <label className="mb-1 block text-sm text-slate-600">Perfil inicial</label>
            <select
              value={roleName}
              disabled={!canManageUsers}
              onChange={(e) => setRoleName(e.target.value as RoleName)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-60"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-slate-500">
              As permissões são definidas automaticamente pelo perfil; edite o usuário depois para ajustar.
            </p>
          </div>
          <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Projetos vinculados (escopo de dados)</p>
              <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-slate-100 p-3">
                {allProjects.length === 0 ? (
                  <p className="text-sm text-slate-500">Nenhum projeto listado.</p>
                ) : (
                  allProjects.map((p) => (
                    <label key={p.id} className="flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        disabled={!canManageUsers}
                        checked={projectIds.has(p.id)}
                        onChange={() => toggleCreateProject(p.id)}
                      />
                      <span>{p.name}</span>
                    </label>
                  ))
                )}
              </div>
            </div>
          {roleName === "CONSULTA" && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Preset: acesso majoritariamente leitura.</p>
          )}
          <button
            type="submit"
            disabled={creating || !canManageUsers}
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
                <SortableTh label="Nome" column="name" variant="standard" {...headerSort} />
                <SortableTh label="Email" column="email" variant="standard" {...headerSort} />
                <SortableTh label="Perfil" column="role" variant="standard" {...headerSort} />
                <SortableTh label="Permissões" column="permissions" variant="standard" {...headerSort} />
                <SortableTh label="Projetos" column="projects" variant="standard" {...headerSort} />
                <SortableTh label="Ativo" column="active" variant="standard" {...headerSort} />
                <th className="px-4 py-3 font-medium text-slate-600 w-44" />
              </tr>
            </thead>
            <tbody>
              {sortedRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                    Nenhum usuário ou sem permissão para listar.
                  </td>
                </tr>
              ) : (
                sortedRows.map((u) => {
                  const primaryRole = u.role_names?.[0] || "—";
                  const nPerms = u.permission_names?.length ?? 0;
                  const st = statusBadge(u);
                  return (
                    <tr key={u.id} className="border-b border-slate-50 last:border-0">
                      <td className="px-4 py-3 font-medium text-slate-900">{u.full_name}</td>
                      <td className="px-4 py-3 text-slate-600">{u.email}</td>
                      <td className="px-4 py-3 text-slate-600">
                        <span className="inline-flex flex-wrap items-center gap-1">
                          {primaryRole}
                          {primaryRole === "CONSULTA" && (
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">leitura</span>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{nPerms ? `${nPerms} permissões` : "—"}</td>
                      <td className="px-4 py-3 text-slate-600">
                        {u.project_ids?.length ? `${u.project_ids.length} vínculo(s)` : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${st.cls}`}>
                            {st.label}
                          </span>
                          {!u.deleted_at && (
                            <button
                              type="button"
                              disabled={!canManageUsers}
                              onClick={() => void toggleActive(u, !u.is_active)}
                              className={`relative inline-flex h-6 w-10 items-center rounded-full transition ${
                                u.is_active ? "bg-emerald-600" : "bg-slate-300"
                              } disabled:opacity-60`}
                              title={!canManageUsers ? "Sem permissão." : undefined}
                            >
                              <span
                                className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
                                  u.is_active ? "translate-x-5" : "translate-x-1"
                                }`}
                              />
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={!canManageUsers}
                          onClick={() => openEdit(u)}
                          className="text-sm font-medium text-slate-700 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          disabled={!canManageUsers}
                          onClick={() => {
                            setResetFor(u);
                            setResetPassword("");
                            setError(null);
                          }}
                          className="text-sm font-medium text-indigo-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Resetar senha
                        </button>
                        {!u.deleted_at && (
                          <button
                            type="button"
                            disabled={!canManageUsers}
                            onClick={() => void handleSoftDelete(u)}
                            className="text-sm font-medium text-red-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Excluir
                          </button>
                        )}
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
