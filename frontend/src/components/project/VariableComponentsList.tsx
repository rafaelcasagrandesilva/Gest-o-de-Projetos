import { useMemo, useState } from "react";
import type { PaymentComponentType } from "@/services/paymentComponentTypes";
import { ComponentAttachmentsPanel } from "@/components/project/ComponentAttachmentsPanel";

/** Linha em edição (sem id = novo lançamento). */
export type ComponentRow = {
  key: string;
  id: string | null;
  typeId: string;
  amount: string;
  note: string;
  /** Comprovantes já gravados no servidor (só a contagem; a lista é buscada ao abrir). */
  attachmentCount: number;
  /** Arquivos escolhidos numa linha ainda não salva — sobem junto com o salvamento. */
  pendingFiles: File[];
};

let _seq = 0;
export const nextComponentRowKey = () => `pvc_${++_seq}`;

/** Linha nova, vazia — mantém o formato num lugar só (usado pelas duas telas). */
export function emptyComponentRow(typeId: string): ComponentRow {
  return {
    key: nextComponentRowKey(),
    id: null,
    typeId,
    amount: "",
    note: "",
    attachmentCount: 0,
    pendingFiles: [],
  };
}

/** Linha a partir do que veio da API (descarta a fila local: já foi enviada). */
export function rowFromComponent(c: {
  id: string;
  type_id: string;
  amount: number;
  note: string | null;
  attachment_count?: number;
}): ComponentRow {
  return {
    key: nextComponentRowKey(),
    id: c.id,
    typeId: c.type_id,
    amount: String(c.amount),
    note: c.note ?? "",
    attachmentCount: c.attachment_count ?? 0,
    pendingFiles: [],
  };
}

/**
 * Lista visual (presentacional) de Componentes Variáveis de Pagamento — layout ÚNICO,
 * compartilhado entre a tela de Projetos (F3, inline) e o modal de Custo Fixo (F4).
 * Sem carregamento/persistência: recebe rows/types e emite eventos.
 *
 * Comprovantes: cada linha tem um clipe com o número de anexos; o painel de arquivos abre
 * só na linha clicada (uma por vez). Assim a lista continua com uma linha por lançamento
 * mesmo para quem lança dezenas de reembolsos no mês.
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
  const [openKey, setOpenKey] = useState<string | null>(null);

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

  const attachmentsOf = (row: ComponentRow) => row.attachmentCount + row.pendingFiles.length;
  const semComprovante = rows.filter((r) => attachmentsOf(r) === 0).length;

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
          {rows.map((row) => {
            const count = attachmentsOf(row);
            const open = openKey === row.key;
            return (
              <div key={row.key}>
                <div className="flex flex-wrap items-center gap-2">
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
                  <button
                    type="button"
                    onClick={() => setOpenKey(open ? null : row.key)}
                    aria-expanded={open}
                    title={
                      count === 0
                        ? "Sem comprovante anexado"
                        : `${count} comprovante${count > 1 ? "s" : ""}`
                    }
                    className={`shrink-0 rounded border px-1.5 py-1 text-xs ${
                      count > 0
                        ? "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                        : "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100"
                    }`}
                  >
                    📎 {count > 0 ? count : "—"}
                  </button>
                  {!readOnly && (
                    <button
                      type="button"
                      onClick={() => {
                        if (open) setOpenKey(null);
                        onRemove(row.key);
                      }}
                      className="rounded px-1.5 py-1 text-xs text-red-700 hover:bg-red-50"
                      title="Remover componente"
                    >
                      Remover
                    </button>
                  )}
                </div>

                {open && (
                  <ComponentAttachmentsPanel
                    componentId={row.id}
                    pendingFiles={row.pendingFiles}
                    readOnly={readOnly}
                    onPendingChange={(files) => onUpdate(row.key, { pendingFiles: files })}
                    onCountChange={(n) => onUpdate(row.key, { attachmentCount: n })}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {rows.length > 0 && semComprovante > 0 && (
        <p className="mt-2 text-[11px] text-amber-700">
          {semComprovante === 1
            ? "1 lançamento sem comprovante anexado."
            : `${semComprovante} lançamentos sem comprovante anexado.`}{" "}
          O comprovante é opcional e não impede o salvamento.
        </p>
      )}
    </div>
  );
}
