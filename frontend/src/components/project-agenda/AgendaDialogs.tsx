import { useEffect, useState, type ReactNode } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import {
  KIND_LABELS,
  KIND_STYLES,
  linkMeetingItem,
  listOpenCommitments,
  listUpcomingMeetings,
  type Commitment,
  type MeetingOption,
} from "@/services/projectAgenda";

/**
 * Caixas de diálogo da Agenda — do próprio sistema, nunca `window.prompt`/`confirm` do navegador.
 * Ficam por cima do detalhe do compromisso (z-[60]), que já é um modal.
 */

function dataBr(raw: string | null): string {
  if (!raw) return "—";
  return new Date(raw).toLocaleDateString("pt-BR");
}

export function Dialog({
  title,
  subtitle,
  children,
  footer,
  onClose,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer: ReactNode;
  onClose: () => void;
  wide?: boolean | "xl";
}) {
  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/40 p-4" onClick={onClose}>
      <div
        className={`my-10 w-full rounded-xl bg-white shadow-xl ${
          wide === "xl" ? "max-w-4xl" : wide ? "max-w-2xl" : "max-w-lg"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-slate-900">{title}</h3>
            {subtitle ? <p className="mt-0.5 truncate text-sm text-slate-500">{subtitle}</p> : null}
          </div>
          <button type="button" onClick={onClose} className="rounded px-2 py-1 text-slate-400 hover:bg-slate-100">
            ✕
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</div>
      </div>
    </div>
  );
}

/** Caixa de texto de um desfecho: Concluir ("o que gerou a conclusão") ou Parcial ("o que avançou"). */
export function OutcomeNoteDialog({
  title,
  itemTitle,
  label,
  placeholder,
  confirmLabel,
  tone = "emerald",
  option,
  onConfirm,
  onClose,
}: {
  title: string;
  itemTitle: string;
  label: string;
  placeholder: string;
  confirmLabel: string;
  tone?: "emerald" | "amber";
  /** Caixa de marcar opcional (ex.: concluir junto as obrigações em aberto). Começa marcada. */
  option?: string;
  onConfirm: (note: string | null, optionChecked: boolean) => Promise<void>;
  onClose: () => void;
}) {
  const [nota, setNota] = useState("");
  const [marcado, setMarcado] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function confirmar() {
    setSalvando(true);
    setErro(null);
    try {
      await onConfirm(nota.trim() || null, Boolean(option) && marcado);
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar.");
      setSalvando(false);
    }
  }

  const botao =
    tone === "amber" ? "bg-amber-600 hover:bg-amber-700" : "bg-emerald-600 hover:bg-emerald-700";

  return (
    <Dialog
      title={title}
      subtitle={itemTitle}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100">
            Cancelar
          </button>
          <button
            type="button"
            disabled={salvando}
            onClick={() => void confirmar()}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 ${botao}`}
          >
            {salvando ? "Salvando…" : confirmLabel}
          </button>
        </>
      }
    >
      <label className="block text-xs font-medium text-slate-600">
        {label} <span className="font-normal text-slate-400">(opcional)</span>
        <textarea
          autoFocus
          rows={4}
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          placeholder={placeholder}
          className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
        />
      </label>
      <p className="mt-1.5 text-[11px] text-slate-500">O texto entra no histórico do item.</p>
      {option ? (
        <label className="mt-3 flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <input type="checkbox" checked={marcado} onChange={(e) => setMarcado(e.target.checked)} />
          {option}
        </label>
      ) : null}
      {erro ? <p className="mt-2 text-xs text-red-700">{erro}</p> : null}
    </Dialog>
  );
}

/** Concluir um compromisso, uma obrigação ou um item de pauta: pede o que gerou a conclusão. */
export function ConcludeDialog({
  itemTitle,
  openObligations = 0,
  onConfirm,
  onClose,
}: {
  itemTitle: string;
  /** Item de pauta com obrigações em aberto: oferece concluí-las junto. */
  openObligations?: number;
  onConfirm: (note: string | null, completeObligations: boolean) => Promise<void>;
  onClose: () => void;
}) {
  return (
    <OutcomeNoteDialog
      title="Concluir"
      itemTitle={itemTitle}
      label="O que gerou a conclusão?"
      placeholder="Ex.: documentos entregues ao Kleison em 16/09."
      confirmLabel="Concluir"
      option={
        openObligations > 0
          ? `Concluir também ${openObligations === 1 ? "a obrigação em aberto" : `as ${openObligations} obrigações em aberto`}`
          : undefined
      }
      onConfirm={onConfirm}
      onClose={onClose}
    />
  );
}

/** Alterar o prazo de uma obrigação: novo prazo e o motivo (vão para o histórico do item). */
export function RescheduleDialog({
  itemTitle,
  currentDue,
  onConfirm,
  onClose,
}: {
  itemTitle: string;
  currentDue: string | null;
  onConfirm: (dueDate: string, reason: string | null) => Promise<void>;
  onClose: () => void;
}) {
  const [data, setData] = useState(() => {
    if (!currentDue) return "";
    const d = new Date(currentDue);
    const p = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  });
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function confirmar() {
    if (!data) return;
    setSalvando(true);
    setErro(null);
    try {
      await onConfirm(data, motivo.trim() || null);
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível alterar o prazo.");
      setSalvando(false);
    }
  }

  return (
    <Dialog
      title="Alterar prazo"
      subtitle={itemTitle}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100">
            Cancelar
          </button>
          <button
            type="button"
            disabled={salvando || !data}
            onClick={() => void confirmar()}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {salvando ? "Salvando…" : "Alterar prazo"}
          </button>
        </>
      }
    >
      <div className="grid gap-3">
        <label className="block text-xs font-medium text-slate-600">
          Novo prazo
          <input
            type="date"
            value={data}
            onChange={(e) => setData(e.target.value)}
            className="mt-1 block w-44 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Motivo <span className="font-normal text-slate-400">(opcional)</span>
          <textarea
            rows={3}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ex.: aguardando retorno do contador."
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
          />
        </label>
      </div>
      <p className="mt-1.5 text-[11px] text-slate-500">A alteração (de → para) entra no histórico do item.</p>
      {erro ? <p className="mt-2 text-xs text-red-700">{erro}</p> : null}
    </Dialog>
  );
}

/** "Levar para reunião": escolhe a reunião em cuja pauta o compromisso vai entrar. */
export function LinkToMeetingDialog({
  commitment,
  onLinked,
  onClose,
}: {
  commitment: Commitment;
  onLinked: () => Promise<void>;
  onClose: () => void;
}) {
  const [reunioes, setReunioes] = useState<MeetingOption[] | null>(null);
  const [escolhida, setEscolhida] = useState<string>("");
  /** Reuniões em cuja pauta o item já está — aparecem, mas não dá para escolher de novo. */
  const jaNaPauta = new Set((commitment.agenda_meetings ?? []).map((p) => p.meeting_id));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    void listUpcomingMeetings()
      .then((rows) => {
        setReunioes(rows);
        const livre = rows.find((r) => !jaNaPauta.has(r.id));
        if (livre) setEscolhida(livre.id);
      })
      .catch(() => setReunioes([]));
  }, []);

  async function confirmar() {
    if (!escolhida) return;
    setSalvando(true);
    setErro(null);
    try {
      await linkMeetingItem(escolhida, commitment.id);
      await onLinked();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível levar para a reunião.");
      setSalvando(false);
    }
  }

  return (
    <Dialog
      title="Levar para reunião"
      subtitle={commitment.title}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100">
            Cancelar
          </button>
          <button
            type="button"
            disabled={salvando || !escolhida}
            onClick={() => void confirmar()}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {salvando ? "Levando…" : "Colocar na pauta"}
          </button>
        </>
      }
    >
      <p className="mb-2 text-xs text-slate-600">
        O compromisso entra na pauta da reunião escolhida e passa a seguir o ritmo dela (concluir, parcial,
        estender para a próxima).
      </p>
      {reunioes === null ? (
        <p className="py-4 text-center text-xs text-slate-500">Carregando reuniões…</p>
      ) : reunioes.length === 0 ? (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Não há reunião de hoje em diante. Marque a reunião na agenda primeiro.
        </p>
      ) : (
        <ul className="max-h-72 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
          {reunioes.map((r) => {
            const ja = jaNaPauta.has(r.id);
            return (
              <li key={r.id}>
                <label
                  className={`flex items-center gap-3 px-3 py-2 text-sm ${
                    ja ? "cursor-not-allowed bg-slate-50 text-slate-400" : "cursor-pointer hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="radio"
                    name="reuniao"
                    disabled={ja}
                    checked={escolhida === r.id}
                    onChange={() => setEscolhida(r.id)}
                  />
                  <span className="w-24 shrink-0 tabular-nums text-slate-600">{dataBr(r.starts_at)}</span>
                  <span className={`truncate ${ja ? "text-slate-400" : "text-slate-800"}`}>{r.title}</span>
                  {ja ? (
                    <span className="ml-auto shrink-0 rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700 ring-1 ring-indigo-200">
                      já está na pauta
                    </span>
                  ) : null}
                </label>
              </li>
            );
          })}
        </ul>
      )}
      {erro ? <p className="mt-2 text-xs text-red-700">{erro}</p> : null}
    </Dialog>
  );
}

/** "+ Item existente" na pauta: busca compromissos em aberto e traz para esta reunião. */
export function AddExistingItemDialog({
  meetingId,
  onAdded,
  onClose,
}: {
  meetingId: string;
  onAdded: () => Promise<void>;
  onClose: () => void;
}) {
  const [busca, setBusca] = useState("");
  const [lista, setLista] = useState<Commitment[] | null>(null);
  const [adicionando, setAdicionando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    const t = setTimeout(() => {
      void listOpenCommitments({ meetingId, q: busca })
        .then((rows) => vivo && setLista(rows))
        .catch(() => vivo && setLista([]));
    }, 250);
    return () => {
      vivo = false;
      clearTimeout(t);
    };
  }, [meetingId, busca]);

  async function adicionar(c: Commitment) {
    setAdicionando(c.id);
    setErro(null);
    try {
      await linkMeetingItem(meetingId, c.id);
      setLista((prev) => (prev ?? []).filter((x) => x.id !== c.id));
      await onAdded();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível adicionar.");
    } finally {
      setAdicionando(null);
    }
  }

  return (
    <Dialog
      title="Adicionar item existente à pauta"
      subtitle="Compromissos em aberto criados no calendário ou em outras reuniões"
      wide
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
          Fechar
        </button>
      }
    >
      <input
        autoFocus
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
        placeholder="Buscar pelo assunto…"
        className="block w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm"
      />
      <div className="mt-3 max-h-80 overflow-y-auto rounded-lg border border-slate-200">
        {lista === null ? (
          <p className="py-4 text-center text-xs text-slate-500">Carregando…</p>
        ) : lista.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">Nenhum compromisso em aberto encontrado.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {lista.map((c) => (
              <li key={c.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${KIND_STYLES[c.kind]}`}>
                  {KIND_LABELS[c.kind]}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-slate-800">{c.title}</p>
                  <p className="text-[11px] text-slate-500">
                    {c.owner_name ?? "Sem responsável"} · prazo{" "}
                    <span className={`tabular-nums ${c.is_overdue ? "text-rose-700" : ""}`}>{dataBr(c.due_at ?? c.starts_at)}</span>
                  </p>
                </div>
                <button
                  type="button"
                  disabled={adicionando !== null}
                  onClick={() => void adicionar(c)}
                  className="shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
                >
                  {adicionando === c.id ? "Adicionando…" : "Adicionar"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {erro ? <p className="mt-2 text-xs text-red-700">{erro}</p> : null}
    </Dialog>
  );
}
