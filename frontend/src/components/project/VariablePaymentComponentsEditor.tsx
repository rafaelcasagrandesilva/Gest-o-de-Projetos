import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import {
  fetchProjectLaborComponents,
  replaceProjectLaborComponents,
  type VariableComponentItem,
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

export interface VariablePaymentComponentsHandle {
  /** Persiste o conjunto atual (chamado pelo "Salvar custos do mês"). */
  persist: () => Promise<void>;
}

/** Constrói os itens do payload a partir das linhas (descarta linhas inválidas). */
export function rowsToItems(rows: ComponentRow[]): VariableComponentItem[] {
  return rows
    .map((row) => {
      const amount = Number(row.amount);
      if (!row.typeId || !Number.isFinite(amount) || amount <= 0) return null;
      return {
        ...(row.id ? { id: row.id } : {}),
        type_id: row.typeId,
        amount,
        note: row.note.trim() || null,
      } as VariableComponentItem;
    })
    .filter((x): x is VariableComponentItem => x !== null);
}

export const VariablePaymentComponentsEditor = forwardRef<
  VariablePaymentComponentsHandle,
  { laborId: string; readOnly?: boolean }
>(function VariablePaymentComponentsEditor({ laborId, readOnly = false }, ref) {
  const [types, setTypes] = useState<PaymentComponentType[]>([]);
  const [rows, setRows] = useState<ComponentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [typeList, components] = await Promise.all([
        fetchPaymentComponentTypes(false),
        fetchProjectLaborComponents(laborId),
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
      setError("Não foi possível carregar os componentes variáveis.");
    } finally {
      setLoading(false);
    }
  }, [laborId]);

  useEffect(() => {
    void load();
  }, [load]);

  const firstActive = types.filter((t) => t.is_active).sort((a, b) => a.display_order - b.display_order)[0];

  function addRow() {
    setRows((r) => [
      ...r,
      { key: nextComponentRowKey(), id: null, typeId: firstActive?.id ?? "", amount: "", note: "" },
    ]);
  }

  useImperativeHandle(
    ref,
    () => ({
      async persist() {
        const saved = await replaceProjectLaborComponents(laborId, rowsToItems(rowsRef.current));
        setRows(
          saved.map((c) => ({
            key: nextComponentRowKey(),
            id: c.id,
            typeId: c.type_id,
            amount: String(c.amount),
            note: c.note ?? "",
          })),
        );
      },
    }),
    [laborId],
  );

  return (
    <div className="mt-4 rounded-lg border border-emerald-100 bg-emerald-50/40 p-3">
      {error && <p className="mb-2 text-xs text-red-700">{error}</p>}
      {loading ? (
        <p className="text-xs text-slate-500">Carregando…</p>
      ) : (
        <VariableComponentsList
          rows={rows}
          types={types}
          readOnly={readOnly}
          onAdd={addRow}
          onUpdate={(key, patch) => setRows((r) => r.map((x) => (x.key === key ? { ...x, ...patch } : x)))}
          onRemove={(key) => setRows((r) => r.filter((x) => x.key !== key))}
        />
      )}
      {!readOnly && !loading && (
        <p className="mt-2 text-[11px] text-slate-500">
          As alterações são gravadas ao clicar em <strong>Salvar custos do mês</strong>.
        </p>
      )}
    </div>
  );
});
