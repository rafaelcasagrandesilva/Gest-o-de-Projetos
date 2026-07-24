import { useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  createRole,
  deleteRole,
  listRoles,
  updateRole,
  type RoleRow,
} from "@/services/users";
import { PermissionGrid } from "@/components/PermissionGrid";

const ADMIN_NAME = "ADMIN";

/** Permissão que caracteriza um perfil ADMINISTRATIVO (acesso administrativo do sistema).
 *  A lógica de alto risco na exclusão baseia-se NELA — não no nome do perfil — para
 *  continuar válida se o ADMIN for renomeado ou se outros perfis administrativos existirem. */
const SYSTEM_ADMIN_PERM = "system.admin";

/** Frase fixa de confirmação para exclusão de perfil administrativo (NÃO usa o nome do perfil,
 *  para permanecer válida se o ADMIN for renomeado). Comparação case-insensitive. */
const DELETE_CONFIRM_PHRASE = "EXCLUIR";

function roleHasSystemAdmin(r: RoleRow): boolean {
  return r.permission_names.includes(SYSTEM_ADMIN_PERM);
}

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
  // Exclusão de alto risco (perfil com system.admin): perfil-alvo e texto de confirmação digitado.
  const [dangerDelete, setDangerDelete] = useState<RoleRow | null>(null);
  const [confirmText, setConfirmText] = useState("");

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

  function requestDelete(r: RoleRow) {
    // Trava única de exclusão: só com 0 usuários vinculados (inclusive perfis de sistema).
    if (!canManage || r.user_count > 0) return;
    // Perfil ADMINISTRATIVO (tem system.admin): confirmação de alto risco (modal + digitar o nome).
    if (roleHasSystemAdmin(r)) {
      setConfirmText("");
      setDangerDelete(r);
      return;
    }
    // Perfil comum: confirmação padrão.
    if (!window.confirm(`Excluir o perfil "${r.name}"?`)) return;
    void performDelete(r);
  }

  async function performDelete(r: RoleRow) {
    setError(null);
    try {
      await deleteRole(r.id);
      setDangerDelete(null);
      setConfirmText("");
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
                      disabled={!canManage || r.user_count > 0}
                      onClick={() => requestDelete(r)}
                      title={r.user_count > 0 ? "Possui usuários vinculados" : roleHasSystemAdmin(r) ? "Perfil administrativo — exige confirmação reforçada" : undefined}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2 sm:p-4">
          <div
            role="dialog"
            aria-modal="true"
            className="flex h-[95vh] w-[95vw] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg"
          >
            <form onSubmit={handleSave} className="flex h-full min-h-0 flex-col">
              {/* Cabeçalho fixo */}
              <div className="shrink-0 border-b border-slate-100 px-6 py-4">
                <div className="flex items-center justify-between gap-4">
                  <h3 className="text-lg font-semibold text-slate-900">
                    {form.id === null ? "Novo perfil" : `Editar perfil${form.is_system ? " (sistema)" : ""}`}
                  </h3>
                  {form.id !== null && canManage && (
                    <button
                      type="button"
                      onClick={() => setForm((f) => (f ? { ...f, id: null, is_system: false, name: `${f.name} (cópia)`, base_role_id: null } : f))}
                      className="shrink-0 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
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
              </div>

              {/* Miolo: campos (fixos) + grade (rola nos dois eixos) */}
              <div className="flex min-h-0 flex-1 flex-col gap-4 px-6 py-4">
                <div className="shrink-0 space-y-4">
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

                  <p className="text-sm font-medium text-slate-700">
                    Permissões {permsReadOnly && <span className="text-xs font-normal text-slate-400">(somente leitura)</span>}
                  </p>
                </div>

                <div className="min-h-0 flex-1">
                  <PermissionGrid selected={form.perms} onToggle={togglePerm} disabled={permsReadOnly} />
                </div>
              </div>

              {/* Rodapé fixo */}
              <div className="flex shrink-0 justify-end gap-2 border-t border-slate-100 px-6 py-3">
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

      {dangerDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-100 text-xl font-bold text-red-700">
                !
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-900">
                  Excluir perfil administrativo — ação de alto risco
                </h3>
                <p className="mt-1 text-sm text-slate-600">
                  O perfil <strong>{dangerDelete.name}</strong> possui a permissão{" "}
                  <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">system.admin</code> (acesso administrativo
                  do sistema). Esta exclusão é <strong>irreversível</strong> e remove o agrupamento de permissões deste
                  perfil.
                </p>
              </div>
            </div>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
              <li>Só é possível excluir com <strong>0 usuários vinculados</strong> (realoque-os antes).</li>
              <li>
                Se o sistema for reiniciado e <strong>nenhum</strong> perfil administrativo existir, o bootstrap recria
                automaticamente um perfil <strong>ADMIN padrão</strong> e um usuário administrador padrão — cuja senha
                deve ser redefinida imediatamente.
              </li>
              <li>A ação fica registrada na auditoria (quem excluiu, quando e qual perfil).</li>
            </ul>
            <label htmlFor="danger-confirm" className="mt-4 block text-sm font-medium text-slate-700">
              Para confirmar, digite{" "}
              <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">{DELETE_CONFIRM_PHRASE}</code>
            </label>
            <input
              id="danger-confirm"
              autoFocus
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={DELETE_CONFIRM_PHRASE}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-red-400 focus:outline-none"
            />
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setDangerDelete(null);
                  setConfirmText("");
                }}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={confirmText.trim().toUpperCase() !== DELETE_CONFIRM_PHRASE}
                onClick={() => void performDelete(dangerDelete)}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-40"
              >
                Excluir definitivamente
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
