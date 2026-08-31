import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatApiError } from "@/utils/apiError";
import { formatCurrencyShortOrDash } from "@/utils/currency";
import { LegalEventForm } from "@/components/legal/LegalEventForm";
import {
  concludeEvent,
  fetchLegalSummary,
  fetchWorkCenter,
  EVENT_TYPE_LABELS,
  type LegalExecutiveSummary,
  type WorkCenter,
  type WorkItem,
} from "@/services/legalOperation";

/**
 * Central de Trabalho — a tela inicial do Workspace Jurídico.
 *
 * Princípio fundador (O2): não é um relatório de problemas, é uma FILA EXECUTÁVEL. Por isso
 * apenas três blocos, com horizontes distintos e ação na própria linha (U4):
 *
 *   AGORA          o que quebra hoje se ninguém agir
 *   ESTA SEMANA    o que vem nos próximos sete dias — para planejar, não para executar agora
 *   PRECISA DE DONO  o que não é de ninguém (O3) e o que parou de andar (O10)
 *
 * Regras de horizonte semanal (sem movimentação) ficam no terceiro bloco, nunca no primeiro:
 * misturar horizontes é o que incha o painel.
 */

function horaBR(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function dataBR(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function diaSemana(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
}

export function LegalWorkCenter() {
  const navigate = useNavigate();
  const [data, setData] = useState<WorkCenter | null>(null);
  const [summary, setSummary] = useState<LegalExecutiveSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [wc, sm] = await Promise.all([fetchWorkCenter(), fetchLegalSummary()]);
      setData(wc);
      setSummary(sm);
      setError(null);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleConcluir(item: WorkItem) {
    setBusyId(item.id);
    try {
      await concludeEvent(item.id, null);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  function abrirProcesso(caseId: string | null) {
    if (caseId) navigate(`/legal/cases?case=${caseId}`);
  }

  const hoje = new Date().toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Central de Trabalho</h2>
          <p className="text-sm text-slate-500 first-letter:uppercase">{hoje}</p>
        </div>
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700"
        >
          + Novo compromisso
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {/* Card executivo: cinco números, nada além (U1/U7). */}
      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Kpi label="Em andamento" value={String(summary.em_andamento)} tone="slate" />
          <Kpi label="Acordos" value={String(summary.acordos)} tone="indigo" />
          <Kpi label="Valor dos acordos" value={formatCurrencyShortOrDash(summary.valor_acordos)} tone="indigo" />
          <Kpi label="Em aberto" value={formatCurrencyShortOrDash(summary.pendente)} tone="amber" />
          <Kpi label="Encerrados" value={String(summary.encerrados)} tone="emerald" />
        </div>
      )}

      {loading ? (
        <p className="text-slate-500">Carregando…</p>
      ) : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            {/* ---------- AGORA ---------- */}
            <section className="overflow-hidden rounded-xl border border-red-200 bg-white shadow-sm">
              <header className="flex items-center justify-between border-b border-red-100 bg-red-50/60 px-5 py-3">
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-red-800">Agora</h3>
                  <p className="text-xs text-red-700/80">O que quebra hoje se ninguém agir</p>
                </div>
                <span className="rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-semibold text-white">
                  {data?.agora.length ?? 0}
                </span>
              </header>
              {data && data.agora.length > 0 ? (
                <ul>
                  {data.agora.map((item) => (
                    <li
                      key={item.id}
                      className="flex flex-wrap items-center gap-3 border-b border-slate-50 px-5 py-3 last:border-0"
                    >
                      <span className="w-14 shrink-0 text-sm font-semibold tabular-nums text-slate-900">
                        {horaBR(item.scheduled_for) || "—"}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-slate-900">{item.title}</p>
                        <p className="truncate text-xs text-slate-500">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
                            {EVENT_TYPE_LABELS[item.event_type] ?? item.event_type}
                          </span>
                          {item.case_number ? ` · ${item.case_number}` : ""}
                          {item.claimant ? ` · ${item.claimant}` : ""}
                          {item.location ? ` · ${item.location}` : ""}
                        </p>
                      </div>
                      {item.overdue && (
                        <span className="rounded bg-red-100 px-2 py-0.5 text-[11px] font-medium text-red-700">
                          atrasado
                        </span>
                      )}
                      <div className="flex shrink-0 gap-2">
                        <button
                          type="button"
                          disabled={busyId === item.id}
                          onClick={() => void handleConcluir(item)}
                          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        >
                          Concluir
                        </button>
                        {item.case_id && (
                          <button
                            type="button"
                            onClick={() => abrirProcesso(item.case_id)}
                            className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
                          >
                            Abrir caso
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="px-5 py-8 text-center text-sm text-slate-500">
                  Nada pendente para hoje. <span className="text-slate-400">A fila está limpa.</span>
                </p>
              )}
            </section>

            {/* ---------- ESTA SEMANA ---------- */}
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <header className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-5 py-3">
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-700">Esta semana</h3>
                  <p className="text-xs text-slate-500">Próximos sete dias — para planejar</p>
                </div>
                <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
                  {data?.semana.length ?? 0}
                </span>
              </header>
              {data && data.semana.length > 0 ? (
                <ul>
                  {data.semana.map((item) => (
                    <li
                      key={item.id}
                      className="flex flex-wrap items-center gap-3 border-b border-slate-50 px-5 py-2.5 last:border-0"
                    >
                      <span className="w-20 shrink-0 text-xs tabular-nums text-slate-500">
                        <span className="font-medium text-slate-700">{dataBR(item.scheduled_for)}</span>{" "}
                        {diaSemana(item.scheduled_for)}
                      </span>
                      <span className="w-12 shrink-0 text-xs tabular-nums text-slate-500">
                        {horaBR(item.scheduled_for)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-slate-800">{item.title}</p>
                        <p className="truncate text-xs text-slate-500">
                          {EVENT_TYPE_LABELS[item.event_type] ?? item.event_type}
                          {item.case_number ? ` · ${item.case_number}` : ""}
                        </p>
                      </div>
                      {item.case_id && (
                        <button
                          type="button"
                          onClick={() => abrirProcesso(item.case_id)}
                          className="shrink-0 text-xs text-indigo-600 hover:underline"
                        >
                          Abrir caso
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="px-5 py-6 text-center text-sm text-slate-500">Nenhum compromisso nos próximos sete dias.</p>
              )}
            </section>
          </div>

          <div className="space-y-5">
            {/* ---------- PRÓXIMAS AUDIÊNCIAS ---------- */}
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-800">Próximas audiências</h3>
              {data && data.proximas_audiencias.length > 0 ? (
                <ul className="mt-3 space-y-3">
                  {data.proximas_audiencias.map((a) => (
                    <li key={a.id} className="border-l-2 border-indigo-300 pl-3">
                      <p className="text-xs font-medium tabular-nums text-indigo-700">
                        {dataBR(a.scheduled_for)} · {horaBR(a.scheduled_for)}
                      </p>
                      <p className="truncate text-sm text-slate-800">{a.title}</p>
                      <p className="truncate text-xs text-slate-500">
                        {a.claimant ?? a.case_number ?? "sem processo vinculado"}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-sm text-slate-500">Nenhuma audiência agendada.</p>
              )}
            </section>

            {/* ---------- PRECISA DE DONO ---------- */}
            <section className="rounded-xl border border-amber-200 bg-white shadow-sm">
              <header className="border-b border-amber-100 bg-amber-50/60 px-5 py-3">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-900">Precisa de dono</h3>
                <p className="text-xs text-amber-800/80">Casos sem responsável ou parados</p>
              </header>
              <div className="space-y-4 px-5 py-4">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Sem responsável · {data?.sem_dono.length ?? 0}
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {(data?.sem_dono ?? []).slice(0, 5).map((c) => (
                      <li key={c.case_id}>
                        <button
                          type="button"
                          onClick={() => abrirProcesso(c.case_id)}
                          className="w-full truncate text-left text-sm text-slate-700 hover:text-indigo-700"
                        >
                          <span className="tabular-nums text-slate-500">{c.case_number}</span>
                          {c.claimant ? ` · ${c.claimant}` : ""}
                        </button>
                      </li>
                    ))}
                    {(data?.sem_dono.length ?? 0) === 0 && (
                      <li className="text-sm text-slate-400">Todos os casos têm responsável.</li>
                    )}
                  </ul>
                </div>

                <div className="border-t border-slate-100 pt-3">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Sem movimentação há {data?.stale_days ?? 60} dias · {data?.parados.length ?? 0}
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {(data?.parados ?? []).slice(0, 5).map((c) => (
                      <li key={c.case_id} className="flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => abrirProcesso(c.case_id)}
                          className="min-w-0 flex-1 truncate text-left text-sm text-slate-700 hover:text-indigo-700"
                        >
                          <span className="tabular-nums text-slate-500">{c.case_number}</span>
                          {c.claimant ? ` · ${c.claimant}` : ""}
                        </button>
                        <span className="shrink-0 text-xs tabular-nums text-amber-700">{c.days}d</span>
                      </li>
                    ))}
                    {(data?.parados.length ?? 0) === 0 && (
                      <li className="text-sm text-slate-400">Nenhum caso parado.</li>
                    )}
                  </ul>
                </div>
              </div>
            </section>
          </div>
        </div>
      )}

      {showForm && (
        <LegalEventForm onClose={() => setShowForm(false)} onCreated={() => void load()} />
      )}
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: string }) {
  const cores: Record<string, string> = {
    slate: "text-slate-900",
    indigo: "text-indigo-700",
    amber: "text-amber-700",
    emerald: "text-emerald-700",
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${cores[tone] ?? cores.slate}`}>{value}</p>
    </div>
  );
}
