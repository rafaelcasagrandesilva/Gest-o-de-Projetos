import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import {
  createAdvanceInstitution,
  deleteAdvanceInstitution,
  fetchAdvanceInstitutions,
  updateAdvanceInstitution,
  OPERATION_PROFILE_OPTIONS,
  type AdvanceInstitution,
  type OperationProfile,
} from "@/services/advanceInstitutions";
import { formatApiError } from "@/utils/apiError";
import { usePermission } from "@/hooks/usePermission";

const INSTITUTION_TYPES = ["FIDC", "BANCO", "FACTORING", "OUTROS"];

function emptyForm() {
  return {
    name: "",
    institution_type: "FIDC",
    operation_profile: "LEPTA" as OperationProfile,
    is_active: true,
  };
}

export function AdvanceInstitutions() {
  const canEdit = usePermission("invoices.update");
  const [rows, setRows] = useState<AdvanceInstitution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await fetchAdvanceInstitutions());
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar instituições.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!canEdit || !form.name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createAdvanceInstitution({
        name: form.name.trim(),
        institution_type: form.institution_type,
        operation_profile: form.operation_profile,
        is_active: form.is_active,
      });
      setForm(emptyForm());
      setShowForm(false);
      await load();
    } catch (err) {
      setError(isAxiosError(err) ? formatApiError(err) : "Não foi possível criar a instituição.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(inst: AdvanceInstitution) {
    if (!canEdit) return;
    setBusyId(inst.id);
    setError(null);
    try {
      await updateAdvanceInstitution(inst.id, { is_active: !inst.is_active });
      await load();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível atualizar.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(inst: AdvanceInstitution) {
    if (!canEdit) return;
    if (!window.confirm(`Excluir a instituição ${inst.name}?`)) return;
    setBusyId(inst.id);
    setError(null);
    try {
      await deleteAdvanceInstitution(inst.id);
      await load();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível excluir.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Instituições de Antecipação</h1>
          <p className="mt-1 text-sm text-slate-600">
            Instituições financeiras usadas nas operações de antecipação. O perfil de operação define
            automaticamente o fluxo (telas e regras) aplicado na criação da operação.
          </p>
        </div>
        <button
          type="button"
          disabled={!canEdit}
          onClick={() => setShowForm((s) => !s)}
          className="shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {showForm ? "Fechar" : "+ Nova instituição"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {showForm && canEdit && (
        <form
          onSubmit={handleCreate}
          className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50/80 p-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          <label className="flex flex-col gap-1 text-sm lg:col-span-2">
            <span className="font-medium text-slate-700">Nome *</span>
            <input
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Tipo</span>
            <select
              value={form.institution_type}
              onChange={(e) => setForm((f) => ({ ...f, institution_type: e.target.value }))}
              className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            >
              {INSTITUTION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Perfil de operação *</span>
            <select
              value={form.operation_profile}
              onChange={(e) => setForm((f) => ({ ...f, operation_profile: e.target.value as OperationProfile }))}
              className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            >
              {OPERATION_PROFILE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm lg:col-span-4">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              className="h-4 w-4 rounded border-slate-300"
            />
            <span className="text-slate-700">Ativa</span>
          </label>
          <div className="lg:col-span-4">
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Salvando…" : "Cadastrar instituição"}
            </button>
          </div>
        </form>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[640px] w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-3">Nome</th>
              <th className="px-3 py-3">Tipo</th>
              <th className="px-3 py-3">Perfil de operação</th>
              <th className="px-3 py-3">Situação</th>
              <th className="px-3 py-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  Carregando…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  Nenhuma instituição cadastrada.
                </td>
              </tr>
            ) : (
              rows.map((inst) => (
                <tr key={inst.id} className={`hover:bg-slate-50/80 ${inst.is_active ? "" : "opacity-60"}`}>
                  <td className="px-3 py-2 font-medium text-slate-900">{inst.name}</td>
                  <td className="px-3 py-2 text-slate-700">{inst.institution_type}</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700 ring-1 ring-slate-200">
                      {inst.operation_profile}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${
                        inst.is_active
                          ? "bg-emerald-100 text-emerald-900 ring-emerald-200"
                          : "bg-slate-200 text-slate-700 ring-slate-300"
                      }`}
                    >
                      {inst.is_active ? "Ativa" : "Inativa"}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    <button
                      type="button"
                      disabled={!canEdit || busyId === inst.id}
                      onClick={() => void toggleActive(inst)}
                      className="mr-2 rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {inst.is_active ? "Desativar" : "Ativar"}
                    </button>
                    <button
                      type="button"
                      disabled={!canEdit || busyId === inst.id}
                      onClick={() => void handleDelete(inst)}
                      className="text-xs font-medium text-red-700 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Excluir
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
