import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import { PageSizeSelect, TablePager } from "@/components/table";
import { usePagination, type PageSize } from "@/hooks/usePagination";
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
import { AddExistingItemDialog, ConcludeDialog, OutcomeNoteDialog } from "@/components/project-agenda/AgendaDialogs";
import { AgendaItemDialog } from "@/components/project-agenda/AgendaItemDialog";
import { OwnerPicker } from "@/components/project-agenda/OwnerPicker";

/** Padrão da pauta: 3 itens por página (pedido do Rafael — vale para qualquer layout da linha). */
const PAGINA_PADRAO = 3;
const TAMANHOS_PAUTA: readonly PageSize[] = [3, 5, 10, 15, 20, "ALL"];

/**
 * Pauta de uma reunião — os ITENS tratados nela, no ritmo da reunião gerencial semanal.
 *
 * Cada item é um ASSUNTO; o que cobra são as OBRIGAÇÕES dele (uma ou mais, cada uma com seus
 * responsáveis e prazo), que ficam dentro do item — a pauta mostra só o título, o resumo das
 * obrigações e a situação do item nesta reunião. Clicar no item abre as obrigações e o histórico.
 *
 * O modelo é **uma passagem por reunião**: o mesmo assunto rola de reunião em reunião, cada
 * passagem com o seu desfecho (Concluído · Parcial · Estendido). Ao estender, o item entra na
 * pauta da reunião escolhida levando as obrigações.
 */

const OUTCOMES: CommitmentOutcome[] = ["OPEN", "DONE", "PARTIAL", "EXTENDED"];

function dataBr(raw: string | null): string {
  if (!raw) return "—";
  return new Date(raw.length <= 10 ? `${raw}T12:00:00` : raw).toLocaleDateString("pt-BR");
}

type Rascunho = {
  title: string;
  external_participants: string;
  ob_title: string;
  ob_owner_ids: string[];
  ob_due: string;
};
const VAZIO: Rascunho = { title: "", external_participants: "", ob_title: "", ob_owner_ids: [], ob_due: "" };

function ResumoObrigacoes({ i }: { i: AgendaItem }) {
  if (i.obligations_total === 0) {
    return <span className="text-xs text-slate-400">Sem obrigações</span>;
  }
  const feitas = i.obligations_total - i.obligations_open;
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
      <span className="tabular-nums text-slate-600">
        {feitas}/{i.obligations_total} concluída{i.obligations_total === 1 ? "" : "s"}
      </span>
      {i.obligations_overdue > 0 ? (
        <span className="rounded-full bg-rose-50 px-1.5 py-px font-medium text-rose-700 ring-1 ring-rose-200">
          {i.obligations_overdue} atrasada{i.obligations_overdue === 1 ? "" : "s"}
        </span>
      ) : null}
    </span>
  );
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
  const [notaEstender, setNotaEstender] = useState("");
  const [concluindo, setConcluindo] = useState<AgendaItem | null>(null);
  const [parcialDe, setParcialDe] = useState<AgendaItem | null>(null);
  const [aberto, setAberto] = useState<AgendaItem | null>(null);
  const [trazendoExistente, setTrazendoExistente] = useState(false);
  const [excluindo, setExcluindo] = useState<string | null>(null);
  /** O MESMO formulário serve para anotar um item e para corrigir título/envolvidos. */
  const [form, setForm] = useState<{ modo: "novo" } | { modo: "edicao"; item: AgendaItem } | null>(null);
  const [rascunho, setRascunho] = useState<Rascunho>(VAZIO);
  const paginacao = usePagination(itens, PAGINA_PADRAO);

  const recarregar = useCallback(async () => {
    try {
      const novos = await listMeetingItems(meeting.id);
      setItens(novos);
      // A janela aberta acompanha o item atualizado (resumo, situação).
      setAberto((atual) => (atual ? (novos.find((n) => n.occurrence_id === atual.occurrence_id) ?? atual) : atual));
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar a pauta.");
    } finally {
      setCarregando(false);
    }
  }, [meeting.id]);

  useEffect(() => {
    void recarregar();
    void listAgendaUsers().then(setUsuarios).catch(() => setUsuarios([]));
    void listUpcomingMeetings()
      .then((rows) => {
        const outras = rows.filter((r) => r.id !== meeting.id);
        // Mesma série primeiro: é o destino natural de um item que "fica para a próxima".
        outras.sort((a, b) => {
          const sa = meeting.series_id != null && a.series_id === meeting.series_id ? 0 : 1;
          const sb = meeting.series_id != null && b.series_id === meeting.series_id ? 0 : 1;
          return sa - sb;
        });
        setReunioes(outras);
      })
      .catch(() => setReunioes([]));
  }, [recarregar, meeting.id, meeting.series_id]);

  function abrirNovo() {
    setRascunho(VAZIO);
    setForm({ modo: "novo" });
  }

  function abrirEdicao(i: AgendaItem) {
    setRascunho({ ...VAZIO, title: i.title, external_participants: i.external_participants ?? "" });
    setForm({ modo: "edicao", item: i });
  }

  async function salvar() {
    if (!rascunho.title.trim() || form === null) return;
    setSalvando(true);
    setErro(null);
    try {
      if (form.modo === "edicao") {
        await updateCommitment(form.item.id, {
          title: rascunho.title.trim(),
          external_participants: rascunho.external_participants.trim() || null,
        });
        await recarregar();
      } else {
        const novos = await addMeetingItem(meeting.id, {
          title: rascunho.title.trim(),
          external_participants: rascunho.external_participants.trim() || null,
          project_id: meeting.project_id,
          first_obligation: rascunho.ob_title.trim()
            ? {
                title: rascunho.ob_title.trim(),
                owner_ids: rascunho.ob_owner_ids,
                due_at: rascunho.ob_due ? new Date(`${rascunho.ob_due}T23:59`).toISOString() : null,
              }
            : null,
        });
        setItens(novos);
        // O item novo entra no FIM da pauta: leva o usuário até a página dele.
        if (paginacao.pageSize !== "ALL") paginacao.setPage(Math.ceil(novos.length / paginacao.pageSize));
      }
      setForm(null);
      setRascunho(VAZIO);
      await onChanged();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar o item.");
    } finally {
      setSalvando(false);
    }
  }

  async function marcar(
    item: AgendaItem,
    outcome: CommitmentOutcome,
    opts: { nextId?: string; nota?: string | null; concluirObrigacoes?: boolean } = {},
  ) {
    const perguntou = "nota" in opts;
    // Estender exige destino: a tela pede a reunião antes de enviar.
    if (outcome === "EXTENDED" && !opts.nextId) {
      setEstendendo(item.occurrence_id);
      return;
    }
    // Concluir e Parcial abrem uma caixa do sistema (o texto vai para o histórico do item).
    if (outcome === "DONE" && !perguntou) {
      if (item.outcome !== "DONE") setConcluindo(item);
      return;
    }
    if (outcome === "PARTIAL" && !perguntou) {
      if (item.outcome !== "PARTIAL") setParcialDe(item);
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      setItens(
        await setItemOutcome(
          item.occurrence_id,
          meeting.id,
          outcome,
          opts.nextId,
          opts.nota,
          Boolean(opts.concluirObrigacoes),
        ),
      );
      setEstendendo(null);
      setNotaEstender("");
      await onChanged();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível marcar o desfecho.");
    } finally {
      setSalvando(false);
    }
  }

  const proximaDaSerie =
    meeting.series_id == null ? null : (reunioes.find((r) => r.series_id === meeting.series_id) ?? null);

  const emAberto = itens.filter((i) => i.outcome === "OPEN" || i.outcome === "PARTIAL").length;
  const paginar = itens.length > 3;

  return (
    <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-600">Pauta da reunião</p>
        <div className="flex items-center gap-3">
          {paginar ? (
            <PageSizeSelect
              value={paginacao.pageSize}
              onChange={paginacao.setPageSize}
              label="Ver"
              options={TAMANHOS_PAUTA}
              compact
            />
          ) : null}
          <span className="text-[11px] text-slate-500">
            {emAberto} em aberto · {itens.length} {itens.length === 1 ? "item" : "itens"}
          </span>
        </div>
      </div>

      {carregando ? (
        <p className="px-4 py-5 text-center text-xs text-slate-500">Carregando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-white text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            <tr className="border-b border-slate-100">
              <th className="px-4 py-2 text-left">Item</th>
              <th className="w-56 px-3 py-2 text-left">Obrigações</th>
              <th className="w-72 px-3 py-2 text-left">Situação</th>
              <th className="w-24 px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {paginacao.pageRows.map((i) => {
              const emEdicao = form?.modo === "edicao" && form.item.occurrence_id === i.occurrence_id;
              return (
                <tr
                  key={i.occurrence_id}
                  className={
                    emEdicao
                      ? "bg-indigo-50/70"
                      : i.outcome === "DONE"
                        ? "bg-emerald-50/40"
                        : i.outcome === "EXTENDED"
                          ? "bg-slate-50/60"
                          : ""
                  }
                >
                  <td className="px-4 py-2.5 align-top">
                    <button
                      type="button"
                      onClick={() => setAberto(i)}
                      className="text-left font-medium text-slate-800 hover:text-indigo-700 hover:underline"
                      title="Abrir o item: obrigações e histórico"
                    >
                      {i.title}
                    </button>
                    {i.occurrence_number > 1 ? (
                      <p className="text-[11px] text-indigo-700">
                        {i.occurrence_number}ª vez · veio de {dataBr(i.came_from_date)}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <ResumoObrigacoes i={i} />
                  </td>
                  <td className="px-3 py-2.5 align-top">
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
                        <textarea
                          rows={2}
                          value={notaEstender}
                          onChange={(e) => setNotaEstender(e.target.value)}
                          placeholder="O que falta? (opcional — entra no histórico)"
                          className="mb-2 block w-full rounded-md border border-indigo-200 bg-white px-2 py-1 text-[11px]"
                        />
                        <p className="mb-1 text-[11px] text-slate-700">Levar para qual reunião?</p>
                        {reunioes.length ? (
                          <div className="flex flex-wrap gap-1">
                            {reunioes.slice(0, 6).map((r) => {
                              const mesmaSerie = proximaDaSerie != null && r.id === proximaDaSerie.id;
                              return (
                                <button
                                  key={r.id}
                                  type="button"
                                  disabled={salvando}
                                  onClick={() =>
                                    void marcar(i, "EXTENDED", { nextId: r.id, nota: notaEstender.trim() || null })
                                  }
                                  className={`rounded-lg px-2 py-1 text-[11px] font-medium ring-1 disabled:opacity-50 ${
                                    mesmaSerie
                                      ? "bg-indigo-600 text-white ring-indigo-600 hover:bg-indigo-700"
                                      : "bg-white text-indigo-700 ring-indigo-200 hover:bg-indigo-50"
                                  }`}
                                >
                                  {r.starts_at ? dataBr(r.starts_at) : r.title}
                                  {mesmaSerie ? " · próxima" : ""}
                                </button>
                              );
                            })}
                          </div>
                        ) : (
                          <p className="text-[11px] text-amber-800">
                            Não há reunião futura cadastrada. Marque a próxima na agenda primeiro.
                          </p>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            setEstendendo(null);
                            setNotaEstender("");
                          }}
                          className="mt-1 text-[11px] text-slate-500 hover:text-slate-700"
                        >
                          cancelar
                        </button>
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 text-right align-top">
                    <div className="flex flex-col items-end gap-0.5">
                      <button
                        type="button"
                        onClick={() => setAberto(i)}
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium text-indigo-700 hover:bg-indigo-50"
                      >
                        Abrir
                      </button>
                      {podeEditar ? (
                        <>
                          <button
                            type="button"
                            onClick={() => abrirEdicao(i)}
                            className="rounded px-1.5 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-100"
                          >
                            Editar
                          </button>
                          {excluindo === i.occurrence_id ? (
                            <button
                              type="button"
                              onClick={async () => {
                                setExcluindo(null);
                                await deleteCommitment(i.id);
                                await recarregar();
                                await onChanged();
                              }}
                              className="rounded bg-red-600 px-1.5 py-0.5 text-[11px] font-medium text-white hover:bg-red-700"
                              title="O item e as obrigações dele serão excluídos"
                            >
                              Confirmar
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setExcluindo(i.occurrence_id)}
                              className="rounded px-1.5 py-0.5 text-[11px] font-medium text-red-600 hover:bg-red-50"
                            >
                              Excluir
                            </button>
                          )}
                        </>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
            {itens.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-5 text-center text-xs text-slate-500">
                  Nenhum item em pauta. Anote abaixo o que a reunião vai tratar.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      )}

      {!carregando && paginar ? <TablePager pagination={paginacao} itemLabel="itens" /> : null}

      {podeEditar && form === null ? (
        <div className="flex flex-wrap gap-2 border-t border-slate-200 px-4 py-2">
          <button
            type="button"
            onClick={abrirNovo}
            className="rounded-lg px-2.5 py-1 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50"
          >
            + Novo item
          </button>
          <button
            type="button"
            onClick={() => setTrazendoExistente(true)}
            className="rounded-lg px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
          >
            + Item existente
          </button>
        </div>
      ) : null}

      {podeEditar && form !== null ? (
        <div className="border-t border-slate-200 bg-slate-50 px-4 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
            {form.modo === "edicao" ? "Editar item" : "Novo item"}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-xs font-medium text-slate-600 sm:col-span-2">
              Assunto
              <input
                autoFocus
                value={rascunho.title}
                onChange={(e) => setRascunho((r) => ({ ...r, title: e.target.value }))}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-slate-600">
              Envolvidos
              <input
                value={rascunho.external_participants}
                onChange={(e) => setRascunho((r) => ({ ...r, external_participants: e.target.value }))}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
              />
            </label>
          </div>
          {form.modo === "novo" ? (
            <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
              <p className="mb-2 text-[11px] text-slate-500">
                Primeira obrigação <span className="text-slate-400">(opcional — outras podem ser criadas ao abrir o item)</span>
              </p>
              <div className="grid gap-3 sm:grid-cols-6">
                <label className="text-xs font-medium text-slate-600 sm:col-span-6">
                  Obrigação
                  <input
                    value={rascunho.ob_title}
                    onChange={(e) => setRascunho((r) => ({ ...r, ob_title: e.target.value }))}
                    placeholder="O que precisa ser feito"
                    className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
                  />
                </label>
                <label className="text-xs font-medium text-slate-600 sm:col-span-4">
                  Responsáveis
                  <OwnerPicker
                    users={usuarios}
                    value={rascunho.ob_owner_ids}
                    onChange={(ids) => setRascunho((r) => ({ ...r, ob_owner_ids: ids }))}
                  />
                </label>
                <label className="text-xs font-medium text-slate-600 sm:col-span-2">
                  Prazo
                  <input
                    type="date"
                    value={rascunho.ob_due}
                    onChange={(e) => setRascunho((r) => ({ ...r, ob_due: e.target.value }))}
                    className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                  />
                </label>
              </div>
            </div>
          ) : null}
          <div className="mt-3 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setForm(null)}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Cancelar
            </button>
            <button
              type="button"
              disabled={salvando || !rascunho.title.trim()}
              onClick={() => void salvar()}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {salvando ? "Salvando…" : form.modo === "edicao" ? "Salvar alterações" : "Anotar item"}
            </button>
          </div>
        </div>
      ) : null}

      {erro ? <p className="px-4 py-2 text-xs text-red-700">{erro}</p> : null}
      <p className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
        Clique no item para ver e tratar as obrigações. Cada obrigação aparece no calendário, nos atrasados
        e no “só os meus” de todos os responsáveis.
      </p>

      {aberto ? (
        <AgendaItemDialog
          item={aberto}
          meetingId={meeting.id}
          users={usuarios}
          podeEditar={podeEditar}
          onClose={() => setAberto(null)}
          onChanged={async () => {
            await recarregar();
            await onChanged();
          }}
        />
      ) : null}

      {concluindo ? (
        <ConcludeDialog
          itemTitle={concluindo.title}
          openObligations={concluindo.obligations_open}
          onClose={() => setConcluindo(null)}
          onConfirm={async (nota, concluirObrigacoes) => {
            await marcar(concluindo, "DONE", { nota, concluirObrigacoes });
            setConcluindo(null);
          }}
        />
      ) : null}

      {parcialDe ? (
        <OutcomeNoteDialog
          title="Parcial"
          itemTitle={parcialDe.title}
          label="O que avançou e o que ainda falta?"
          placeholder="Ex.: Dra. Débora enviou a relação; falta a K-Lima liberar os 60k."
          confirmLabel="Marcar parcial"
          tone="amber"
          onClose={() => setParcialDe(null)}
          onConfirm={async (nota) => {
            await marcar(parcialDe, "PARTIAL", { nota });
            setParcialDe(null);
          }}
        />
      ) : null}

      {trazendoExistente ? (
        <AddExistingItemDialog
          meetingId={meeting.id}
          onClose={() => setTrazendoExistente(false)}
          onAdded={async () => {
            await recarregar();
            await onChanged();
          }}
        />
      ) : null}
    </div>
  );
}
