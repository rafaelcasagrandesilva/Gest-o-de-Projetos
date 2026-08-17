import { useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  createRepasseWithdrawal,
  fetchRepasseLedger,
  DIRECTION_LABELS,
  SOURCE_LABELS,
  WITHDRAWAL_PURPOSE_LABELS,
  type LedgerStatement,
  type WithdrawalPurpose,
} from "@/services/advanceRepasseLedger";
import { formatApiError } from "@/utils/apiError";
import { formatCurrency, normalizeCurrencyForApi, sanitizeCurrencyTyping } from "@/utils/currency";
import { Money } from "@/components/Money";

function formatDateBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return String(iso);
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Extrato de Repasse — read-only + Registrar retirada. O usuário vê Entradas/Saídas e o Saldo. */
export function RepasseLedgerModal({
  institutions,
  canEdit,
  onClose,
}: {
  institutions: { id: string; name: string }[];
  canEdit: boolean;
  onClose: () => void;
}) {
  const [instId, setInstId] = useState<string>(institutions[0]?.id ?? "");
  const [statement, setStatement] = useState<LedgerStatement | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [withdrawOpen, setWithdrawOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    async function run() {
      setLoading(true);
      setError(null);
      try {
        const st = await fetchRepasseLedger(instId || undefined);
        if (alive) setStatement(st);
      } catch (e) {
        if (alive) setError(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar o extrato.");
      } finally {
        if (alive) setLoading(false);
      }
    }
    void run();
    return () => {
      alive = false;
    };
  }, [instId, refresh]);

  const entries = useMemo(() => statement?.entries ?? [], [statement]);
  const selectedInst = institutions.find((i) => i.id === instId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2 sm:p-4" onClick={onClose}>
      <div
        className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-200 p-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Extrato do Repasse</h2>
            <p className="mt-0.5 text-sm text-slate-600">Entradas (operações) e saídas (liquidações e retiradas). Histórico preservado.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            ✕
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4">
          <label className="text-xs font-medium text-slate-600">
            Instituição
            <select
              value={instId}
              onChange={(e) => setInstId(e.target.value)}
              className="mt-1 block w-56 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              {institutions.length === 0 && <option value="">—</option>}
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center gap-4">
            {canEdit && (
              <button
                type="button"
                onClick={() => setWithdrawOpen(true)}
                disabled={!instId}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Registrar retirada
              </button>
            )}
            <div className="text-right">
              <p className="text-xs uppercase tracking-wide text-slate-500">Saldo do Repasse</p>
              <p className="text-xl font-semibold tabular-nums text-indigo-700">
                {statement ? formatCurrency(statement.balance) : "—"}
              </p>
            </div>
          </div>
        </div>

        {error && <div className="m-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}

        <div className="overflow-x-auto p-2">
          <table className="w-full min-w-[640px] divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-2 py-2">Data</th>
                <th className="px-2 py-2">Tipo</th>
                <th className="px-2 py-2">Origem</th>
                <th className="px-2 py-2 text-right">Valor</th>
                <th className="px-2 py-2">Descrição</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                    Carregando…
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                    Sem lançamentos.
                  </td>
                </tr>
              ) : (
                entries.map((e) => {
                  const isIn = e.direction === "CREDIT";
                  const reversed = Boolean(e.reversed_at);
                  const purposeLabel = e.withdrawal_purpose
                    ? WITHDRAWAL_PURPOSE_LABELS[e.withdrawal_purpose]
                    : null;
                  return (
                    <tr key={e.id} className={reversed ? "text-slate-400 line-through" : ""}>
                      <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(e.occurred_at)}</td>
                      <td className="px-2 py-1.5">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${
                            isIn ? "bg-emerald-100 text-emerald-900 ring-emerald-200" : "bg-red-100 text-red-800 ring-red-200"
                          }`}
                        >
                          {DIRECTION_LABELS[e.direction]}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-slate-600">{SOURCE_LABELS[e.source_type]}</td>
                      <td className={`px-2 py-1.5 ${isIn ? "text-emerald-700" : "text-red-700"}`}>
                        <Money value={e.amount} sign={isIn ? "+" : "−"} />
                      </td>
                      <td className="max-w-[240px] px-2 py-1.5 text-slate-600">
                        <div className="flex items-center gap-1.5">
                          {purposeLabel && (
                            <span className="inline-flex shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-900 ring-1 ring-amber-200">
                              {purposeLabel}
                            </span>
                          )}
                          <span className="truncate" title={e.description || undefined}>
                            {e.description || (purposeLabel ? "" : "—")}
                          </span>
                          {reversed && <span className="shrink-0 text-[10px] uppercase">(estornado)</span>}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {withdrawOpen && instId && (
        <WithdrawalModal
          institutionId={instId}
          institutionName={selectedInst?.name ?? "—"}
          onClose={() => setWithdrawOpen(false)}
          onSaved={() => {
            setWithdrawOpen(false);
            setRefresh((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Registrar retirada — DÉBITO append-only. Destino estruturado; observação livre à parte.
// ---------------------------------------------------------------------------

function WithdrawalModal({
  institutionId,
  institutionName,
  onClose,
  onSaved,
}: {
  institutionId: string;
  institutionName: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [occurredAt, setOccurredAt] = useState(todayIso());
  const [amount, setAmount] = useState("");
  const [purpose, setPurpose] = useState<WithdrawalPurpose>("DEBT_REDUCTION");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setErr(null);
    const value = normalizeCurrencyForApi(amount);
    if (value <= 0) {
      setErr("Informe um valor positivo para a retirada.");
      return;
    }
    setSaving(true);
    try {
      await createRepasseWithdrawal({
        institution_id: institutionId,
        amount: value,
        occurred_at: occurredAt || todayIso(),
        purpose,
        description: description.trim() || null,
      });
      onSaved();
    } catch (e) {
      // Validação oficial (inclusive saldo insuficiente) é do backend — exibimos a mensagem.
      setErr(isAxiosError(e) ? formatApiError(e) : "Não foi possível registrar a retirada.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-2 sm:p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-slate-200 p-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Registrar retirada</h3>
            <p className="mt-0.5 text-sm text-slate-600">{institutionName} · reduz o Saldo do Repasse.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            ✕
          </button>
        </div>

        <div className="space-y-3 p-4">
          <div className="flex flex-wrap gap-3">
            <label className="text-xs font-medium text-slate-600">
              Data
              <input
                type="date"
                value={occurredAt}
                onChange={(e) => setOccurredAt(e.target.value)}
                className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-slate-600">
              Valor
              <input
                value={amount}
                onChange={(e) => setAmount(sanitizeCurrencyTyping(e.target.value))}
                placeholder="0,00"
                className="mt-1 block w-40 rounded-lg border border-slate-300 px-2 py-1.5 text-right text-sm tabular-nums"
              />
            </label>
          </div>

          <fieldset className="text-xs font-medium text-slate-600">
            <legend className="mb-1">Destino do saque</legend>
            <div className="flex flex-col gap-1.5">
              <label className="inline-flex items-center gap-2 font-normal text-slate-700">
                <input
                  type="radio"
                  name="withdrawal-purpose"
                  checked={purpose === "DEBT_REDUCTION"}
                  onChange={() => setPurpose("DEBT_REDUCTION")}
                />
                {WITHDRAWAL_PURPOSE_LABELS.DEBT_REDUCTION}
              </label>
              <label className="inline-flex items-center gap-2 font-normal text-slate-700">
                <input
                  type="radio"
                  name="withdrawal-purpose"
                  checked={purpose === "OTHER"}
                  onChange={() => setPurpose("OTHER")}
                />
                {WITHDRAWAL_PURPOSE_LABELS.OTHER}
              </label>
            </div>
          </fieldset>

          <label className="block text-xs font-medium text-slate-600">
            Observação
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Opcional"
              rows={2}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>

          {err && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{err}</div>}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={saving}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Salvando…" : "Registrar retirada"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
