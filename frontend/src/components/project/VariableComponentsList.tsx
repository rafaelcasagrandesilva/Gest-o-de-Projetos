import { useMemo } from "react";
import type { PaymentComponentType } from "@/services/paymentComponentTypes";

/** Linha em edição (sem id = novo lançamento). */
export type ComponentRow = {
  key: string;
  id: string | null;
  typeId: string;
  amount: string;
  note: string;
};

let _seq = 0;
export const nextComponentRowKey = () => `pvc_${++_seq}`;

/**
 * Lista visual (presentacional) de Componentes Variáveis de Pagamento — layout ÚNICO,
 * compartilhado entre a tela de Projetos (F3, inline) e o modal de Custo Fixo (F4).
 * Sem carregamento/persistência: recebe rows/types e emite eventos.
 */
export function VariableComponentsList({
  rows,
  types,
  readOnly = false,
  onAdd,
  onUpdate,
  onRemove,
}: {
  rows: ComponentRow[];
  types: PaymentComponentType[];
  readOnly?: boolean;
  onAdd: () => void;
  onUpdate: (key: string, patch: Partial<ComponentRow>) => void;
  onRemove: (key: string) => void;
}) {
  const activeTypes = useMemo(
    () =>
      types
        .filter((t) => t.is_active)
        .sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name)),
    [types],
  );

  /** Opções do dropdown de uma linha: ativos (por ordem) + o tipo atual mesmo inativo. */
  function optionsFor(row: ComponentRow): PaymentComponentType[] {
    const opts = [...activeTypes];
    if (row.typeId && !opts.some((t) => t.id === row.typeId)) {
      const inactive = types.find((t) => t.id === row.typeId);
      if (inactive) opts.push(inactive);
    }
    return opts;
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-emerald-900">Componentes Variáveis de Pagamento</p>
        {!readOnly && (
          <button
            type="button"
            onClick={onAdd}
            disabled={activeTypes.length === 0}
            className="rounded border border-emerald-300 bg-white px-2 py-0.5 text-xs font-medium text-emerald-800 hover:bg-emerald-50 disabled:opacity-50"
          >
            + Adicionar componente
          </button>
        )}
      </div>

      {rows.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">Nenhum componente variável lançado neste mês.</p>
      ) : (
        <div className="mt-2 space-y-2">
          {rows.map((row) => (
            <div key={row.key} className="flex flex-wrap items-center gap-2">
              <select
                value={row.typeId}
                disabled={readOnly}
                onChange={(e) => onUpdate(row.key, { typeId: e.target.value })}
                className="min-w-[9rem] flex-1 rounded border border-slate-200 px-2 py-1 text-sm"
              >
                {optionsFor(row).map((t) => (
                  <option key={t.id} value={t.id} disabled={!t.is_active}>
                    {t.name}
                    {!t.is_active ? " (inativo)" : ""}
                  </option>
                ))}
              </select>
              <input
                type="number"
                step="0.01"
                min={0}
                value={row.amount}
                disabled={readOnly}
                onChange={(e) => onUpdate(row.key, { amount: e.target.value })}
                placeholder="Valor"
                className="w-24 rounded border border-slate-200 px-2 py-1 text-sm"
              />
              <input
                type="text"
                value={row.note}
                disabled={readOnly}
                onChange={(e) => onUpdate(row.key, { note: e.target.value })}
                placeholder="Observação (opcional)"
                className="min-w-[8rem] flex-1 rounded border border-slate-200 px-2 py-1 text-sm"
              />
              {!readOnly && (
                <button
                  type="button"
                  onClick={() => onRemove(row.key)}
                  className="rounded px-1.5 py-1 text-xs text-red-700 hover:bg-red-50"
                  title="Remover componente"
                >
                  Remover
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
