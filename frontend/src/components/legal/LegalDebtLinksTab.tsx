import { useCallback, useEffect, useState } from "react";
import { Money } from "@/components/Money";
import { PaymentBadge, StatusPill } from "@/components/legal/LegalPanelPieces";
import {
  LEGAL_STATUS_LABELS,
  dismissLegalDebtLink,
  linkLegalDebt,
  listLegalDebtLinkSuggestions,
  listLegalDebtLinks,
  unlinkLegalDebt,
  type LegalDebtLink,
  type LegalDebtLinkSuggestion,
} from "@/services/legal";
import { formatApiError } from "@/utils/apiError";

/**
 * Administração › Vínculos com Endividamento.
 *
 * O acordo de um processo (ou o acordo de rescisão de um desligado sem processo) é pago como uma
 * dívida do Endividamento. Ligar as duas pontas faz o Jurídico mostrar, sozinho, quanto já foi
 * pago e se está quitado. O nome só SUGERE o par — nada é vinculado sem a confirmação daqui.
 */

const CONFIDENCE_LABELS: Record<LegalDebtLinkSuggestion["confidence"], { label: string; tone: string }> = {
  VINCULADA: { label: "Já é do desligado", tone: "bg-indigo-100 text-indigo-800" },
  ALTA: { label: "Nome confere", tone: "bg-emerald-100 text-emerald-800" },
  MEDIA: { label: "Nome parecido", tone: "bg-amber-100 text-amber-900" },
};

function suggestionKey(s: LegalDebtLinkSuggestion): string {
  return `${s.item_id}:${s.case_id ?? ""}:${s.person_id}`;
}

export function LegalDebtLinksTab({
  canLinkCases,
  canLinkPersons,
}: {
  canLinkCases: boolean;
  canLinkPersons: boolean;
}) {
  const [suggestions, setSuggestions] = useState<LegalDebtLinkSuggestion[]>([]);
  const [links, setLinks] = useState<LegalDebtLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sug, lnk] = await Promise.all([listLegalDebtLinkSuggestions(), listLegalDebtLinks()]);
      setSuggestions(sug);
      setLinks(lnk);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(key: string, action: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await action();
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusy(null);
    }
  }

  const canConfirm = (s: LegalDebtLinkSuggestion) => (s.case_id ? canLinkCases : canLinkPersons);

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-500">
        Ligue cada acordo à dívida do Endividamento que o paga. A partir daí, Processos e Desligados
        mostram o valor pago e se o acordo está quitado, direto dos pagamentos do Contas a Pagar. O
        vínculo não altera nome nem valor da dívida.
      </p>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      <section className="rounded-xl border border-slate-200 bg-white">
        <header className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">Sugestões de vínculo</h2>
          <p className="text-xs text-slate-500">
            Dívidas do Endividamento cujo nome bate com um desligado. Confira antes de confirmar:
            nome parecido pode ser outra pessoa.
          </p>
        </header>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2 font-semibold">Dívida (Endividamento)</th>
                <th className="px-3 py-2 text-right font-semibold">Valor da dívida</th>
                <th className="px-3 py-2 font-semibold">Desligado</th>
                <th className="px-3 py-2 font-semibold">Processo</th>
                <th className="px-3 py-2 text-right font-semibold">Acordo</th>
                <th className="px-3 py-2 font-semibold">Confiança</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {!loading && suggestions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-slate-400">
                    Nenhuma sugestão pendente.
                  </td>
                </tr>
              ) : null}
              {suggestions.map((s) => {
                const key = suggestionKey(s);
                const conf = CONFIDENCE_LABELS[s.confidence];
                return (
                  <tr key={key} className="border-b border-slate-100 last:border-0">
                    <td className="max-w-[16rem] truncate px-3 py-2" title={s.debt_name}>
                      {s.debt_name}
                      {!s.debt_active ? <span className="ml-1.5 text-xs text-slate-400">(inativa)</span> : null}
                    </td>
                    <td className="px-3 py-2">
                      <Money value={s.debt_total} />
                    </td>
                    <td className="max-w-[14rem] truncate px-3 py-2" title={s.person_name}>
                      {s.person_name}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {s.case_number ? (
                        <span className="flex items-center gap-1.5">
                          <span className="tabular-nums">{s.case_number}</span>
                          {s.case_status ? (
                            <StatusPill status={s.case_status} label={LEGAL_STATUS_LABELS[s.case_status]} />
                          ) : null}
                        </span>
                      ) : (
                        <span className="text-slate-500">Sem processo (acordo de rescisão)</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {s.case_id ? <Money value={s.case_agreed} /> : <span className="block text-right text-slate-300">—</span>}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${conf.tone}`}>
                        {conf.label}
                      </span>
                      {s.value_matches ? (
                        <span className="ml-1.5 text-[11px] text-emerald-700" title="Valor da dívida a até 10% do acordo">
                          valor confere
                        </span>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <button
                        type="button"
                        disabled={!canConfirm(s) || busy !== null}
                        onClick={() =>
                          void run(key, () =>
                            linkLegalDebt({ item_id: s.item_id, case_id: s.case_id, person_id: s.person_id }),
                          )
                        }
                        className="rounded-lg bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        {busy === key ? "Vinculando…" : "Vincular"}
                      </button>
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() =>
                          void run(`x:${key}`, () =>
                            dismissLegalDebtLink({ item_id: s.item_id, case_id: s.case_id, person_id: s.person_id }),
                          )
                        }
                        className="ml-2 rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                      >
                        Descartar
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white">
        <header className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">Vínculos ativos</h2>
          <p className="text-xs text-slate-500">
            Dívidas do Endividamento ligadas a um processo ou desligado, com a situação de hoje.
          </p>
        </header>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2 font-semibold">Desligado</th>
                <th className="px-3 py-2 font-semibold">Processo</th>
                <th className="px-3 py-2 font-semibold">Dívida (Endividamento)</th>
                <th className="px-3 py-2 font-semibold">Situação</th>
                <th className="px-3 py-2 text-right font-semibold">Valor</th>
                <th className="px-3 py-2 text-right font-semibold">Pago</th>
                <th className="px-3 py-2 text-right font-semibold">Em aberto</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {!loading && links.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-sm text-slate-400">
                    Nenhuma dívida vinculada ainda.
                  </td>
                </tr>
              ) : null}
              {links.map((l) => {
                // Desfazer o vínculo com o processo exige editar Processos; com o desligado, Desligados.
                const canUnlink = (l.case_id ? canLinkCases : true) && (l.person_id ? canLinkPersons : true);
                return (
                  <tr key={l.item_id} className="border-b border-slate-100 last:border-0">
                    <td className="max-w-[14rem] truncate px-3 py-2">{l.person_name ?? "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                      {l.case_number ?? <span className="text-slate-500">Sem processo</span>}
                    </td>
                    <td className="max-w-[16rem] truncate px-3 py-2" title={l.debt_name}>
                      {l.debt_name}
                    </td>
                    <td className="px-3 py-2">
                      <PaymentBadge status={l.status} />
                    </td>
                    <td className="px-3 py-2">
                      <Money value={l.total} />
                    </td>
                    <td className="px-3 py-2">
                      <Money value={l.paid} />
                    </td>
                    <td className="px-3 py-2">
                      <Money value={l.pending} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        disabled={!canUnlink || busy !== null}
                        onClick={() => {
                          if (!window.confirm(`Desfazer o vínculo de "${l.debt_name}" com o Jurídico?`)) return;
                          void run(`u:${l.item_id}`, () => unlinkLegalDebt(l.item_id, true));
                        }}
                        className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                      >
                        Desvincular
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
