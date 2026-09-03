import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import {
  formatCurrencyInputFromApi,
  formatCurrencyOrDash,
  normalizeCurrencyForApi,
} from "@/utils/currency";
import type {
  ScheduleLineInput,
  ScheduleRangeInput,
  ScheduleRead,
  SchedulePreview,
} from "@/services/companyFinance";

/**
 * Editor GENÉRICO de Cronograma Financeiro.
 *
 * Conceito de primeira classe, reutilizável por qualquer obrigação parcelada (Endividamento
 * hoje; Processos Judiciais, Parcelamentos Tributários, Financiamentos, Acordos Comerciais no
 * futuro). NÃO contém regra de negócio nem conhece o domínio — recebe `load/preview/save` por
 * props e o `renegotiatedAmount` alvo. Toda a EXECUÇÃO (saldo/progresso/pago) é exibida pelo
 * chamador a partir do contrato do backend; aqui só se edita o PLANO (agenda de parcelas) e se
 * valida o fechamento (Σ cronograma = renegociado). Pagamentos vêm do backend e ficam travados.
 */

const MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

/** "2026-08-20" → "Ago/26". */
function monthChip(venc: string | null): string {
  if (!venc || venc.length < 7) return "—";
  const y = venc.slice(2, 4);
  const m = Number(venc.slice(5, 7));
  return `${MONTHS[m - 1] ?? "?"}/${y}`;
}

/** "2026-08-20" → "20/08/2026". */
function fmtDate(venc: string | null): string {
  if (!venc || venc.length < 10) return "—";
  return `${venc.slice(8, 10)}/${venc.slice(5, 7)}/${venc.slice(0, 4)}`;
}

type LineDraft = {
  key: string;
  id: string | null;
  seq: number;
  vencimento: string; // YYYY-MM-DD
  valor: string; // input formatado
  descricao: string;
  hasPayment: boolean;
  capStatus?: string | null;
};

let ROW_SEQ = 0;
const nextKey = () => `sl-${ROW_SEQ++}`;

function toDraft(l: ScheduleRead["lines"][number]): LineDraft {
  return {
    key: nextKey(),
    id: l.id,
    seq: l.seq ?? 0,
    vencimento: l.vencimento ?? "",
    valor: l.valor != null ? formatCurrencyInputFromApi(l.valor) : "",
    descricao: l.descricao ?? "",
    hasPayment: Boolean(l.has_payment),
    capStatus: l.cap_status ?? null,
  };
}

/** Atribui posição 1..N às parcelas sem sequência, respeitando as que já têm. */
function numerarParcelasSemSequencia(drafts: LineDraft[]): LineDraft[] {
  if (drafts.every((d) => d.seq > 0)) return drafts;
  const porVencimento = [...drafts].sort((a, b) =>
    (a.vencimento || "").localeCompare(b.vencimento || ""),
  );
  const usadas = new Set(drafts.filter((d) => d.seq > 0).map((d) => d.seq));
  let proxima = 1;
  const atribuida = new Map<string, number>();
  for (const d of porVencimento) {
    if (d.seq > 0) continue;
    while (usadas.has(proxima)) proxima += 1;
    usadas.add(proxima);
    atribuida.set(d.key, proxima);
  }
  return drafts.map((d) => (atribuida.has(d.key) ? { ...d, seq: atribuida.get(d.key)! } : d));
}

export function FinancialScheduleEditor({
  title,
  subtitle,
  renegotiatedAmount,
  load,
  preview,
  save,
  canEdit = true,
  onClose,
  onSaved,
}: {
  title: string;
  subtitle?: string;
  /** Valor renegociado alvo do fechamento (contrato). */
  renegotiatedAmount: number;
  load: () => Promise<ScheduleRead>;
  preview: (ranges: ScheduleRangeInput[]) => Promise<SchedulePreview>;
  save: (lines: ScheduleLineInput[]) => Promise<ScheduleRead>;
  canEdit?: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const [lines, setLines] = useState<LineDraft[]>([]);
  const [loadedPaid, setLoadedPaid] = useState<Map<number, LineDraft>>(new Map());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [redacted, setRedacted] = useState(false);

  // Faixas do gerador (form + lista acumulada).
  const [ranges, setRanges] = useState<ScheduleRangeInput[]>([]);
  const [fSeqStart, setFSeqStart] = useState("");
  const [fSeqEnd, setFSeqEnd] = useState("");
  const [fValor, setFValor] = useState("");
  const [fDia, setFDia] = useState("20");
  const [fFirst, setFFirst] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await load();
      const anyRedacted = data.lines.some((l) => l.valor == null);
      setRedacted(anyRedacted);
      // Parcela vinda da grade comum (Modo 1) não tem `schedule_seq` no banco. Sem numerá-la
      // aqui, ela chegava ao editor com seq 0 — exibida como "—" e recusada ao salvar, porque
      // o servidor exige seq >= 1. A posição é atribuída por VENCIMENTO, que é a ordem em que
      // as parcelas realmente acontecem; quem já tem seq mantém o seu.
      const drafts = numerarParcelasSemSequencia(data.lines.map(toDraft));
      setLines(drafts);
      setLoadedPaid(new Map(drafts.filter((d) => d.hasPayment).map((d) => [d.seq, d])));
    } catch {
      setError("Não foi possível carregar o cronograma.");
    } finally {
      setLoading(false);
    }
  }, [load]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const editable = canEdit && !redacted;

  // -------- Conferência (fechamento) — soma do RASCUNHO exibido (validação do plano). ----------
  const totalCronograma = useMemo(
    () => lines.reduce((s, r) => s + normalizeCurrencyForApi(r.valor), 0),
    [lines],
  );
  const diferenca = useMemo(
    () => Math.round((renegotiatedAmount - totalCronograma) * 100) / 100,
    [renegotiatedAmount, totalCronograma],
  );
  const fechado = Math.abs(diferenca) < 0.005;
  const ordered = useMemo(
    () => [...lines].sort((a, b) => (a.vencimento || "").localeCompare(b.vencimento || "") || a.seq - b.seq),
    [lines],
  );
  const primeira = ordered.find((l) => l.vencimento)?.vencimento ?? null;
  const ultima = [...ordered].reverse().find((l) => l.vencimento)?.vencimento ?? null;

  // -------- Gerador de faixas ----------
  function addRange() {
    const s = Number.parseInt(fSeqStart || "0", 10);
    const e = Number.parseInt(fSeqEnd || "0", 10);
    const v = normalizeCurrencyForApi(fValor);
    const d = Number.parseInt(fDia || "0", 10);
    if (!s || !e || e < s) return setError("Faixa inválida: parcela inicial/final.");
    if (v <= 0) return setError("Faixa inválida: valor deve ser maior que zero.");
    if (d < 1 || d > 31) return setError("Faixa inválida: dia entre 1 e 31.");
    if (!fFirst) return setError("Faixa inválida: informe o primeiro vencimento.");
    setError(null);
    setRanges((r) => [...r, { seq_start: s, seq_end: e, valor: v, dia: d, primeiro_vencimento: fFirst }]);
    // Prepara a próxima faixa continuando a numeração.
    setFSeqStart(String(e + 1));
    setFSeqEnd("");
    setFValor("");
    setFFirst("");
  }

  function removeRange(idx: number) {
    setRanges((r) => r.filter((_, i) => i !== idx));
  }

  async function generate() {
    if (ranges.length === 0) return setError("Adicione ao menos uma faixa.");
    setGenerating(true);
    setError(null);
    try {
      const res = await preview(ranges);
      // Regeração preserva parcelas PAGAS (casadas por seq): o backend também garante isso ao salvar.
      const merged: LineDraft[] = res.lines.map((l) => {
        const paid = loadedPaid.get(l.seq);
        if (paid) return { ...paid, key: nextKey() };
        return {
          key: nextKey(),
          id: null,
          seq: l.seq,
          vencimento: l.vencimento,
          valor: formatCurrencyInputFromApi(l.valor),
          descricao: l.descricao ?? "",
          hasPayment: false,
        };
      });
      setLines(merged);
      setRanges([]);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível gerar o cronograma.");
    } finally {
      setGenerating(false);
    }
  }

  // -------- Edição pontual ----------
  function updateLine(key: string, patch: Partial<LineDraft>) {
    setLines((r) => r.map((x) => (x.key === key ? { ...x, ...patch } : x)));
  }
  function removeLine(key: string) {
    setLines((r) => r.filter((x) => x.key !== key));
  }
  function addExtraLine() {
    const maxSeq = lines.reduce((m, l) => Math.max(m, l.seq), 0);
    setLines((r) => [
      ...r,
      { key: nextKey(), id: null, seq: maxSeq + 1, vencimento: "", valor: "", descricao: "", hasPayment: false },
    ]);
  }

  async function doSave() {
    setSaving(true);
    setError(null);
    setWarning(null);
    try {
      const payload: ScheduleLineInput[] = ordered
        .map((r) => ({
          id: r.id ?? undefined,
          seq: r.seq,
          vencimento: r.vencimento,
          valor: normalizeCurrencyForApi(r.valor),
          descricao: r.descricao.trim() || null,
        }))
        .filter((l) => l.valor > 0 && l.vencimento);
      const res = await save(payload);
      await Promise.resolve(onSaved());
      if (res.payable_sync_warning) {
        setWarning(res.payable_sync_warning);
        await reload();
      } else {
        onClose();
      }
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar o cronograma.");
    } finally {
      setSaving(false);
    }
  }

  const hasLines = lines.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/30 p-4">
      <div className="my-6 w-full max-w-4xl rounded-xl bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-slate-800">{title}</h4>
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
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

        {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-red-200">{error}</p>}
        {warning && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">{warning}</p>
        )}
        {redacted && (
          <p className="mt-3 text-xs text-slate-500">Valores ocultos (sem “Dados sensíveis”). Edição desabilitada.</p>
        )}

        {loading ? (
          <p className="mt-4 text-xs text-slate-500">Carregando…</p>
        ) : (
          <>
            {/* -------- Gerador de faixas (fluxo principal de criação) -------- */}
            {editable && (
              <section className="mt-4 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3">
                <h5 className="text-xs font-semibold uppercase tracking-wide text-indigo-800">Gerador por faixas</h5>
                <p className="mt-0.5 text-[11px] text-indigo-700/80">
                  Monte o acordo em blocos (ex.: 1–6 · R$ 15.000 · dia 20). Adicione as faixas e gere o cronograma.
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-[repeat(5,minmax(0,1fr))_auto]">
                  <label className="flex flex-col gap-1 text-[11px] text-slate-600">
                    Parcela inicial
                    <input value={fSeqStart} onChange={(e) => setFSeqStart(e.target.value)} inputMode="numeric"
                      className="rounded border border-slate-300 px-2 py-1.5 text-sm" placeholder="1" />
                  </label>
                  <label className="flex flex-col gap-1 text-[11px] text-slate-600">
                    Parcela final
                    <input value={fSeqEnd} onChange={(e) => setFSeqEnd(e.target.value)} inputMode="numeric"
                      className="rounded border border-slate-300 px-2 py-1.5 text-sm" placeholder="6" />
                  </label>
                  <label className="flex flex-col gap-1 text-[11px] text-slate-600">
                    Valor
                    <input value={fValor} onChange={(e) => setFValor(e.target.value)} inputMode="decimal"
                      className="rounded border border-slate-300 px-2 py-1.5 text-sm tabular-nums" placeholder="15.000,00" />
                  </label>
                  <label className="flex flex-col gap-1 text-[11px] text-slate-600">
                    Dia
                    <input value={fDia} onChange={(e) => setFDia(e.target.value)} inputMode="numeric"
                      className="rounded border border-slate-300 px-2 py-1.5 text-sm" placeholder="20" />
                  </label>
                  <label className="flex flex-col gap-1 text-[11px] text-slate-600">
                    1º vencimento
                    <input type="date" value={fFirst} onChange={(e) => setFFirst(e.target.value)}
                      className="rounded border border-slate-300 px-2 py-1.5 text-sm" />
                  </label>
                  <div className="flex items-end">
                    <button type="button" onClick={addRange}
                      className="w-full rounded-lg border border-dashed border-indigo-300 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-100">
                      + Faixa
                    </button>
                  </div>
                </div>

                {ranges.length > 0 && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {ranges.map((r, i) => (
                      <span key={i} className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-700 ring-1 ring-indigo-200">
                        {r.seq_start}–{r.seq_end} · {formatCurrencyOrDash(r.valor)} · dia {r.dia}
                        <button type="button" onClick={() => removeRange(i)} className="ml-0.5 text-slate-400 hover:text-red-600" aria-label="Remover faixa">✕</button>
                      </span>
                    ))}
                    <button type="button" onClick={() => void generate()} disabled={generating}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                      {generating ? "Gerando…" : "Gerar cronograma"}
                    </button>
                  </div>
                )}
              </section>
            )}

            {/* -------- Timeline (resumo visual do tamanho do acordo) -------- */}
            {hasLines && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {ordered.map((l) => (
                  <span key={l.key}
                    title={`${fmtDate(l.vencimento)} · ${formatCurrencyOrDash(normalizeCurrencyForApi(l.valor))}`}
                    className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] tabular-nums ring-1 ${
                      l.hasPayment ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-slate-50 text-slate-500 ring-slate-200"
                    }`}>
                    {monthChip(l.vencimento)} {l.hasPayment ? "✔" : "●"}
                  </span>
                ))}
              </div>
            )}

            {/* -------- Tabela do cronograma (edição pontual) -------- */}
            {hasLines && (
              <div className="mt-4 max-h-[320px] overflow-y-auto rounded-lg border border-slate-100">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="px-2 py-1.5 text-left font-medium">#</th>
                      <th className="px-2 py-1.5 text-left font-medium">Vencimento</th>
                      <th className="px-2 py-1.5 text-left font-medium">Valor</th>
                      <th className="px-2 py-1.5 text-left font-medium">Descrição</th>
                      <th className="px-2 py-1.5 text-left font-medium">Situação</th>
                      <th className="px-2 py-1.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {ordered.map((l) => (
                      <tr key={l.key} className={l.hasPayment ? "bg-emerald-50/40" : "odd:bg-white even:bg-slate-50/40"}>
                        <td className="px-2 py-1.5 tabular-nums text-slate-500">{l.seq || "—"}</td>
                        <td className="px-2 py-1.5">
                          <input type="date" value={l.vencimento}
                            onChange={(e) => updateLine(l.key, { vencimento: e.target.value })}
                            disabled={!editable || l.hasPayment}
                            className="rounded border border-slate-300 px-2 py-1 text-sm disabled:border-transparent disabled:bg-transparent disabled:text-slate-600" />
                        </td>
                        <td className="px-2 py-1.5">
                          <input value={l.valor} inputMode="decimal"
                            onChange={(e) => updateLine(l.key, { valor: e.target.value })}
                            disabled={!editable || l.hasPayment}
                            className="w-32 rounded border border-slate-300 px-2 py-1 text-sm tabular-nums disabled:border-transparent disabled:bg-transparent disabled:text-slate-600" />
                        </td>
                        <td className="px-2 py-1.5">
                          <input value={l.descricao} maxLength={150}
                            onChange={(e) => updateLine(l.key, { descricao: e.target.value })}
                            disabled={!editable || l.hasPayment}
                            placeholder="—"
                            className="w-full rounded border border-slate-300 px-2 py-1 text-sm disabled:border-transparent disabled:bg-transparent disabled:text-slate-500" />
                        </td>
                        <td className="px-2 py-1.5">
                          {l.hasPayment ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                              🔒 Pago
                            </span>
                          ) : (
                            <span className="text-[11px] text-slate-400">Em aberto</span>
                          )}
                        </td>
                        <td className="px-2 py-1.5 text-right">
                          <button type="button" onClick={() => removeLine(l.key)}
                            disabled={!editable || l.hasPayment}
                            title={l.hasPayment ? "Parcela paga — não pode ser removida" : "Remover parcela"}
                            className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-30"
                            aria-label="Remover parcela">✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {editable && hasLines && (
              <button type="button" onClick={addExtraLine}
                className="mt-2 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700">
                + Adicionar parcela extraordinária
              </button>
            )}

            {/* -------- Painel de conferência -------- */}
            {hasLines && (
              <div className={`mt-4 rounded-lg p-3 ring-1 ${fechado ? "bg-emerald-50 ring-emerald-200" : "bg-red-50 ring-red-300"}`}>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-4">
                  <Stat label="Valor renegociado" value={formatCurrencyOrDash(renegotiatedAmount)} />
                  <Stat label="Total do cronograma" value={redacted ? "—" : formatCurrencyOrDash(totalCronograma)} />
                  <Stat label="Diferença" value={redacted ? "—" : formatCurrencyOrDash(diferenca)} strong={!fechado} />
                  <Stat label="Parcelas" value={String(lines.length)} />
                  <Stat label="1ª parcela" value={fmtDate(primeira)} />
                  <Stat label="Última parcela" value={fmtDate(ultima)} />
                  <Stat label="Encerramento" value={fmtDate(ultima)} />
                  <div className="flex items-end">
                    {fechado ? (
                      <span className="text-sm font-semibold text-emerald-700">✔ Cronograma válido</span>
                    ) : (
                      <span className="text-sm font-semibold text-red-700">⚠ Não fecha o renegociado</span>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="mt-4 flex items-center justify-end gap-2">
              <button type="button" disabled={saving} onClick={onClose}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                {editable ? "Cancelar" : "Fechar"}
              </button>
              {editable && (
                <button type="button" onClick={() => void doSave()} disabled={saving || !hasLines || !fechado}
                  title={!fechado ? "O cronograma precisa fechar o valor renegociado para salvar." : undefined}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">
                  {saving ? "Salvando…" : "Salvar cronograma"}
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className={`tabular-nums ${strong ? "text-sm font-bold text-red-700" : "text-sm font-semibold text-slate-800"}`}>{value}</dd>
    </div>
  );
}
