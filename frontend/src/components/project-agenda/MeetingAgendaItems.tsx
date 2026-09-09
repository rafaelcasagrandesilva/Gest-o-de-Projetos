import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import {
  addMeetingItem,
  deleteCommitment,
  listAgendaUsers,
  listMeetingItems,
  listUpcomingMeetings,
  OUTCOME_LABELS,
  OUTCOME_STYLES,
  setItemOutcome,
  updateCommitment,
  type AgendaItem,
  type AgendaUser,
  type Commitment,
  type CommitmentOutcome,
  type MeetingOption,
} from "@/services/projectAgenda";

/**
 * Pauta de uma reunião — os itens tratados nela, no ritmo da reunião gerencial semanal.
 *
 * O modelo é **uma passagem por reunião**: o mesmo assunto costuma ser tratado em várias
 * reuniões seguidas, e cada passagem tem o seu desfecho (Concluído · Parcial · Estendido).
 * Guardar só o último desfecho faria a ata de cada reunião perder o que foi decidido nela.
 *
 * Ao marcar **Estendido**, o item entra automaticamente na pauta da reunião escolhida — é o que
 * faz a reunião seguinte já nascer montada — e o prazo passa a ser a data dela, que é o que se
 * combina na prática ("me traz até a reunião que vem").
 *
 * Não há campo de devolutiva: a devolutiva real é longa e vive na ATA anexada. Aqui fica o
 * essencial, estruturado — quem responde, até quando, e em que pé está.
 */

const OUTCOMES: CommitmentOutcome[] = ["OPEN", "DONE", "PARTIAL", "EXTENDED"];

function dataBr(raw: string | null): string {
  if (!raw) return "—";
  return new Date(raw.length <= 10 ? `${raw}T12:00:00` : raw).toLocaleDateString("pt-BR");
}

export function MeetingAgendaItems({
  meeting,
  podeEditar,
  onChanged,
}: {
  meeting: Commitment;
  podeEditar: boolean;
  onChanged: () => void | Promise<void>;
}) {
  const [itens, setItens] = useState<AgendaItem[]>([]);
  const [usuarios, setUsuarios] = useState<AgendaUser[]>([]);
  const [reunioes, setReunioes] = useState<MeetingOption[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  /** Item aguardando a escolha da reunião de destino (fluxo de "Estendido"). */
  const [estendendo, setEstendendo] = useState<string | null>(null);
  /** Item em edição na própria linha, e o rascunho dos campos. */
  const [editando, setEditando] = useState<string | null>(null);
  const [rascunho, setRascunho] = useState({
    title: "",
    description: "",
    external_participants: "",
    owner_user_id: "",
    due_at: "",
  });

  const [assunto, setAssunto] = useState("");
  const [acao, setAcao] = useState("");
  const [envolvidos, setEnvolvidos] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [prazo, setPrazo] = useState("");

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setItens(await listMeetingItems(meeting.id));
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar a pauta.");
    } finally {
      setCarregando(false);
    }
  }, [meeting.id]);

  useEffect(() => {
    void carregar();
    void listAgendaUsers().then(setUsuarios).catch(() => setUsuarios([]));
    void listUpcomingMeetings()
      .then((rows) => setReunioes(rows.filter((r) => r.id !== meeting.id)))
      .catch(() => setReunioes([]));
  }, [carregar, meeting.id]);

  async function adicionar() {
    if (!assunto.trim()) return;
    setSalvando(true);
    setErro(null);
    try {
      setItens(
        await addMeetingItem(meeting.id, {
          title: assunto.trim(),
          description: acao.trim() || null,
          external_participants: envolvidos.trim() || null,
          owner_user_id: responsavel || null,
          due_at: prazo ? new Date(`${prazo}T23:59`).toISOString() : null,
          project_id: meeting.project_id,
        }),
      );
      setAssunto("");
      setAcao("");
      setEnvolvidos("");
      setPrazo("");
      await onChanged();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível anotar o item.");
    } finally {
      setSalvando(false);
    }
  }

  function abrirEdicao(i: AgendaItem) {
    setEditando(i.occurrence_id);
    setRascunho({
      title: i.title,
      description: i.description ?? "",
      external_participants: i.external_participants ?? "",
      owner_user_id: i.owner_user_id ?? "",
      due_at: i.due_at ? new Date(i.due_at).toISOString().slice(0, 10) : "",
    });
  }

  /** Salva a correção do item. Errar o responsável na hora da reunião é comum — e antes
   *  disto a única saída era excluir e recriar, perdendo o histórico de passagens. */
  async function salvarEdicao(i: AgendaItem) {
    setSalvando(true);
    setErro(null);
    try {
      await updateCommitment(i.id, {
        title: rascunho.title.trim(),
        description: rascunho.description.trim() || null,
        external_participants: rascunho.external_participants.trim() || null,
        owner_user_id: rascunho.owner_user_id || null,
        due_at: rascunho.due_at ? new Date(`${rascunho.due_at}T23:59`).toISOString() : null,
      });
      setEditando(null);
      await carregar();
      await onChanged();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar a alteração.");
    } finally {
      setSalvando(false);
    }
  }

  async function marcar(item: AgendaItem, outcome: CommitmentOutcome, nextId?: string) {
    // Estender exige destino: em vez de recusar depois, a tela pede a reunião antes de enviar.
    if (outcome === "EXTENDED" && !nextId) {
      setEstendendo(item.occurrence_id);
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      setItens(await setItemOutcome(item.occurrence_id, meeting.id, outcome, nextId));
      setEstendendo(null);
      await onChanged();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível marcar o desfecho.");
    } finally {
      setSalvando(false);
    }
  }

  const emAberto = itens.filter((i) => i.outcome === "OPEN" || i.outcome === "PARTIAL").length;

  return (
    <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-600">
          Pauta da reunião
        </p>
        <span className="text-[11px] text-slate-500">
          {emAberto} em aberto · {itens.length} {itens.length === 1 ? "item" : "itens"}
        </span>
      </div>

      {carregando ? (
        <p className="px-4 py-5 text-center text-xs text-slate-500">Carregando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-white text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            <tr className="border-b border-slate-100">
              <th className="px-4 py-2.5 text-left">Assunto e ação</th>
              <th className="w-40 px-3 py-2.5 text-left">Envolvidos</th>
              <th className="w-44 px-3 py-2.5 text-left">Responsável</th>
              <th className="w-24 px-3 py-2.5 text-left">Prazo</th>
              <th className="w-64 px-3 py-2.5 text-left">Situação</th>
              <th className="w-20 px-3 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {itens.map((i) => {
              const emEdicao = editando === i.occurrence_id;
              return (
              <tr
                key={i.occurrence_id}
                className={
                  i.outcome === "DONE"
                    ? "bg-emerald-50/40"
                    : i.outcome === "EXTENDED"
                      ? "bg-slate-50/60"
                      : i.is_overdue
                        ? "bg-rose-50/40"
                        : ""
                }
              >
                <td className="px-4 py-3 align-top">
                  {emEdicao ? (
                    <div className="space-y-1.5">
                      <input
                        value={rascunho.title}
                        onChange={(e) => setRascunho((r) => ({ ...r, title: e.target.value }))}
                        placeholder="Assunto"
                        className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
                      />
                      <input
                        value={rascunho.description}
                        onChange={(e) => setRascunho((r) => ({ ...r, description: e.target.value }))}
                        placeholder="Ação"
                        className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
                      />
                    </div>
                  ) : (
                    <>
                      <p className="font-medium text-slate-800">{i.title}</p>
                      {i.description ? <p className="mt-0.5 text-xs text-slate-500">{i.description}</p> : null}
                    </>
                  )}
                  {/* Quantas vezes o assunto já rolou: um item na 4ª reunião é um sinal. */}
                  {i.occurrence_number > 1 ? (
                    <p className="mt-1 text-[11px] text-indigo-700">
                      {i.occurrence_number}ª vez · veio de {dataBr(i.came_from_date)}
                    </p>
                  ) : null}
                </td>
                <td className="px-3 py-3 align-top text-xs text-slate-600">
                  {emEdicao ? (
                    <input
                      value={rascunho.external_participants}
                      onChange={(e) =>
                        setRascunho((r) => ({ ...r, external_participants: e.target.value }))
                      }
                      placeholder="—"
                      className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
                    />
                  ) : (
                    (i.external_participants ?? "—")
                  )}
                </td>
                <td className="px-3 py-3 align-top text-xs text-slate-700">
                  {emEdicao ? (
                    <select
                      value={rascunho.owner_user_id}
                      onChange={(e) => setRascunho((r) => ({ ...r, owner_user_id: e.target.value }))}
                      className="w-full rounded border border-slate-300 px-1 py-1 text-xs"
                    >
                      <option value="">—</option>
                      {usuarios.map((u) => (
                        <option key={u.id} value={u.id}>{u.full_name}</option>
                      ))}
                    </select>
                  ) : (
                    (i.owner_name ?? "—")
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-3 align-top text-xs">
                  {emEdicao ? (
                    <input
                      type="date"
                      value={rascunho.due_at}
                      onChange={(e) => setRascunho((r) => ({ ...r, due_at: e.target.value }))}
                      className="w-full rounded border border-slate-300 px-1 py-1 text-xs"
                    />
                  ) : (
                    <span className={i.is_overdue && i.outcome !== "DONE" ? "font-medium text-rose-700" : "text-slate-600"}>
                      {i.due_at ? dataBr(i.due_at) : "—"}
                    </span>
                  )}
                </td>
                <td className="px-3 py-3 align-top">
                  {i.outcome === "EXTENDED" && i.extended_to_date ? (
                    <span className="inline-flex rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-800 ring-1 ring-indigo-200">
                      Estendido → {dataBr(i.extended_to_date)}
                    </span>
                  ) : podeEditar ? (
                    <div className="flex flex-wrap gap-1">
                      {OUTCOMES.map((o) => (
                        <button
                          key={o}
                          type="button"
                          disabled={salvando}
                          onClick={() => void marcar(i, o)}
                          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 disabled:opacity-50 ${
                            i.outcome === o ? OUTCOME_STYLES[o] : "bg-white text-slate-500 ring-slate-200 hover:bg-slate-50"
                          }`}
                        >
                          {OUTCOME_LABELS[o]}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${OUTCOME_STYLES[i.outcome]}`}>
                      {OUTCOME_LABELS[i.outcome]}
                    </span>
                  )}

                  {estendendo === i.occurrence_id ? (
                    <div className="mt-2 rounded-lg border border-indigo-200 bg-indigo-50/60 p-2">
                      <p className="mb-1 text-[11px] text-slate-700">Levar para qual reunião?</p>
                      {reunioes.length ? (
                        <div className="flex flex-wrap gap-1">
                          {reunioes.slice(0, 6).map((r) => (
                            <button
                              key={r.id}
                              type="button"
                              disabled={salvando}
                              onClick={() => void marcar(i, "EXTENDED", r.id)}
                              className="rounded-lg bg-white px-2 py-1 text-[11px] font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
                            >
                              {r.starts_at ? dataBr(r.starts_at) : r.title}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="text-[11px] text-amber-800">
                          Não há reunião futura cadastrada. Marque a próxima na agenda primeiro.
                        </p>
                      )}
                      <button
                        type="button"
                        onClick={() => setEstendendo(null)}
                        className="mt-1 text-[11px] text-slate-500 hover:text-slate-700"
                      >
                        cancelar
                      </button>
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-3 align-top text-right">
                  {podeEditar ? (
                    emEdicao ? (
                      <div className="flex flex-col items-end gap-1">
                        <button
                          type="button"
                          disabled={salvando || !rascunho.title.trim()}
                          onClick={() => void salvarEdicao(i)}
                          className="rounded bg-indigo-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                        >
                          Salvar
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditando(null)}
                          className="text-[11px] text-slate-500 hover:text-slate-700"
                        >
                          cancelar
                        </button>
                      </div>
                    ) : (
                      <div className="flex flex-col items-end gap-0.5">
                        <button
                          type="button"
                          onClick={() => abrirEdicao(i)}
                          className="rounded px-1.5 py-0.5 text-[11px] font-medium text-indigo-700 hover:bg-indigo-50"
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          onClick={async () => {
                            if (!window.confirm(`Excluir "${i.title}"?`)) return;
                            await deleteCommitment(i.id);
                            await carregar();
                            await onChanged();
                          }}
                          className="rounded px-1.5 py-0.5 text-[11px] font-medium text-red-600 hover:bg-red-50"
                        >
                          Excluir
                        </button>
                      </div>
                    )
                  ) : null}
                </td>
              </tr>
              );
            })}
            {itens.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-5 text-center text-xs text-slate-500">
                  Nenhum item em pauta. Anote abaixo o que a reunião decidiu.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      )}

      {podeEditar ? (
        <div className="border-t border-slate-200 bg-slate-50 px-4 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
            Anotar item
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-xs font-medium text-slate-600 lg:col-span-2">
              Assunto
              <input
                value={assunto}
                onChange={(e) => setAssunto(e.target.value)}
                placeholder="Ex.: Processos Trabalhistas ENEL"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-slate-600">
              Envolvidos
              <input
                value={envolvidos}
                onChange={(e) => setEnvolvidos(e.target.value)}
                placeholder="Ex.: Dra. Débora"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-slate-600">
              Responsável
              <select
                value={responsavel}
                onChange={(e) => setResponsavel(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              >
                <option value="">—</option>
                {usuarios.map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-600 lg:col-span-3">
              Ação
              <input
                value={acao}
                onChange={(e) => setAcao(e.target.value)}
                placeholder="Ex.: João entrar em contato com a Dra. Débora"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
              />
            </label>
            <div className="flex items-end gap-2">
              <label className="flex-1 text-xs font-medium text-slate-600">
                Prazo
                <input
                  type="date"
                  value={prazo}
                  onChange={(e) => setPrazo(e.target.value)}
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                />
              </label>
              <button
                type="button"
                disabled={salvando || !assunto.trim()}
                onClick={() => void adicionar()}
                className="shrink-0 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {salvando ? "…" : "Anotar"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {erro ? <p className="px-4 py-2 text-xs text-red-700">{erro}</p> : null}
      <p className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
        Cada item é um compromisso próprio: aparece no calendário, entra nos contadores de atraso
        e no “só os meus” de quem ficou responsável. O detalhe do que foi dito vive na ata.
      </p>
    </div>
  );
}
