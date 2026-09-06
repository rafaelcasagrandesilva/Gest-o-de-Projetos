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
  type PaymentVariableComponent,
  type VariableComponentItem,
} from "@/services/paymentVariableComponents";
import { uploadComponentAttachments } from "@/services/paymentComponentAttachments";
import {
  fetchPaymentComponentTypes,
  type PaymentComponentType,
} from "@/services/paymentComponentTypes";
import {
  VariableComponentsList,
  emptyComponentRow,
  rowFromComponent,
  type ComponentRow,
} from "@/components/project/VariableComponentsList";

export interface VariablePaymentComponentsHandle {
  /** Persiste o conjunto atual (chamado pelo "Salvar custos do mês"). */
  persist: () => Promise<void>;
}

/** Linhas que viram lançamento — a ordem é a MESMA enviada e devolvida pelo backend. */
export function validComponentRows(rows: ComponentRow[]): ComponentRow[] {
  return rows.filter((row) => {
    const amount = Number(row.amount);
    return Boolean(row.typeId) && Number.isFinite(amount) && amount > 0;
  });
}

/** Constrói os itens do payload a partir das linhas (descarta linhas inválidas). */
export function rowsToItems(rows: ComponentRow[]): VariableComponentItem[] {
  return validComponentRows(rows).map((row) => ({
    ...(row.id ? { id: row.id } : {}),
    type_id: row.typeId,
    amount: Number(row.amount),
    note: row.note.trim() || null,
  }));
}

/**
 * Salva os lançamentos e, em seguida, sobe os comprovantes que estavam na fila das linhas
 * novas — só depois do salvamento existe o id ao qual o arquivo se prende.
 *
 * O casamento é POSICIONAL e seguro: `validComponentRows` e o backend percorrem a mesma
 * lista na mesma ordem, então `saved[i]` é o lançamento de `enviadas[i]`.
 *
 * A falha do upload NÃO desfaz o salvamento (o lançamento é o dado financeiro; o
 * comprovante é anexo): devolve as linhas já salvas + a mensagem, para o usuário reenviar
 * o arquivo sem redigitar nada.
 */
export async function persistRowsWithAttachments(
  rows: ComponentRow[],
  save: (items: VariableComponentItem[]) => Promise<PaymentVariableComponent[]>,
): Promise<{ rows: ComponentRow[]; attachmentError: string | null }> {
  const enviadas = validComponentRows(rows);
  const saved = await save(rowsToItems(rows));

  let attachmentError: string | null = null;
  const next = await Promise.all(
    saved.map(async (component, i) => {
      const row = rowFromComponent(component);
      const pending = enviadas[i]?.pendingFiles ?? [];
      if (pending.length === 0) return row;
      try {
        const uploaded = await uploadComponentAttachments(component.id, pending);
        return { ...row, attachmentCount: row.attachmentCount + uploaded.length };
      } catch {
        attachmentError =
          "Os lançamentos foram salvos, mas houve falha ao enviar algum comprovante. Abra o clipe da linha e reenvie.";
        return row;
      }
    }),
  );
  return { rows: next, attachmentError };
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
      setRows(components.map(rowFromComponent));
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
    setRows((r) => [...r, emptyComponentRow(firstActive?.id ?? "")]);
  }

  useImperativeHandle(
    ref,
    () => ({
      async persist() {
        const { rows: next, attachmentError } = await persistRowsWithAttachments(
          rowsRef.current,
          (items) => replaceProjectLaborComponents(laborId, items),
        );
        setRows(next);
        setError(attachmentError);
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
          As alterações são gravadas ao clicar em <strong>Salvar custos do mês</strong> — inclusive
          os comprovantes anexados numa linha nova.
        </p>
      )}
    </div>
  );
});
