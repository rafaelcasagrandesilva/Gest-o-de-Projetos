import { useCallback, useEffect, useMemo, useState } from "react";
import { formatApiError } from "@/utils/apiError";
import { LegalEventForm } from "@/components/legal/LegalEventForm";
import {
  concludeEvent,
  listEvents,
  rescheduleEvent,
  EVENT_TYPE_LABELS,
  type LegalEvent,
} from "@/services/legalOperation";

/**
 * Agenda — visualização dos EVENTOS (M4). Não é uma entidade própria: mês, semana e lista são
 * três recortes do mesmo dado.
 *
 * Adiar não apaga (O7): o evento antigo fica ADIADO apontando o novo, e os dois aparecem.
 */

type Vista = "mes" | "semana" | "lista";

const TIPO_CORES: Record<string, string> = {
  AUDIENCIA: "bg-indigo-100 text-indigo-800 border-indigo-200",
  PERICIA: "bg-violet-100 text-violet-800 border-violet-200",
  SESSAO_ARBITRAL: "bg-sky-100 text-sky-800 border-sky-200",
  REUNIAO: "bg-slate-100 text-slate-700 border-slate-200",
  PRAZO_PROCESSUAL: "bg-red-100 text-red-800 border-red-200",
  PRAZO_INTERNO: "bg-amber-100 text-amber-800 border-amber-200",
  DILIGENCIA: "bg-emerald-100 text-emerald-800 border-emerald-200",
  OUTRO: "bg-slate-100 text-slate-700 border-slate-200",
};

function inicioDoMes(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function inicioDaSemana(d: Date): Date {
  const copy = new Date(d);
  copy.setDate(copy.getDate() - copy.getDay());
  copy.setHours(0, 0, 0, 0);
  return copy;
}
function addDias(d: Date, n: number): Date {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}
function mesmoDia(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString();
}
function hora(iso: string | null): string {
  return iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
}

export function LegalAgenda() {
  // Semana é o padrão (a especificação operacional define assim): é o horizonte de quem
  // trabalha. Mês serve para planejar, lista para conferir.
  const [vista, setVista] = useState<Vista>("semana");
  const [referencia, setReferencia] = useState(() => new Date());
  const [eventos, setEventos] = useState<LegalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [diaSelecionado, setDiaSelecionado] = useState<Date | undefined>();
  const [busyId, setBusyId] = useState<string | null>(null);

  const janela = useMemo(() => {
    if (vista === "semana") {
      const inicio = inicioDaSemana(referencia);
      return { inicio, fim: addDias(inicio, 7) };
    }
    if (vista === "lista") {
      const inicio = new Date();
      inicio.setHours(0, 0, 0, 0);
      return { inicio, fim: addDias(inicio, 90) };
    }
    const primeiro = inicioDoMes(referencia);
    return { inicio: addDias(primeiro, -primeiro.getDay()), fim: addDias(primeiro, 42) };
  }, [vista, referencia]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEventos(await listEvents(janela.inicio, janela.fim));
      setError(null);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [janela.inicio, janela.fim]);

  useEffect(() => {
    void load();
  }, [load]);

  const porDia = useMemo(() => {
    const mapa = new Map<string, LegalEvent[]>();
    for (const e of eventos) {
      if (!e.scheduled_for) continue;
      const chave = new Date(e.scheduled_for).toDateString();
      mapa.set(chave, [...(mapa.get(chave) ?? []), e]);
    }
    return mapa;
  }, [eventos]);

  async function handleConcluir(id: string) {
    setBusyId(id);
    try {
      await concludeEvent(id, null);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  async function handleAdiar(ev: LegalEvent) {
    const nova = window.prompt("Nova data e hora (AAAA-MM-DD HH:MM):", "");
    if (!nova) return;
    const parsed = new Date(nova.replace(" ", "T"));
    if (Number.isNaN(parsed.getTime())) {
      setError("Data inválida. Use o formato AAAA-MM-DD HH:MM.");
      return;
    }
    const motivo = window.prompt("Motivo do adiamento (opcional):", "") || null;
    setBusyId(ev.id);
    try {
      await rescheduleEvent(ev.id, parsed.toISOString(), motivo);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  const tituloPeriodo =
    vista === "lista"
      ? "Próximos 90 dias"
      : vista === "semana"
        ? `Semana de ${inicioDaSemana(referencia).toLocaleDateString("pt-BR")}`
        : referencia.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Agenda</h2>
          <p className="text-sm text-slate-500">
            Audiências, perícias, prazos e reuniões. O calendário é uma visualização dos compromissos.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setDiaSelecionado(undefined);
            setShowForm(true);
          }}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700"
        >
          + Novo compromisso
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
          {(["mes", "semana", "lista"] as Vista[]).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setVista(v)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                vista === v ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {v === "mes" ? "Mês" : v === "semana" ? "Semana" : "Lista"}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-700 first-letter:uppercase">{tituloPeriodo}</span>
          {vista !== "lista" && (
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => setReferencia(addDias(referencia, vista === "mes" ? -30 : -7))}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-sm text-slate-600 hover:bg-slate-50"
              >
                ‹
              </button>
              <button
                type="button"
                onClick={() => setReferencia(new Date())}
                className="rounded-lg border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50"
              >
                Hoje
              </button>
              <button
                type="button"
                onClick={() => setReferencia(addDias(referencia, vista === "mes" ? 30 : 7))}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-sm text-slate-600 hover:bg-slate-50"
              >
                ›
              </button>
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <p className="text-slate-500">Carregando…</p>
      ) : vista === "mes" ? (
        <MesGrid
          referencia={referencia}
          porDia={porDia}
          onDiaClick={(dia) => {
            setDiaSelecionado(dia);
            setShowForm(true);
          }}
        />
      ) : vista === "semana" ? (
        <SemanaGrid referencia={referencia} porDia={porDia} />
      ) : (
        <ListaEventos
          eventos={eventos}
          busyId={busyId}
          onConcluir={handleConcluir}
          onAdiar={handleAdiar}
        />
      )}

      {showForm && (
        <LegalEventForm
          initialDate={diaSelecionado}
          onClose={() => setShowForm(false)}
          onCreated={() => void load()}
        />
      )}
    </div>
  );
}

function Chip({ ev }: { ev: LegalEvent }) {
  const cor = TIPO_CORES[ev.event_type] ?? TIPO_CORES.OUTRO;
  const adiado = ev.status === "ADIADO";
  const realizado = ev.status === "REALIZADO";
  return (
    <div
      title={`${ev.title}${ev.case_number ? ` · ${ev.case_number}` : ""}`}
      className={`truncate rounded border px-1.5 py-0.5 text-[11px] ${cor} ${
        adiado ? "line-through opacity-60" : ""
      } ${realizado ? "opacity-60" : ""}`}
    >
      <span className="font-medium tabular-nums">{hora(ev.scheduled_for)}</span> {ev.title}
    </div>
  );
}

function MesGrid({
  referencia,
  porDia,
  onDiaClick,
}: {
  referencia: Date;
  porDia: Map<string, LegalEvent[]>;
  onDiaClick: (d: Date) => void;
}) {
  const primeiro = inicioDoMes(referencia);
  const inicio = addDias(primeiro, -primeiro.getDay());
  const hoje = new Date();
  const dias = Array.from({ length: 42 }, (_, i) => addDias(inicio, i));

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50/80">
        {["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"].map((d) => (
          <div key={d} className="px-2 py-2 text-center text-[11px] font-medium uppercase text-slate-500">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {dias.map((dia) => {
          const doMes = dia.getMonth() === referencia.getMonth();
          const eventos = porDia.get(dia.toDateString()) ?? [];
          const ehHoje = mesmoDia(dia, hoje);
          return (
            <button
              key={dia.toISOString()}
              type="button"
              onClick={() => onDiaClick(dia)}
              className={`min-h-[92px] border-b border-r border-slate-100 p-1.5 text-left align-top transition hover:bg-indigo-50/40 ${
                doMes ? "bg-white" : "bg-slate-50/60"
              }`}
            >
              <span
                className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs tabular-nums ${
                  ehHoje
                    ? "bg-indigo-600 font-semibold text-white"
                    : doMes
                      ? "text-slate-700"
                      : "text-slate-400"
                }`}
              >
                {dia.getDate()}
              </span>
              <div className="mt-1 space-y-1">
                {eventos.slice(0, 3).map((ev) => (
                  <Chip key={ev.id} ev={ev} />
                ))}
                {eventos.length > 3 && (
                  <p className="text-[11px] text-slate-500">+{eventos.length - 3} mais</p>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SemanaGrid({ referencia, porDia }: { referencia: Date; porDia: Map<string, LegalEvent[]> }) {
  const inicio = inicioDaSemana(referencia);
  const hoje = new Date();
  const dias = Array.from({ length: 7 }, (_, i) => addDias(inicio, i));

  return (
    <div className="grid gap-3 md:grid-cols-7">
      {dias.map((dia) => {
        const eventos = porDia.get(dia.toDateString()) ?? [];
        const ehHoje = mesmoDia(dia, hoje);
        return (
          <div
            key={dia.toISOString()}
            className={`rounded-xl border bg-white p-3 shadow-sm ${
              ehHoje ? "border-indigo-300 ring-1 ring-indigo-100" : "border-slate-200"
            }`}
          >
            <p className="text-[11px] uppercase text-slate-500">
              {dia.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "")}
            </p>
            <p className={`text-lg font-semibold tabular-nums ${ehHoje ? "text-indigo-700" : "text-slate-800"}`}>
              {dia.getDate()}
            </p>
            <div className="mt-2 space-y-1.5">
              {eventos.length === 0 ? (
                <p className="text-[11px] text-slate-400">—</p>
              ) : (
                eventos.map((ev) => <Chip key={ev.id} ev={ev} />)
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ListaEventos({
  eventos,
  busyId,
  onConcluir,
  onAdiar,
}: {
  eventos: LegalEvent[];
  busyId: string | null;
  onConcluir: (id: string) => void;
  onAdiar: (ev: LegalEvent) => void;
}) {
  if (eventos.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500 shadow-sm">
        Nenhum compromisso nos próximos 90 dias.
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50/80">
          <tr>
            <th className="px-4 py-3 font-medium text-slate-600">Data</th>
            <th className="px-4 py-3 font-medium text-slate-600">Tipo</th>
            <th className="px-4 py-3 font-medium text-slate-600">Compromisso</th>
            <th className="px-4 py-3 font-medium text-slate-600">Processo</th>
            <th className="px-4 py-3 font-medium text-slate-600">Local</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {eventos.map((ev) => (
            <tr key={ev.id} className="border-b border-slate-50 last:border-0">
              <td className="whitespace-nowrap px-4 py-3 tabular-nums text-slate-700">
                {ev.scheduled_for
                  ? new Date(ev.scheduled_for).toLocaleDateString("pt-BR")
                  : "sem data"}
                <span className="ml-1 text-slate-400">{hora(ev.scheduled_for)}</span>
              </td>
              <td className="px-4 py-3">
                <span
                  className={`rounded border px-1.5 py-0.5 text-[11px] ${
                    TIPO_CORES[ev.event_type] ?? TIPO_CORES.OUTRO
                  }`}
                >
                  {EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}
                </span>
              </td>
              <td className="max-w-[280px] truncate px-4 py-3 text-slate-800">
                {ev.title}
                {ev.status === "ADIADO" && (
                  <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">adiado</span>
                )}
                {ev.status === "REALIZADO" && (
                  <span className="ml-2 rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-700">
                    realizado
                  </span>
                )}
              </td>
              <td className="max-w-[200px] truncate px-4 py-3 text-slate-600">
                {ev.case_number ?? "—"}
                {ev.claimant ? <span className="text-slate-400"> · {ev.claimant}</span> : null}
              </td>
              <td className="max-w-[180px] truncate px-4 py-3 text-slate-500">{ev.location ?? "—"}</td>
              <td className="whitespace-nowrap px-4 py-3 text-right">
                {ev.status === "AGENDADO" && (
                  <>
                    <button
                      type="button"
                      disabled={busyId === ev.id}
                      onClick={() => onConcluir(ev.id)}
                      className="text-xs text-slate-600 hover:text-slate-900 disabled:opacity-50"
                    >
                      Concluir
                    </button>
                    <button
                      type="button"
                      disabled={busyId === ev.id}
                      onClick={() => onAdiar(ev)}
                      className="ml-3 text-xs text-amber-700 hover:underline disabled:opacity-50"
                    >
                      Adiar
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
