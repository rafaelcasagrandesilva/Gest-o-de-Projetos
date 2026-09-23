import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import { ConcludeDialog, RescheduleDialog } from "@/components/project-agenda/AgendaDialogs";
import { OwnerPicker } from "@/components/project-agenda/OwnerPicker";
import {
  completeCommitment,
  createObligation,
  deleteCommitment,
  listObligations,
  reopenCommitment,
  rescheduleCommitment,
  updateCommitment,
  OUTCOME_LABELS,
  OUTCOME_STYLES,
  type AgendaMeetingRef,
  type AgendaUser,
  type Commitment,
} from "@/services/projectAgenda";

/**
 * As OBRIGAÇÕES de um item de pauta, com tudo o que se faz nelas: criar, concluir, alterar prazo,
 * editar, reabrir e excluir.
 *
 * Painel ÚNICO, usado pela janela do item na pauta e pelo detalhe da obrigação aberto no
 * calendário/lista — assim as duas portas de entrada mostram e permitem exatamente o mesmo.
 * `meetingId` só vem quando se está DENTRO de uma reunião: conclusões e prazos alterados ficam
 * registrados como ditos nela; fora dela, entram no histórico como "fora de reunião".
 */

type Rascunho = { title: string; description: string; owner_ids: string[]; due: string };
const VAZIO: Rascunho = { title: "", description: "", owner_ids: [], due: "" };

function dataBr(raw: string | null): string {
  if (!raw) return "—";
  return new Date(raw).toLocaleDateString("pt-BR");
}

/** ISO → "AAAA-MM-DD" no fuso local (sem o deslize de um dia do toISOString). */
function paraInputDate(raw: string | null): string {
  if (!raw) return "";
  const d = new Date(raw);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const fimDoDia = (data: string) => new Date(`${data}T23:59`).toISOString();

export function ObligationForm({
  users,
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  users: AgendaUser[];
  initial: Rascunho;
  submitLabel: string;
  onSubmit: (r: Rascunho) => Promise<void>;
  onCancel: () => void;
}) {
  const [r, setR] = useState<Rascunho>(initial);
  const [salvando, setSalvando] = useState(false);

  async function enviar() {
    if (!r.title.trim()) return;
    setSalvando(true);
    try {
      await onSubmit(r);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-3">
      <div className="grid gap-3 sm:grid-cols-6">
        <label className="text-xs font-medium text-slate-600 sm:col-span-6">
          Obrigação
          <input
            autoFocus
            value={r.title}
            onChange={(e) => setR({ ...r, title: e.target.value })}
            placeholder="O que precisa ser feito"
            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm"
          />
        </label>
        <label className="text-xs font-medium text-slate-600 sm:col-span-4">
          Responsáveis
          <OwnerPicker users={users} value={r.owner_ids} onChange={(ids) => setR({ ...r, owner_ids: ids })} />
        </label>
        <label className="text-xs font-medium text-slate-600 sm:col-span-2">
          Prazo
          <input
            type="date"
            value={r.due}
            onChange={(e) => setR({ ...r, due: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
          />
        </label>
        <label className="text-xs font-medium text-slate-600 sm:col-span-6">
          Detalhes <span className="font-normal text-slate-400">(opcional)</span>
          <textarea
            rows={2}
            value={r.description}
            onChange={(e) => setR({ ...r, description: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm"
          />
        </label>
      </div>
      <div className="mt-2 flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100">
          Cancelar
        </button>
        <button
          type="button"
          disabled={salvando || !r.title.trim()}
          onClick={() => void enviar()}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {salvando ? "Salvando…" : submitLabel}
        </button>
      </div>
    </div>
  );
}

export function ItemObligations({
  itemId,
  meetingId = null,
  users,
  podeEditar,
  destaqueId = null,
  onChanged,
}: {
  itemId: string;
  /** Só dentro de uma reunião: conclusões e prazos ficam registrados como ditos nela. */
  meetingId?: string | null;
  users: AgendaUser[];
  podeEditar: boolean;
  /** Obrigação que foi aberta no calendário — aparece marcada como "esta". */
  destaqueId?: string | null;
  onChanged: () => void | Promise<void>;
}) {
  const [obrigacoes, setObrigacoes] = useState<Commitment[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [criando, setCriando] = useState(false);
  const [editando, setEditando] = useState<string | null>(null);
  const [concluindo, setConcluindo] = useState<Commitment | null>(null);
  const [reprogramando, setReprogramando] = useState<Commitment | null>(null);
  const [excluindo, setExcluindo] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setObrigacoes(await listObligations(itemId));
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar as obrigações.");
      setObrigacoes([]);
    }
  }, [itemId]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function depois() {
    await carregar();
    await onChanged();
  }

  async function executar(acao: () => Promise<unknown>, falha: string) {
    setErro(null);
    try {
      await acao();
      await depois();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : falha);
    }
  }

  const abertas = (obrigacoes ?? []).filter((o) => o.status !== "CONCLUIDO" && o.status !== "CANCELADO");

  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Obrigações {obrigacoes ? `· ${abertas.length} em aberto de ${obrigacoes.length}` : ""}
        </p>
        {podeEditar && !criando ? (
          <button
            type="button"
            onClick={() => setCriando(true)}
            className="rounded-lg px-2.5 py-1 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50"
          >
            + Nova obrigação
          </button>
        ) : null}
      </div>

      {criando ? (
        <div className="mt-2">
          <ObligationForm
            users={users}
            initial={VAZIO}
            submitLabel="Adicionar obrigação"
            onCancel={() => setCriando(false)}
            onSubmit={(r) =>
              executar(async () => {
                await createObligation(itemId, {
                  title: r.title.trim(),
                  description: r.description.trim() || null,
                  owner_ids: r.owner_ids,
                  due_at: r.due ? fimDoDia(r.due) : null,
                });
                setCriando(false);
              }, "Não foi possível criar a obrigação.")
            }
          />
        </div>
      ) : null}

      <div className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
        {obrigacoes === null ? (
          <p className="px-3 py-4 text-center text-xs text-slate-500">Carregando…</p>
        ) : obrigacoes.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-slate-500">
            Nenhuma obrigação. Use “+ Nova obrigação” para definir o que fazer, quem e até quando.
          </p>
        ) : (
          obrigacoes.map((o) => {
            const concluida = o.status === "CONCLUIDO";
            if (editando === o.id) {
              return (
                <div key={o.id} className="p-2">
                  <ObligationForm
                    users={users}
                    initial={{
                      title: o.title,
                      description: o.description ?? "",
                      owner_ids: o.owners.map((x) => x.user_id),
                      due: paraInputDate(o.due_at),
                    }}
                    submitLabel="Salvar"
                    onCancel={() => setEditando(null)}
                    onSubmit={(r) =>
                      executar(async () => {
                        await updateCommitment(o.id, {
                          title: r.title.trim(),
                          description: r.description.trim() || null,
                          owner_ids: r.owner_ids,
                          due_at: r.due ? fimDoDia(r.due) : null,
                        });
                        setEditando(null);
                      }, "Não foi possível salvar a obrigação.")
                    }
                  />
                </div>
              );
            }
            return (
              <div
                key={o.id}
                className={`flex items-start gap-3 px-3 py-2.5 ${
                  o.id === destaqueId ? "bg-indigo-50/70" : concluida ? "bg-emerald-50/40" : ""
                }`}
              >
                <span
                  className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${
                    concluida ? "bg-emerald-500" : o.is_overdue ? "bg-rose-500" : "bg-amber-400"
                  }`}
                  title={concluida ? "Concluída" : o.is_overdue ? "Atrasada" : "Em aberto"}
                />
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-medium ${concluida ? "text-slate-500 line-through" : "text-slate-800"}`}>
                    {o.title}
                    {o.id === destaqueId ? (
                      <span className="ml-2 rounded bg-indigo-100 px-1.5 py-px text-[10px] font-medium text-indigo-800 no-underline">
                        esta
                      </span>
                    ) : null}
                  </p>
                  {o.description ? (
                    <p className="mt-0.5 whitespace-pre-wrap text-xs text-slate-500">{o.description}</p>
                  ) : null}
                  <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-600">
                    <span>{o.owner_name ?? "Sem responsável"}</span>
                    <span className={!concluida && o.is_overdue ? "font-medium text-rose-700" : ""}>
                      Prazo <span className="tabular-nums">{dataBr(o.due_at)}</span>
                      {!concluida && o.is_overdue ? " · atrasada" : ""}
                    </span>
                    {concluida && o.completed_at ? (
                      <span className="text-emerald-700">Concluída em {dataBr(o.completed_at)}</span>
                    ) : null}
                  </p>
                  {concluida && o.completion_note ? (
                    <p className="mt-1 whitespace-pre-wrap text-xs text-emerald-800">{o.completion_note}</p>
                  ) : null}
                  {excluindo === o.id ? (
                    <div className="mt-1.5 flex items-center gap-2 text-xs">
                      <span className="text-red-700">Excluir esta obrigação?</span>
                      <button
                        type="button"
                        onClick={() => {
                          setExcluindo(null);
                          void executar(() => deleteCommitment(o.id), "Não foi possível excluir.");
                        }}
                        className="rounded px-2 py-0.5 font-medium text-white bg-red-600 hover:bg-red-700"
                      >
                        Excluir
                      </button>
                      <button type="button" onClick={() => setExcluindo(null)} className="text-slate-500 hover:text-slate-700">
                        cancelar
                      </button>
                    </div>
                  ) : null}
                </div>
                {podeEditar ? (
                  <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
                    {concluida ? (
                      <button
                        type="button"
                        onClick={() => void executar(() => reopenCommitment(o.id), "Não foi possível reabrir.")}
                        className="rounded-lg px-2 py-1 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50"
                      >
                        Reabrir
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => setConcluindo(o)}
                          className="rounded-lg bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-700"
                        >
                          Concluir
                        </button>
                        <button
                          type="button"
                          onClick={() => setReprogramando(o)}
                          className="rounded-lg px-2 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
                        >
                          Alterar prazo
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditando(o.id)}
                          className="rounded-lg px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                        >
                          Editar
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => setExcluindo(o.id)}
                      className="rounded-lg px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                    >
                      Excluir
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>

      {erro ? <p className="mt-2 text-xs text-red-700">{erro}</p> : null}

      {concluindo ? (
        <ConcludeDialog
          itemTitle={concluindo.title}
          onClose={() => setConcluindo(null)}
          onConfirm={async (nota) => {
            await completeCommitment(concluindo.id, nota, meetingId);
            setConcluindo(null);
            await depois();
          }}
        />
      ) : null}

      {reprogramando ? (
        <RescheduleDialog
          itemTitle={reprogramando.title}
          currentDue={reprogramando.due_at}
          onClose={() => setReprogramando(null)}
          onConfirm={async (data, motivo) => {
            await rescheduleCommitment(reprogramando.id, {
              due_at: fimDoDia(data),
              reason: motivo,
              meeting_id: meetingId,
            });
            setReprogramando(null);
            await depois();
          }}
        />
      ) : null}
    </div>
  );
}

/** "Quarta, 23/09" a partir do início da reunião. */
function diaDaReuniao(raw: string | null): string {
  if (!raw) return "sem data";
  return new Date(raw).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/**
 * Em quais pautas o item está / passou. Responde à pergunta "isso já está em alguma reunião?"
 * nas duas portas de entrada (pauta e calendário). A reunião atual, quando há, vem marcada.
 */
export function AgendaMeetingsInfo({
  pautas,
  reuniaoAtualId = null,
}: {
  pautas: AgendaMeetingRef[];
  reuniaoAtualId?: string | null;
}) {
  if (pautas.length === 0) {
    return (
      <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-amber-200">
        Ainda não está na pauta de nenhuma reunião.
      </p>
    );
  }
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  return (
    <ul className="flex flex-wrap gap-1.5">
      {pautas.map((p) => {
        const atual = p.meeting_id === reuniaoAtualId;
        const futura = p.meeting_starts_at ? new Date(p.meeting_starts_at) >= hoje : false;
        return (
          <li
            key={p.occurrence_id}
            title={p.meeting_title}
            className={`flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs ring-1 ${
              atual
                ? "bg-indigo-600 text-white ring-indigo-600"
                : futura
                  ? "bg-indigo-50 text-indigo-900 ring-indigo-200"
                  : "bg-white text-slate-600 ring-slate-200"
            }`}
          >
            <span className="tabular-nums font-medium">{diaDaReuniao(p.meeting_starts_at)}</span>
            <span className={`max-w-[12rem] truncate ${atual ? "text-indigo-100" : "text-slate-500"}`}>
              {p.meeting_title}
            </span>
            <span
              className={`rounded-full px-1.5 py-px text-[10px] font-medium ring-1 ${
                atual ? "bg-white/15 text-white ring-white/30" : OUTCOME_STYLES[p.outcome]
              }`}
            >
              {atual ? "esta reunião" : OUTCOME_LABELS[p.outcome]}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
