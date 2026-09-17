import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import { ConcludeDialog, Dialog, RescheduleDialog } from "@/components/project-agenda/AgendaDialogs";
import { CommitmentUpdates } from "@/components/project-agenda/CommitmentUpdates";
import { OwnerPicker } from "@/components/project-agenda/OwnerPicker";
import {
  completeCommitment,
  createObligation,
  deleteCommitment,
  listObligations,
  reopenCommitment,
  rescheduleCommitment,
  updateCommitment,
  type AgendaItem,
  type AgendaUser,
  type Commitment,
} from "@/services/projectAgenda";

/**
 * Um item de pauta aberto: as OBRIGAÇÕES dele e o histórico.
 *
 * O item é o assunto; quem cobra são as obrigações — cada uma com um ou mais responsáveis e prazo,
 * e cada uma aparece no calendário e no "só os meus" de todos os responsáveis. Na reunião, cada
 * obrigação recebe conclusão ou prazo novo, e novas obrigações nascem aqui. A pauta mostra só o
 * título e o resumo; o detalhe vive nesta janela.
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

function ObligationForm({
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

export function AgendaItemDialog({
  item,
  meetingId,
  users,
  podeEditar,
  onChanged,
  onClose,
}: {
  item: AgendaItem;
  meetingId: string;
  users: AgendaUser[];
  podeEditar: boolean;
  onChanged: () => void | Promise<void>;
  onClose: () => void;
}) {
  const [obrigacoes, setObrigacoes] = useState<Commitment[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [criando, setCriando] = useState(false);
  const [editando, setEditando] = useState<string | null>(null);
  const [concluindo, setConcluindo] = useState<Commitment | null>(null);
  const [reprogramando, setReprogramando] = useState<Commitment | null>(null);
  const [excluindo, setExcluindo] = useState<string | null>(null);
  const [historicoAberto, setHistoricoAberto] = useState(false);
  /** Muda a cada alteração para o histórico recarregar (conclusões e prazos entram lá). */
  const [versao, setVersao] = useState(0);

  const carregar = useCallback(async () => {
    try {
      setObrigacoes(await listObligations(item.id));
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar as obrigações.");
      setObrigacoes([]);
    }
  }, [item.id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function depois() {
    await carregar();
    setVersao((v) => v + 1);
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
    <Dialog
      title={item.title}
      subtitle={item.external_participants ? `Envolvidos: ${item.external_participants}` : undefined}
      wide="xl"
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
          Fechar
        </button>
      }
    >
      {item.occurrence_number > 1 ? (
        <p className="mb-2 text-[11px] text-indigo-700">
          {item.occurrence_number}ª vez em pauta · veio de {dataBr(item.came_from_date)}
        </p>
      ) : null}
      {item.description ? (
        <p className="mb-3 whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">{item.description}</p>
      ) : null}

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
                await createObligation(item.id, {
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
              <div key={o.id} className={`flex items-start gap-3 px-3 py-2.5 ${concluida ? "bg-emerald-50/40" : ""}`}>
                <span
                  className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${
                    concluida ? "bg-emerald-500" : o.is_overdue ? "bg-rose-500" : "bg-amber-400"
                  }`}
                  title={concluida ? "Concluída" : o.is_overdue ? "Atrasada" : "Em aberto"}
                />
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-medium ${concluida ? "text-slate-500 line-through" : "text-slate-800"}`}>
                    {o.title}
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

      {/* Histórico recolhido: conclusões, prazos alterados e observações. Não ocupa a tela. */}
      <div className="mt-4 rounded-lg border border-slate-200">
        <button
          type="button"
          onClick={() => setHistoricoAberto((v) => !v)}
          className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 hover:bg-slate-50"
        >
          <span>Histórico e observações</span>
          <span className={`transition-transform ${historicoAberto ? "rotate-90" : ""}`}>›</span>
        </button>
        {historicoAberto ? (
          <div className="border-t border-slate-100 p-3">
            <CommitmentUpdates key={versao} commitmentId={item.id} meetingId={meetingId} podeEditar={podeEditar} />
          </div>
        ) : null}
      </div>

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
    </Dialog>
  );
}
