import { useEffect, useMemo, useState } from "react";
import { bulkDeleteStructureItems, type BulkDeleteResult, type CostCategory } from "../../services/projectStructure";

/**
 * Seleção múltipla + exclusão em massa das abas de estrutura do projeto.
 *
 * Um único lugar para as quatro abas (Mão de obra, Veículos, Sistemas, Custos diversos):
 * a exclusão é sempre em DUAS FASES — a primeira chamada só relata o que aconteceria, e é
 * ela que alimenta o aviso de "N destes já têm pagamento no Contas a Pagar". Excluir um
 * item com título pago não perde o dinheiro, mas deixa o título órfão, e essa consequência
 * precisa aparecer ANTES da confirmação.
 */
export function useBulkSelection<T>({
  projectId,
  category,
  rows,
  getId,
  resetKey,
  onDone,
}: {
  projectId: string;
  category: CostCategory;
  rows: T[];
  getId: (row: T) => string;
  /** Muda quando a competência/cenário muda — zera a seleção. */
  resetKey: string;
  onDone: () => void;
}) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<BulkDeleteResult | null>(null);
  const [busy, setBusy] = useState(false);

  // A seleção não pode sobreviver a uma troca de competência/cenário nem apontar para linha
  // que sumiu — senão o usuário confirmaria a exclusão de algo que não está mais vendo.
  useEffect(() => {
    setSelectedIds(new Set());
    setPreview(null);
  }, [resetKey]);

  const visibleIds = useMemo(() => rows.map(getId), [rows, getId]);
  const selected = useMemo(
    () => visibleIds.filter((id) => selectedIds.has(id)),
    [visibleIds, selectedIds],
  );
  const allSelected = visibleIds.length > 0 && selected.length === visibleIds.length;

  function toggleOne(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelectedIds(allSelected ? new Set() : new Set(visibleIds));
  }

  function clear() {
    setSelectedIds(new Set());
  }

  async function ask() {
    if (selected.length === 0) return;
    setBusy(true);
    try {
      setPreview(await bulkDeleteStructureItems(projectId, category, selected, false));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    try {
      await bulkDeleteStructureItems(projectId, category, selected, true);
      setSelectedIds(new Set());
      setPreview(null);
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return {
    selectedIds,
    selected,
    allSelected,
    visibleIds,
    preview,
    busy,
    toggleOne,
    toggleAll,
    clear,
    ask,
    confirm,
    cancel: () => setPreview(null),
  };
}

export type BulkSelection = ReturnType<typeof useBulkSelection>;

/** Checkbox do cabeçalho — marca/desmarca tudo o que está visível. */
export function BulkHeaderCheckbox({
  bulk,
  disabled,
}: {
  bulk: BulkSelection;
  disabled?: boolean;
}) {
  return (
    <th className="w-10 px-4 py-3">
      <input
        type="checkbox"
        checked={bulk.allSelected}
        onChange={bulk.toggleAll}
        disabled={disabled || bulk.visibleIds.length === 0}
        aria-label="Selecionar todos"
        title="Selecionar todos"
        className="h-4 w-4 cursor-pointer accent-indigo-600 disabled:cursor-not-allowed"
      />
    </th>
  );
}

/** Checkbox da linha. */
export function BulkRowCheckbox({
  bulk,
  id,
  label,
  disabled,
}: {
  bulk: BulkSelection;
  id: string;
  label: string;
  disabled?: boolean;
}) {
  return (
    <td className="px-4 py-3">
      <input
        type="checkbox"
        checked={bulk.selectedIds.has(id)}
        onChange={() => bulk.toggleOne(id)}
        disabled={disabled}
        aria-label={`Selecionar ${label}`}
        className="h-4 w-4 cursor-pointer accent-indigo-600 disabled:cursor-not-allowed"
      />
    </td>
  );
}

/** Barra que aparece quando há seleção. */
export function BulkActionBar({
  bulk,
  noun,
  nounPlural,
  disabled,
}: {
  bulk: BulkSelection;
  noun: string;
  nounPlural: string;
  disabled?: boolean;
}) {
  if (bulk.selected.length === 0) return null;
  return (
    <div className="mb-2 flex items-center justify-between rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2.5 text-sm">
      <span className="font-medium text-indigo-900">
        {bulk.selected.length} {bulk.selected.length === 1 ? noun : nounPlural} selecionado
        {bulk.selected.length === 1 ? "" : "s"}
      </span>
      <div className="flex items-center gap-3">
        <button type="button" onClick={bulk.clear} className="text-slate-600 hover:underline">
          Limpar seleção
        </button>
        <button
          type="button"
          disabled={disabled || bulk.busy}
          onClick={() => void bulk.ask()}
          className="rounded-lg bg-red-600 px-3 py-1.5 font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Excluir selecionados
        </button>
      </div>
    </div>
  );
}

/** Diálogo de confirmação, com o aviso de títulos já pagos. */
export function BulkDeleteDialog({
  bulk,
  noun,
  nounPlural,
}: {
  bulk: BulkSelection;
  noun: string;
  nounPlural: string;
}) {
  const p = bulk.preview;
  if (!p) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
        <h3 className="text-base font-semibold text-slate-900">Excluir itens?</h3>
        <p className="mt-2 text-sm text-slate-600">
          {p.total === 1
            ? `1 ${noun} será excluído desta competência.`
            : `${p.total} ${nounPlural} serão excluídos desta competência.`}{" "}
          Esta ação não pode ser desfeita.
        </p>
        {p.com_pagamento.length > 0 ? (
          /* O pagamento é preservado, mas o título fica órfão — o usuário precisa saber
             disso ANTES, senão vira resíduo "Origem removida" no Contas a Pagar. */
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-medium">
              {p.com_pagamento.length === 1
                ? "1 deles já tem pagamento lançado no Contas a Pagar:"
                : `${p.com_pagamento.length} deles já têm pagamento lançado no Contas a Pagar:`}
            </p>
            <p className="mt-1">{p.com_pagamento.join(", ")}</p>
            <p className="mt-2 text-xs">
              O pagamento é preservado, mas o título ficará sem origem e vai aparecer como
              resíduo no Contas a Pagar.
            </p>
          </div>
        ) : null}
        <div className="mt-5 flex justify-end gap-3">
          <button
            type="button"
            onClick={bulk.cancel}
            className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={bulk.busy}
            onClick={() => void bulk.confirm()}
            className="rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {bulk.busy ? "Excluindo…" : "Excluir"}
          </button>
        </div>
      </div>
    </div>
  );
}
