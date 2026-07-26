import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import {
  createPaymentComponentType,
  deletePaymentComponentType,
  fetchPaymentComponentTypes,
  updatePaymentComponentType,
  type PaymentComponentType,
  type PaymentComponentTypeUpsert,
} from "@/services/paymentComponentTypes";

/** Deriva um código interno sugerido a partir do nome (enquanto o usuário digita o nome). */
function slugify(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

type Draft = { id: string | null } & PaymentComponentTypeUpsert;

const EMPTY_DRAFT: Draft = {
  id: null,
  name: "",
  code: "",
  description: "",
  is_active: true,
  display_order: 0,
};

export function PaymentComponentTypesSettings({ canEdit }: { canEdit: boolean }) {
  const [rows, setRows] = useState<PaymentComponentType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [codeTouched, setCodeTouched] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await fetchPaymentComponentTypes(false));
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível carregar os tipos.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function openNew() {
    setCodeTouched(false);
    setDraft({ ...EMPTY_DRAFT, display_order: (rows.at(-1)?.display_order ?? 0) + 1 });
  }

  function openEdit(row: PaymentComponentType) {
    setCodeTouched(true);
    setDraft({
      id: row.id,
      name: row.name,
      code: row.code,
      description: row.description ?? "",
      is_active: row.is_active,
      display_order: row.display_order,
    });
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const payload: PaymentComponentTypeUpsert = {
        name: draft.name,
        code: draft.code,
        description: (draft.description ?? "").trim() || null,
        is_active: draft.is_active,
        display_order: draft.display_order,
      };
      if (draft.id) await updatePaymentComponentType(draft.id, payload);
      else await createPaymentComponentType(payload);
      setDraft(null);
      await load();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar o tipo.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(row: PaymentComponentType) {
    setError(null);
    try {
      await updatePaymentComponentType(row.id, { is_active: !row.is_active });
      await load();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível alterar o status.");
    }
  }

  async function remove(row: PaymentComponentType) {
    if (!window.confirm(`Excluir o tipo "${row.name}"? Só é permitido para tipos sem utilização.`)) return;
    setError(null);
    try {
      await deletePaymentComponentType(row.id);
      await load();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível excluir o tipo.");
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Tipos de Componentes Variáveis</h3>
          <p className="mt-1 text-xs text-slate-500">
            Tipos de pagamento variável (Ajuda de custo, Reembolso, Diária…) usados em Projetos e
            Custo Fixo. Novos tipos aparecem automaticamente nas telas de lançamento, no Contas a
            Pagar e no Relatório de Folha. Tipos já utilizados não podem ser excluídos — apenas
            inativados, preservando o histórico.
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            onClick={openNew}
            className="shrink-0 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
          >
            + Novo tipo
          </button>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
              <th className="py-2 pr-3">Nome</th>
              <th className="py-2 pr-3">Código interno</th>
              <th className="py-2 pr-3 text-center">Ativo</th>
              <th className="py-2 pr-3 text-right">Ordem</th>
              <th className="py-2 pr-3 text-right">Utilizações</th>
              <th className="py-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="py-4 text-center text-xs text-slate-400">
                  Carregando…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-4 text-center text-xs text-slate-400">
                  Nenhum tipo cadastrado.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-medium text-slate-800">{r.name}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-slate-500">{r.code}</td>
                  <td className="py-2 pr-3 text-center">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${
                        r.is_active
                          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                          : "bg-slate-100 text-slate-500 ring-1 ring-slate-200"
                      }`}
                    >
                      {r.is_active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums text-slate-600">{r.display_order}</td>
                  <td className="py-2 pr-3 text-right tabular-nums text-slate-600">{r.usage_count}</td>
                  <td className="py-2 text-right">
                    {canEdit && (
                      <span className="inline-flex gap-1.5">
                        <button
                          type="button"
                          onClick={() => openEdit(r)}
                          className="rounded border border-slate-200 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-50"
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          onClick={() => void toggleActive(r)}
                          className="rounded border border-slate-200 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-50"
                        >
                          {r.is_active ? "Inativar" : "Ativar"}
                        </button>
                        <button
                          type="button"
                          disabled={r.usage_count > 0}
                          title={r.usage_count > 0 ? "Tipo em uso: inative em vez de excluir." : undefined}
                          onClick={() => void remove(r)}
                          className="rounded border border-red-200 px-2 py-0.5 text-xs text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          Excluir
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {draft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h4 className="text-sm font-semibold text-slate-800">
              {draft.id ? "Editar tipo" : "Novo tipo de componente"}
            </h4>
            <div className="mt-4 space-y-3">
              <label className="block text-xs text-slate-600">
                Nome
                <input
                  type="text"
                  value={draft.name ?? ""}
                  onChange={(e) => {
                    const name = e.target.value;
                    setDraft((d) =>
                      d ? { ...d, name, code: codeTouched ? d.code : slugify(name) } : d,
                    );
                  }}
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                  placeholder="Ex.: Vale Combustível"
                />
              </label>
              <label className="block text-xs text-slate-600">
                Código interno
                <input
                  type="text"
                  value={draft.code ?? ""}
                  onChange={(e) => {
                    setCodeTouched(true);
                    setDraft((d) => (d ? { ...d, code: e.target.value } : d));
                  }}
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-sm"
                  placeholder="vale_combustivel"
                />
                <span className="mt-1 block text-[11px] text-slate-400">
                  Minúsculas, números e underscore. Estável — não muda ao renomear.
                </span>
              </label>
              <label className="block text-xs text-slate-600">
                Descrição (opcional)
                <textarea
                  rows={2}
                  value={draft.description ?? ""}
                  onChange={(e) => setDraft((d) => (d ? { ...d, description: e.target.value } : d))}
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                />
              </label>
              <div className="flex gap-3">
                <label className="block flex-1 text-xs text-slate-600">
                  Ordem
                  <input
                    type="number"
                    min={0}
                    value={draft.display_order ?? 0}
                    onChange={(e) =>
                      setDraft((d) => (d ? { ...d, display_order: Number(e.target.value) } : d))
                    }
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                  />
                </label>
                <label className="mt-5 flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={draft.is_active ?? true}
                    onChange={(e) => setDraft((d) => (d ? { ...d, is_active: e.target.checked } : d))}
                    className="h-4 w-4 rounded border-slate-300"
                  />
                  Ativo
                </label>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={saving}
                onClick={() => setDraft(null)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={saving || !(draft.name ?? "").trim() || !(draft.code ?? "").trim()}
                onClick={() => void save()}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Salvando…" : "Salvar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
