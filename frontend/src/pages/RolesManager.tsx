import { useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  createRole,
  deleteRole,
  listRoles,
  updateRole,
  type RoleRow,
} from "@/services/users";
import { ALL_PERMISSION_CODES, PERMISSION_LABELS } from "@/permissions";

const ADMIN_NAME = "ADMIN";

type FormState = {
  id: string | null; // null = criação
  name: string;
  description: string;
  is_active: boolean;
  is_system: boolean;
  perms: Set<string>;
  base_role_id: string | null; // só na criação (duplicação)
};

function emptyForm(): FormState {
  return { id: null, name: "", description: "", is_active: true, is_system: false, perms: new Set(), base_role_id: null };
}

function formFromRole(r: RoleRow, { asCopy = false }: { asCopy?: boolean } = {}): FormState {
  return {
    id: asCopy ? null : r.id,
    name: asCopy ? `${r.name} (cópia)` : r.name,
    description: r.description ?? "",
    is_active: r.is_active,
    is_system: asCopy ? false : r.is_system,
    perms: new Set(r.permission_names),
    base_role_id: null,
  };
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}

export function RolesManager({ canManage }: { canManage: boolean }) {
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);

  const isAdminForm = form?.name.trim().toUpperCase() === ADMIN_NAME && form?.is_system;
  const permsReadOnly = !canManage || Boolean(isAdminForm);

  async function load() {
    setError(null);
    try {
      setRoles(await listRoles());
    } catch (e) {
      setError(isAxiosError(e) && e.response?.status === 403 ? "Sem permissão." : "Erro ao listar perfis.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function togglePerm(code: string) {
    if (permsReadOnly) return;
    setForm((f) => {
      if (!f) return f;
      const n = new Set(f.perms);
      if (n.has(code)) n.delete(code);
      else n.add(code);
      return { ...f, perms: n };
    });
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    setError(null);
    try {
      if (form.id === null) {
        await createRole({
          name: form.name.trim(),
          description: form.description.trim() || null,
          is_active: form.is_active,
          permission_names: Array.from(form.perms),
          base_role_id: form.base_role_id,
        });
      } else if (isAdminForm) {
        // ADMIN: nunca envia permissões (somente leitura). Só descrição pode mudar.
        await updateRole(form.id, { description: form.description.trim() || null });
      } else {
        await updateRole(form.id, {
          ...(form.is_system ? {} : { name: form.name.trim() }),
          description: form.description.trim() || null,
          is_active: form.is_active,
          permission_names: Array.from(form.perms),
        });
      }
      setForm(null);
      await load();
    } catch (err) {
      const d = isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof d === "string" ? d : "Não foi possível salvar o perfil.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(r: RoleRow) {
    if (!canManage || r.is_system || r.user_count > 0) return;
    if (!window.confirm(`Excluir o perfil "${r.name}"?`)) return;
    setError(null);
    try {
      await deleteRole(r.id);
      await load();
    } catch (err) {
      const d = isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof d === "string" ? d : "Não foi possível excluir o perfil.");
    }
  }

  const baseOptions = useMemo(() => roles.slice().sort((a, b) => a.name.localeCompare(b.name, "pt-BR")), [roles]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          Perfis agrupam permissões. Os usuários herdam as permissões do perfil (vínculo vivo) e podem ter
          ajustes individuais na tela de Usuários.
        </p>
        <button
          type="button"
          disabled={!canManage}
          onClick={() => setForm(emptyForm())}
          className="shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          + Novo perfil
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {loading ? (
        <div className="text-slate-500">Carregando…</div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/80">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-600">Nome</th>
                <th className="px-4 py-3 font-medium text-slate-600">Descrição</th>
                <th className="px-4 py-3 font-medium text-slate-600">Sistema?</th>
                <th className="px-4 py-3 font-medium text-slate-600">Ativo?</th>
                <th className="px-4 py-3 text-right font-medium text-slate-600">Usuários</th>
                <th className="px-4 py-3 font-medium text-slate-600">Última alteração</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {roles.map((r) => (
                <tr key={r.id} className="border-b border-slate-50 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-900">{r.name}</td>
                  <td className="px-4 py-3 text-slate-600">{r.description || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{r.is_system ? "Sim" : "Não"}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${
                      r.is_active ? "bg-emerald-100 text-emerald-900 ring-emerald-200" : "bg-amber-100 text-amber-900 ring-amber-200"
                    }`}>
                      {r.is_active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-700">{r.user_count}</td>
                  <td className="px-4 py-3 text-slate-500">{fmtDate(r.updated_at)}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button
                      type="button"
                      disabled={!canManage}
                      onClick={() => setForm(formFromRole(r))}
                      className="text-sm text-slate-700 hover:underline disabled:opacity-50"
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      disabled={!canManage || r.is_system || r.user_count > 0}
                      onClick={() => void handleDelete(r)}
                      title={r.is_system ? "Perfil de sistema" : r.user_count > 0 ? "Possui usuários vinculados" : undefined}
                      className="ml-3 text-sm text-red-600 hover:underline disabled:opacity-40"
                    >
                      Excluir
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {form && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div role="dialog" aria-modal="true" className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-200 bg-white p-6 shadow-lg">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-900">
                {form.id === null ? "Novo perfil" : `Editar perfil${form.is_system ? " (sistema)" : ""}`}
              </h3>
              {form.id !== null && canManage && (
                <button
                  type="button"
                  onClick={() => setForm((f) => (f ? { ...f, id: null, is_system: false, name: `${f.name} (cópia)`, base_role_id: null } : f))}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Duplicar
                </button>
              )}
            </div>
            {isAdminForm && (
              <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
                O perfil ADMIN tem acesso irrestrito; suas permissões são somente leitura.
              </p>
            )}
            <form onSubmit={handleSave} className="mt-4 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm text-slate-600">Nome</label>
                  <input
                    required
                    value={form.name}
                    disabled={!canManage || form.is_system}
                    onChange={(e) => setForm((f) => (f ? { ...f, name: e.target.value } : f))}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:bg-slate-50 disabled:opacity-70"
                  />
                  {form.is_system && <p className="mt-1 text-xs text-slate-400">Perfis de sistema não podem ser renomeados.</p>}
                </div>
                <div>
                  <label className="mb-1 block text-sm text-slate-600">Descrição</label>
                  <input
                    value={form.description}
                    disabled={!canManage}
                    onChange={(e) => setForm((f) => (f ? { ...f, description: e.target.value } : f))}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-6">
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    disabled={!canManage || form.is_system}
                    onChange={(e) => setForm((f) => (f ? { ...f, is_active: e.target.checked } : f))}
                  />
                  Ativo (perfil inativo não pode ser atribuído a novos usuários)
                </label>
                {form.id === null && (
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    Criar baseado em:
                    <select
                      value={form.base_role_id ?? ""}
                      onChange={(e) => {
                        const rid = e.target.value || null;
                        const base = roles.find((x) => x.id === rid);
                        setForm((f) => (f ? { ...f, base_role_id: rid, perms: base ? new Set(base.permission_names) : f.perms } : f));
                      }}
                      className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                    >
                      <option value="">(nenhum)</option>
                      {baseOptions.map((r) => (
                        <option key={r.id} value={r.id}>{r.name}</option>
                      ))}
                    </select>
                  </label>
                )}
              </div>

              <div>
                <p className="mb-2 text-sm font-medium text-slate-700">
                  Permissões {permsReadOnly && <span className="text-xs font-normal text-slate-400">(somente leitura)</span>}
                </p>
                <div className="max-h-64 space-y-2 overflow-y-auto rounded-lg border border-slate-100 p-3">
                  {ALL_PERMISSION_CODES.map((code) => (
                    <label key={code} className="flex cursor-pointer items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        disabled={permsReadOnly}
                        checked={form.perms.has(code)}
                        onChange={() => togglePerm(code)}
                      />
                      <span>
                        <span className="font-mono text-xs text-slate-500">{code}</span>
                        <span className="ml-2 text-slate-700">{PERMISSION_LABELS[code] ?? code}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setForm(null)} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                  Cancelar
                </button>
                <button type="submit" disabled={saving || !canManage} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60">
                  {saving ? "Salvando…" : "Salvar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
