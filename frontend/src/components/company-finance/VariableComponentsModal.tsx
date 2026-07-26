import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import {
  fetchCompanyItemComponents,
  replaceCompanyItemComponents,
} from "@/services/paymentVariableComponents";
import {
  fetchPaymentComponentTypes,
  type PaymentComponentType,
} from "@/services/paymentComponentTypes";
import {
  VariableComponentsList,
  nextComponentRowKey,
  type ComponentRow,
} from "@/components/project/VariableComponentsList";
import { rowsToItems } from "@/components/project/VariablePaymentComponentsEditor";

/**
 * Modal de Componentes Variáveis para Custo Fixo (F4). Mantém a grade mensal intacta:
 * é aberto por um botão discreto na linha do colaborador, opera sobre (item, competência)
 * e, ao salvar, chama `onSaved` para o pai atualizar o resumo imediatamente.
 */
export function VariableComponentsModal({
  itemId,
  itemLabel,
  competencia,
  competenciaLabel,
  readOnly = false,
  onClose,
  onSaved,
}: {
  itemId: string;
  itemLabel: string;
  competencia: string; // YYYY-MM-01
  competenciaLabel: string;
  readOnly?: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const [types, setTypes] = useState<PaymentComponentType[]>([]);
  const [rows, setRows] = useState<ComponentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const firstActive = types.filter((t) => t.is_active).sort((a, b) => a.display_order - b.display_order)[0];

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [typeList, components] = await Promise.all([
        fetchPaymentComponentTypes(false),
        fetchCompanyItemComponents(itemId, competencia),
      ]);
      setTypes(typeList);
      setRows(
        components.map((c) => ({
          key: nextComponentRowKey(),
          id: c.id,
          typeId: c.type_id,
          amount: String(c.amount),
          note: c.note ?? "",
        })),
      );
    } catch {
      setError("Não foi possível carregar os componentes.");
    } finally {
      setLoading(false);
    }
  }, [itemId, competencia]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await replaceCompanyItemComponents(itemId, competencia, rowsToItems(rows));
      await Promise.resolve(onSaved());
      onClose();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar os componentes.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-xl rounded-xl bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-slate-800">Componentes Variáveis de Pagamento</h4>
            <p className="mt-0.5 text-xs text-slate-500">
              {itemLabel} · competência {competenciaLabel}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Fechar"
          >
            ✕
          </button>
        </div>

        {error && <p className="mt-3 text-xs text-red-700">{error}</p>}

        <div className="mt-4 rounded-lg border border-emerald-100 bg-emerald-50/40 p-3">
          {loading ? (
            <p className="text-xs text-slate-500">Carregando…</p>
          ) : (
            <VariableComponentsList
              rows={rows}
              types={types}
              readOnly={readOnly}
              onAdd={() =>
                setRows((r) => [
                  ...r,
                  { key: nextComponentRowKey(), id: null, typeId: firstActive?.id ?? "", amount: "", note: "" },
                ])
              }
              onUpdate={(key, patch) =>
                setRows((r) => r.map((x) => (x.key === key ? { ...x, ...patch } : x)))
              }
              onRemove={(key) => setRows((r) => r.filter((x) => x.key !== key))}
            />
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            disabled={saving}
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {readOnly ? "Fechar" : "Cancelar"}
          </button>
          {!readOnly && (
            <button
              type="button"
              disabled={saving || loading}
              onClick={() => void save()}
              className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
            >
              {saving ? "Salvando…" : "Salvar componentes"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
