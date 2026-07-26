import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import {
  fetchCompanyFinanceEntries,
  replaceCompanyFinanceEntries,
  type LancamentoCompetenciaInput,
} from "@/services/companyFinance";
import {
  formatCurrencyInputFromApi,
  formatCurrencyOrDash,
  normalizeCurrencyForApi,
} from "@/utils/currency";

/**
 * Modal GENÉRICO de "Lançamentos da Competência".
 *
 * Exibe e edita uma coleção de lançamentos (vencimento, valor, descrição livre) de um item ×
 * competência. NÃO contém nenhuma regra de negócio de Custos Fixos/Ticket/parcelas: apenas
 * apresenta a coleção e delega a persistência ao service `replaceCompanyFinanceEntries`
 * (pipeline → PayableSnapshot). Ordenação e pagamento são governados pelo backend; lançamentos
 * pagos vêm bloqueados. Reutilizável para qualquer item corporativo.
 */

type EntryRow = {
  key: string;
  id: string | null;
  vencimento: string; // YYYY-MM-DD
  valor: string; // input formatado
  descricao: string;
  hasPayment: boolean;
  capStatus?: string | null;
};

let ROW_SEQ = 0;
const nextRowKey = () => `lc-${ROW_SEQ++}`;

const STATUS_LABEL: Record<string, string> = {
  PAGO: "Pago",
  PARCIAL: "Parcial",
  ABERTO: "Em aberto",
};

export function LancamentosCompetenciaModal({
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
  competencia: string; // YYYY-MM
  competenciaLabel: string;
  readOnly?: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const [rows, setRows] = useState<EntryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [redacted, setRedacted] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCompanyFinanceEntries(itemId, competencia);
      const anyRedacted = data.lancamentos.some((l) => l.valor == null);
      setRedacted(anyRedacted);
      setRows(
        data.lancamentos.map((l) => ({
          key: nextRowKey(),
          id: l.id,
          vencimento: l.vencimento ?? "",
          valor: l.valor != null ? formatCurrencyInputFromApi(l.valor) : "",
          descricao: l.descricao ?? "",
          hasPayment: Boolean(l.has_payment),
          capStatus: l.cap_status ?? null,
        })),
      );
    } catch {
      setError("Não foi possível carregar os lançamentos.");
    } finally {
      setLoading(false);
    }
  }, [itemId, competencia]);

  useEffect(() => {
    void load();
  }, [load]);

  const total = useMemo(
    () => rows.reduce((s, r) => s + normalizeCurrencyForApi(r.valor), 0),
    [rows],
  );

  const canEdit = !readOnly && !redacted;

  function addRow() {
    setRows((r) => [
      ...r,
      { key: nextRowKey(), id: null, vencimento: "", valor: "", descricao: "", hasPayment: false },
    ]);
  }

  function updateRow(key: string, patch: Partial<EntryRow>) {
    setRows((r) => r.map((x) => (x.key === key ? { ...x, ...patch } : x)));
  }

  function removeRow(key: string) {
    setRows((r) => r.filter((x) => x.key !== key));
  }

  async function save() {
    setSaving(true);
    setError(null);
    setWarning(null);
    try {
      const lancamentos: LancamentoCompetenciaInput[] = rows
        .map((r) => ({
          id: r.id ?? undefined,
          vencimento: r.vencimento || null,
          valor: normalizeCurrencyForApi(r.valor),
          descricao: r.descricao.trim() || null,
        }))
        // Descarta linhas novas totalmente vazias; linhas pagas (com id) são mantidas.
        .filter((l) => l.valor > 0 || l.id);
      const res = await replaceCompanyFinanceEntries(itemId, competencia, lancamentos);
      await Promise.resolve(onSaved());
      if (res.payable_sync_warning) {
        setWarning(res.payable_sync_warning);
        await load(); // mantém aberto para o usuário ver o que foi preservado
      } else {
        onClose();
      }
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar os lançamentos.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-2xl rounded-xl bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-slate-800">Lançamentos da Competência</h4>
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
        {warning && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
            {warning}
          </p>
        )}
        {redacted && (
          <p className="mt-3 text-xs text-slate-500">
            Valores ocultos (sem “Dados sensíveis”). Edição desabilitada.
          </p>
        )}

        <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50/40 p-3">
          {loading ? (
            <p className="text-xs text-slate-500">Carregando…</p>
          ) : (
            <div className="space-y-2">
              {rows.length === 0 && (
                <p className="py-2 text-center text-xs text-slate-400">Nenhum lançamento nesta competência.</p>
              )}
              {rows.length > 0 && (
                <div className="hidden grid-cols-[130px_1fr_1fr_auto] gap-2 px-1 text-[11px] font-medium uppercase tracking-wide text-slate-400 sm:grid">
                  <span>Vencimento</span>
                  <span>Valor</span>
                  <span>Descrição (opcional)</span>
                  <span />
                </div>
              )}
              {rows.map((r) => (
                <div
                  key={r.key}
                  className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[130px_1fr_1fr_auto]"
                >
                  <input
                    type="date"
                    value={r.vencimento}
                    onChange={(e) => updateRow(r.key, { vencimento: e.target.value })}
                    disabled={!canEdit || r.hasPayment}
                    className="rounded border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-500"
                  />
                  <div className="flex items-center gap-2">
                    <input
                      value={r.valor}
                      onChange={(e) => updateRow(r.key, { valor: e.target.value })}
                      disabled={!canEdit || r.hasPayment}
                      inputMode="decimal"
                      placeholder="0"
                      className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm tabular-nums disabled:bg-slate-100 disabled:text-slate-500"
                    />
                    {r.hasPayment && r.capStatus && (
                      <span className="whitespace-nowrap rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
                        {STATUS_LABEL[r.capStatus] ?? r.capStatus}
                      </span>
                    )}
                  </div>
                  <input
                    value={r.descricao}
                    onChange={(e) => updateRow(r.key, { descricao: e.target.value })}
                    disabled={!canEdit || r.hasPayment}
                    maxLength={150}
                    placeholder="Descrição (opcional)"
                    className="rounded border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-500"
                  />
                  <button
                    type="button"
                    onClick={() => removeRow(r.key)}
                    disabled={!canEdit || r.hasPayment}
                    title={r.hasPayment ? "Lançamento pago — não pode ser removido" : "Remover lançamento"}
                    className="justify-self-end rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Remover lançamento"
                  >
                    ✕
                  </button>
                </div>
              ))}

              {canEdit && (
                <button
                  type="button"
                  onClick={addRow}
                  className="mt-1 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
                >
                  + Adicionar lançamento
                </button>
              )}
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Total da competência
          </span>
          <span className="text-base font-semibold tabular-nums text-slate-800">
            {redacted ? "—" : formatCurrencyOrDash(total)}
          </span>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            disabled={saving}
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {canEdit ? "Cancelar" : "Fechar"}
          </button>
          {canEdit && (
            <button
              type="button"
              disabled={saving || loading}
              onClick={() => void save()}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Salvando…" : "Salvar lançamentos"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
