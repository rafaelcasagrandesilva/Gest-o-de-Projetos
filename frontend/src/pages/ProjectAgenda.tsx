import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { api } from "@/services/api";
import { useAuth } from "@/context/AuthContext";
import { formatApiError } from "@/utils/apiError";
import { canPreviewInBrowser, saveBlobAsFile, viewFileInNewTab } from "@/utils/fileView";
import { CommitmentModal } from "@/components/project-agenda/CommitmentModal";
import { MeetingAgendaItems } from "@/components/project-agenda/MeetingAgendaItems";
import {
  commitmentAttachmentUrl,
  completeCommitment,
  deleteCommitment,
  fetchAgendaCounters,
  KIND_LABELS,
  KIND_STYLES,
  listCommitments,
  reopenCommitment,
  type AgendaCounters,
  type Commitment,
} from "@/services/projectAgenda";

/**
 * Agenda do workspace Projetos.
 *
 * Módulo PRÓPRIO: nenhum registro, opção ou componente é compartilhado com a agenda do Jurídico
 * (decisão de produto — ver docs/ETAPA0_AGENDA_PROJETOS.md). As três visões existem porque é o
 * formato que a equipe já conhece, não porque o código seja o mesmo.
 *
 * O que diferencia esta agenda de um calendário: ela COBRA. O filtro "só os meus" e os
 * contadores de atraso são o que fazem uma obrigação atribuída aparecer para quem tem que
 * entregá-la, em vez de esperar que alguém lembre de procurar.
 */

type Vista = "mes" | "semana" | "lista";

const DIAS = ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"];
const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

function inicioDoMes(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function inicioDaSemana(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - x.getDay());
  return x;
}
function addDias(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function mesmoDia(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString();
}
/** A data que posiciona o compromisso: quando acontece ou, na falta, quando vence. */
function quando(c: Commitment): Date | null {
  const raw = c.starts_at ?? c.due_at;
  return raw ? new Date(raw) : null;
}
function hora(c: Commitment): string {
  // Hora só faz sentido no que ACONTECE numa hora. Uma obrigação tem prazo, e o 23:59 que o
  // formulário grava como fim do dia é detalhe técnico — mostrá-lo seria ruído na tela.
  if (!c.starts_at || c.all_day) return "";
  return new Date(c.starts_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
function dataBr(raw: string | null): string {
  if (!raw) return "—";
  return new Date(raw).toLocaleDateString("pt-BR");
}

function Contador({ label, valor, meus, destaque }: { label: string; valor: number; meus: number; destaque?: boolean }) {
  return (
    <div
      className={`rounded-lg border px-3 py-2 ${
        destaque && valor > 0 ? "border-rose-200 bg-rose-50" : "border-slate-200 bg-white"
      }`}
    >
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${destaque && valor > 0 ? "text-rose-800" : "text-slate-900"}`}>
        {valor}
      </p>
      <p className="text-[10px] text-slate-500">{meus} {meus === 1 ? "seu" : "seus"}</p>
    </div>
  );
}

/** Quantas etiquetas cabem num dia antes de a célula esticar e desalinhar a semana. */
const CHIPS_POR_DIA = 4;

/** Etiqueta do compromisso no calendário: tipo, hora e título, com marca de atraso. */
function Chip({ c, onClick }: { c: Commitment; onClick: () => void }) {
  const concluido = c.status === "CONCLUIDO";
  return (
    <button
      type="button"
      // Para o clique aqui: a célula do dia abre o "novo compromisso", e sem isto abrir um
      // compromisso existente abriria o formulário em branco por cima.
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      title={`${KIND_LABELS[c.kind]} — ${c.title}${c.owner_name ? ` · ${c.owner_name}` : ""}`}
      className={`block w-full truncate rounded px-1.5 py-0.5 text-left text-[11px] ring-1 hover:brightness-95 ${
        concluido ? "bg-slate-100 text-slate-500 line-through ring-slate-200" : KIND_STYLES[c.kind]
      }`}
    >
      {c.is_overdue ? <span className="mr-1 font-bold text-rose-700">!</span> : null}
      {hora(c) ? <span className="mr-1 tabular-nums opacity-70">{hora(c)}</span> : null}
      {c.title}
    </button>
  );
}

export function ProjectAgenda() {
  const { user } = useAuth();
  const podeEditar = Boolean(user?.permission_names?.includes("project_agenda.create"));

  const [vista, setVista] = useState<Vista>("mes");
  const [referencia, setReferencia] = useState(new Date());
  const [soMeus, setSoMeus] = useState(false);
  const [itens, setItens] = useState<Commitment[]>([]);
  const [contadores, setContadores] = useState<AgendaCounters | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const [emEdicao, setEmEdicao] = useState<Commitment | null>(null);
  //: Data clicada no calendário, para o formulário já nascer no dia certo.
  const [dataPadrao, setDataPadrao] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<Commitment | null>(null);
  /** Dia (ISO) com a lista aberta. Um por vez: abrir outro fecha o anterior, senão a grade
   *  volta a esticar em vários lugares ao mesmo tempo. */
  const [diaAberto, setDiaAberto] = useState<string | null>(null);

  const janela = useMemo(() => {
    if (vista === "semana") {
      const ini = inicioDaSemana(referencia);
      return { inicio: ini, fim: addDias(ini, 6) };
    }
    if (vista === "lista") {
      const hoje = new Date();
      return { inicio: addDias(hoje, -30), fim: addDias(hoje, 90) };
    }
    const ini = inicioDaSemana(inicioDoMes(referencia));
    return { inicio: ini, fim: addDias(ini, 41) };
  }, [vista, referencia]);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const [lista, cont] = await Promise.all([
        listCommitments({ start: iso(janela.inicio), end: iso(janela.fim), only_mine: soMeus }),
        fetchAgendaCounters(),
      ]);
      setItens(lista);
      setContadores(cont);
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar a agenda.");
    } finally {
      setCarregando(false);
    }
  }, [janela.inicio, janela.fim, soMeus]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const porDia = useMemo(() => {
    const mapa = new Map<string, Commitment[]>();
    for (const c of itens) {
      const d = quando(c);
      if (!d) continue;
      const chave = iso(d);
      mapa.set(chave, [...(mapa.get(chave) ?? []), c]);
    }
    return mapa;
  }, [itens]);

  /** Sem data nenhuma: aparece só na Lista, como backlog. Nunca some do sistema. */
  const semData = useMemo(() => itens.filter((c) => !quando(c)), [itens]);

  const dias = useMemo(() => {
    const total = vista === "semana" ? 7 : 42;
    return Array.from({ length: total }, (_, i) => addDias(janela.inicio, i));
  }, [vista, janela.inicio]);

  const titulo =
    vista === "lista"
      ? "Próximos 90 dias"
      : vista === "semana"
        ? `Semana de ${inicioDaSemana(referencia).toLocaleDateString("pt-BR")}`
        : `${MESES[referencia.getMonth()]} de ${referencia.getFullYear()}`;

  async function concluir(c: Commitment) {
    const nota = window.prompt("Observação da conclusão (opcional):", "");
    if (nota === null) return;
    await completeCommitment(c.id, nota.trim() || null);
    setDetalhe(null);
    await carregar();
  }

  async function baixarAnexo(c: Commitment, attId: string, nome: string, mime: string | null) {
    const buscar = async () => {
      const { data } = await api.get<Blob>(commitmentAttachmentUrl(c.id, attId, true), {
        responseType: "blob",
      });
      return data;
    };
    if (canPreviewInBrowser(mime, nome)) await viewFileInNewTab(buscar);
    else saveBlobAsFile(await buscar(), nome);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Agenda</h1>
          <p className="text-sm text-slate-600">
            Reuniões, eventos e obrigações atribuídas a responsáveis, com prazo e ata.
          </p>
        </div>
        {podeEditar ? (
          <button
            type="button"
            onClick={() => {
              setEmEdicao(null);
              setDataPadrao(null);
              setModalAberto(true);
            }}
            className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            + Novo compromisso
          </button>
        ) : null}
      </div>

      {/* Os contadores são o que transforma a agenda em cobrança: quem entra vê o que deve. */}
      {contadores ? (
        <div className="grid grid-cols-2 gap-3 sm:max-w-md">
          <Contador label="Atrasados" valor={contadores.overdue} meus={contadores.overdue_mine} destaque />
          <Contador label="Próximos 7 dias" valor={contadores.this_week} meus={contadores.this_week_mine} />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-lg bg-slate-100 p-0.5">
            {(["mes", "semana", "lista"] as Vista[]).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setVista(v)}
                className={`rounded-md px-3 py-1 text-sm font-medium ${
                  vista === v ? "bg-indigo-600 text-white" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {v === "mes" ? "Mês" : v === "semana" ? "Semana" : "Lista"}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-sm text-slate-700">
            <input type="checkbox" checked={soMeus} onChange={(e) => setSoMeus(e.target.checked)} />
            Só os meus
          </label>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-700">{titulo}</span>
          {vista !== "lista" ? (
            <>
              <button
                type="button"
                onClick={() => setReferencia(addDias(referencia, vista === "mes" ? -30 : -7))}
                className="rounded-lg px-2 py-1 text-sm text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              >
                ‹
              </button>
              <button
                type="button"
                onClick={() => setReferencia(new Date())}
                className="rounded-lg px-2 py-1 text-sm text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              >
                Hoje
              </button>
              <button
                type="button"
                onClick={() => setReferencia(addDias(referencia, vista === "mes" ? 30 : 7))}
                className="rounded-lg px-2 py-1 text-sm text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              >
                ›
              </button>
            </>
          ) : null}
        </div>
      </div>

      {erro ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{erro}</div>
      ) : null}

      {carregando && itens.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-500">Carregando…</p>
      ) : vista === "lista" ? (
        <ListaAgenda itens={itens} semData={semData} onAbrir={setDetalhe} />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            {DIAS.map((d) => (
              <div key={d} className="px-2 py-2 text-center">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {dias.map((dia) => {
              const doDia = porDia.get(iso(dia)) ?? [];
              const foraDoMes = vista === "mes" && dia.getMonth() !== referencia.getMonth();
              const hoje = mesmoDia(dia, new Date());
              return (
                <div
                  key={dia.toISOString()}
                  // Clicar no dia abre o formulário JÁ NAQUELA DATA — é o caminho rápido de
                  // quem está olhando o calendário e quer marcar ali mesmo.
                  onClick={
                    podeEditar
                      ? () => {
                          setEmEdicao(null);
                          setDataPadrao(iso(dia));
                          setModalAberto(true);
                        }
                      : undefined
                  }
                  role={podeEditar ? "button" : undefined}
                  title={podeEditar ? `Novo compromisso em ${dia.toLocaleDateString("pt-BR")}` : undefined}
                  className={`min-h-[6rem] border-b border-r border-slate-100 p-1.5 ${
                    foraDoMes ? "bg-slate-50/60" : ""
                  } ${podeEditar ? "cursor-pointer transition-colors hover:bg-indigo-50/50" : ""}`}
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span
                      className={`inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-xs ${
                        hoje ? "bg-indigo-600 font-semibold text-white" : foraDoMes ? "text-slate-400" : "text-slate-700"
                      }`}
                    >
                      {dia.getDate()}
                    </span>
                  </div>
                  {(() => {
                    // Um dia de reunião gerencial acumula uma dúzia de itens e a célula
                    // esticava, empurrando a semana inteira para baixo. Mostra as primeiras
                    // e guarda o resto atrás de um "+N" — a grade fica legível e nada some.
                    const chave = iso(dia);
                    const aberto = diaAberto === chave;
                    const visiveis =
                      aberto || doDia.length <= CHIPS_POR_DIA
                        ? doDia
                        : doDia.slice(0, CHIPS_POR_DIA);
                    const escondidos = doDia.length - visiveis.length;
                    return (
                      <div className="space-y-1">
                        {visiveis.map((c) => (
                          <Chip key={c.id} c={c} onClick={() => setDetalhe(c)} />
                        ))}
                        {escondidos > 0 || aberto ? (
                          <button
                            type="button"
                            // Sem isto o clique cairia na célula e abriria "novo compromisso".
                            onClick={(e) => {
                              e.stopPropagation();
                              setDiaAberto(aberto ? null : chave);
                            }}
                            className="block w-full rounded px-1.5 py-0.5 text-left text-[11px] font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700"
                          >
                            {aberto ? "mostrar menos" : `+${escondidos} mais`}
                          </button>
                        ) : null}
                      </div>
                    );
                  })()}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {modalAberto ? (
        <CommitmentModal
          commitment={emEdicao}
          defaultDate={dataPadrao}
          onClose={() => setModalAberto(false)}
          onSaved={async () => {
            setModalAberto(false);
            await carregar();
          }}
        />
      ) : null}

      {detalhe ? (
        <DetalheCompromisso
          c={detalhe}
          podeEditar={podeEditar}
          onClose={() => setDetalhe(null)}
          onEditar={() => {
            setEmEdicao(detalhe);
            setDetalhe(null);
            setModalAberto(true);
          }}
          onConcluir={() => void concluir(detalhe)}
          onReabrir={async () => {
            await reopenCommitment(detalhe.id);
            setDetalhe(null);
            await carregar();
          }}
          onExcluir={async () => {
            if (!window.confirm(`Excluir "${detalhe.title}"? Os anexos também serão removidos.`)) return;
            await deleteCommitment(detalhe.id);
            setDetalhe(null);
            await carregar();
          }}
          onAnexo={(attId, nome, mime) => void baixarAnexo(detalhe, attId, nome, mime)}
          onRecarregar={carregar}
        />
      ) : null}
    </div>
  );
}

function ListaAgenda({
  itens,
  semData,
  onAbrir,
}: {
  itens: Commitment[];
  semData: Commitment[];
  onAbrir: (c: Commitment) => void;
}) {
  const comData = itens.filter((c) => quando(c));
  if (comData.length === 0 && semData.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
        Nenhum compromisso no período.
      </div>
    );
  }
  const grupos = new Map<string, Commitment[]>();
  for (const c of comData) {
    const d = quando(c)!;
    const chave = iso(d);
    grupos.set(chave, [...(grupos.get(chave) ?? []), c]);
  }
  return (
    <div className="space-y-3">
      {[...grupos.entries()].sort().map(([chave, doDia]) => (
        <div key={chave} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <p className="border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600">
            {new Date(`${chave}T12:00:00`).toLocaleDateString("pt-BR", {
              weekday: "long", day: "2-digit", month: "long",
            })}
          </p>
          <ul className="divide-y divide-slate-100">
            {doDia.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onAbrir(c)}
                  className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left hover:bg-slate-50"
                >
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${KIND_STYLES[c.kind]}`}>
                    {KIND_LABELS[c.kind]}
                  </span>
                  {hora(c) ? <span className="text-xs tabular-nums text-slate-500">{hora(c)}</span> : null}
                  <span className={`text-sm ${c.status === "CONCLUIDO" ? "text-slate-400 line-through" : "text-slate-800"}`}>
                    {c.title}
                  </span>
                  {c.owner_name ? <span className="text-xs text-slate-500">· {c.owner_name}</span> : null}
                  {c.is_overdue ? (
                    <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-800">
                      atrasado
                    </span>
                  ) : null}
                  {c.attachments.length ? (
                    <span className="text-[10px] text-slate-400">{c.attachments.length} anexo(s)</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {semData.length ? (
        <div className="overflow-hidden rounded-xl border border-dashed border-slate-300 bg-white">
          <p className="border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600">
            Sem data definida
          </p>
          <ul className="divide-y divide-slate-100">
            {semData.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => onAbrir(c)} className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50">
                  {c.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function DetalheCompromisso({
  c,
  podeEditar,
  onClose,
  onEditar,
  onConcluir,
  onReabrir,
  onExcluir,
  onAnexo,
  onRecarregar,
}: {
  c: Commitment;
  podeEditar: boolean;
  onClose: () => void;
  onEditar: () => void;
  onConcluir: () => void;
  onReabrir: () => void | Promise<void>;
  onExcluir: () => void | Promise<void>;
  onAnexo: (attId: string, nome: string, mime: string | null) => void;
  onRecarregar: () => void | Promise<void>;
}) {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviarAnexo(file: File, ata: boolean) {
    setEnviando(true);
    setErro(null);
    try {
      const { uploadCommitmentAttachment } = await import("@/services/projectAgenda");
      await uploadCommitmentAttachment(c.id, file, ata);
      await onRecarregar();
      onClose();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível anexar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/30 p-4">
      {/* Reunião abre mais larga: é ela que carrega a tabela de encaminhamentos, e apertá-la
          numa caixa estreita obrigava a rolar na horizontal para ler a própria ata. */}
      <div
        className={`my-8 w-full rounded-xl bg-white p-6 shadow-xl ${
          c.kind === "REUNIAO" ? "max-w-5xl" : "max-w-2xl"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${KIND_STYLES[c.kind]}`}>
              {KIND_LABELS[c.kind]}
            </span>
            <h3 className="mt-1 text-lg font-semibold text-slate-900">{c.title}</h3>
          </div>
          <button type="button" onClick={onClose} className="rounded px-2 py-1 text-slate-400 hover:bg-slate-100">
            ✕
          </button>
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-x-8 gap-y-4 text-sm sm:grid-cols-3">
          {c.starts_at ? (
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">Quando</dt>
              <dd className="text-slate-800">
                {dataBr(c.starts_at)} {hora(c)}
                {c.duration_minutes ? ` · ${c.duration_minutes} min` : ""}
              </dd>
            </div>
          ) : null}
          {c.due_at ? (
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">Prazo</dt>
              <dd className={c.is_overdue ? "font-medium text-rose-700" : "text-slate-800"}>
                {dataBr(c.due_at)} {c.is_overdue ? "· atrasado" : ""}
              </dd>
            </div>
          ) : null}
          {c.owner_name ? (
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">Responsável</dt>
              <dd className="text-slate-800">{c.owner_name}</dd>
            </div>
          ) : null}
          {c.location ? (
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">Local</dt>
              <dd className="text-slate-800">{c.location}</dd>
            </div>
          ) : null}
          {c.project_name ? (
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-slate-500">Projeto</dt>
              <dd className="text-slate-800">{c.project_name}</dd>
            </div>
          ) : null}
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-slate-500">Situação</dt>
            <dd className="text-slate-800">{c.status === "CONCLUIDO" ? "Concluído" : "Agendado"}</dd>
          </div>
        </dl>

        {c.description ? (
          <p className="mt-3 whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
            {c.description}
          </p>
        ) : null}

        {c.participants.length ? (
          <div className="mt-3">
            <p className="text-[10px] uppercase tracking-wide text-slate-500">Participantes</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {c.participants.map((p) => (
                <span key={p.user_id} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                  {p.full_name}
                </span>
              ))}
              {c.external_participants ? (
                <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-800 ring-1 ring-amber-200">
                  {c.external_participants}
                </span>
              ) : null}
            </div>
          </div>
        ) : null}

        {c.completion_note ? (
          <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
            <strong>Concluído:</strong> {c.completion_note}
          </p>
        ) : null}

        {/* Uma reunião não termina nela: gera encaminhamentos. O bloco fica logo abaixo da ata,
            que é de onde eles saem. */}
        {c.kind === "REUNIAO" ? (
          <MeetingAgendaItems meeting={c} podeEditar={podeEditar} onChanged={onRecarregar} />
        ) : null}

        <div className="mt-4">
          <p className="text-[10px] uppercase tracking-wide text-slate-500">Anexos</p>
          {c.attachments.length ? (
            <ul className="mt-1 divide-y divide-slate-100 rounded-lg border border-slate-200">
              {c.attachments.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm">
                  <span className="truncate text-slate-700">
                    {a.is_minutes ? (
                      <span className="mr-1.5 rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-800">
                        ATA
                      </span>
                    ) : null}
                    {a.file_name}
                  </span>
                  <button
                    type="button"
                    onClick={() => onAnexo(a.id, a.file_name, a.mime_type)}
                    className="shrink-0 rounded px-2 py-0.5 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50"
                  >
                    Ver
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-xs text-slate-500">Nenhum anexo. A ata da reunião entra aqui.</p>
          )}
          {podeEditar ? (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <label className="cursor-pointer rounded-lg px-2 py-1 font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50">
                {enviando ? "Enviando…" : "Anexar ata"}
                <input
                  type="file"
                  className="hidden"
                  disabled={enviando}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void enviarAnexo(f, true);
                  }}
                />
              </label>
              <label className="cursor-pointer rounded-lg px-2 py-1 font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
                Anexar outro documento
                <input
                  type="file"
                  className="hidden"
                  disabled={enviando}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void enviarAnexo(f, false);
                  }}
                />
              </label>
            </div>
          ) : null}
          {erro ? <p className="mt-2 text-xs text-red-700">{erro}</p> : null}
        </div>

        {podeEditar ? (
          <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
            <button type="button" onClick={() => void onExcluir()} className="rounded-lg px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50">
              Excluir
            </button>
            <button type="button" onClick={onEditar} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
              Editar
            </button>
            {c.status === "CONCLUIDO" ? (
              <button type="button" onClick={() => void onReabrir()} className="rounded-lg px-3 py-1.5 text-sm font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50">
                Reabrir
              </button>
            ) : (
              <button type="button" onClick={onConcluir} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700">
                Concluir
              </button>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
