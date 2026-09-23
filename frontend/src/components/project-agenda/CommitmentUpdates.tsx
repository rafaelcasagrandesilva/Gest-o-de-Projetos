import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { useAuth } from "@/context/AuthContext";
import { hasPermission } from "@/permissions";
import { formatApiError } from "@/utils/apiError";
import {
  addCommitmentUpdate,
  deleteCommitmentUpdate,
  listCommitmentUpdates,
  UPDATE_KIND_LABELS,
  UPDATE_KIND_STYLES,
  type CommitmentUpdate,
} from "@/services/projectAgenda";

/**
 * Andamentos de um item — a linha do tempo do que foi dito e feito sobre ele.
 *
 * Substitui o hábito de acumular tudo no campo "Ação": cada registro tem tipo, autor, data e a
 * reunião em que foi dito. Conclusões entram sozinhas, pela caixa de concluir; aqui se registram
 * Atualizações (o que avançou / o que falta). Observações antigas seguem visíveis no histórico.
 */

function dataHora(raw: string): string {
  const d = new Date(raw);
  return `${d.toLocaleDateString("pt-BR")} ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

function dataBr(raw: string): string {
  return new Date(`${raw}T12:00:00`).toLocaleDateString("pt-BR");
}

/** Um andamento, compacto — usado na linha da pauta (o mais recente) e na linha do tempo. */
export function UpdateEntry({ u, compact = false }: { u: CommitmentUpdate; compact?: boolean }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
        <span className={`rounded-full px-1.5 py-px text-[10px] font-medium ring-1 ${UPDATE_KIND_STYLES[u.kind]}`}>
          {UPDATE_KIND_LABELS[u.kind]}
        </span>
        <span>{u.author_name ?? "—"}</span>
        <span>·</span>
        <span className="tabular-nums">{dataHora(u.created_at)}</span>
        {u.meeting_date ? <span>· reunião de {dataBr(u.meeting_date)}</span> : null}
      </div>
      <p className={`mt-0.5 whitespace-pre-wrap text-slate-700 ${compact ? "line-clamp-2 text-xs" : "text-sm"}`}>
        {u.body}
      </p>
    </div>
  );
}

export function CommitmentUpdates({
  commitmentId,
  meetingId = null,
  podeEditar,
  onChanged,
}: {
  commitmentId: string;
  /** Reunião em que o andamento está sendo registrado (na pauta); fora dela, nenhuma. */
  meetingId?: string | null;
  podeEditar: boolean;
  onChanged?: () => void | Promise<void>;
}) {
  const { user } = useAuth();
  const podeExcluirQualquer = hasPermission(user?.permission_names, "project_agenda.delete");
  const [lista, setLista] = useState<CommitmentUpdate[] | null>(null);
  const [texto, setTexto] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setLista(await listCommitmentUpdates(commitmentId));
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar os andamentos.");
      setLista([]);
    }
  }, [commitmentId]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function registrar() {
    if (!texto.trim()) return;
    setSalvando(true);
    setErro(null);
    try {
      setLista(await addCommitmentUpdate(commitmentId, { kind: "ATUALIZACAO", body: texto.trim(), meeting_id: meetingId }));
      setTexto("");
      await onChanged?.();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível registrar.");
    } finally {
      setSalvando(false);
    }
  }

  async function excluir(u: CommitmentUpdate) {
    setErro(null);
    try {
      await deleteCommitmentUpdate(u.id);
      await carregar();
      await onChanged?.();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível excluir.");
    }
  }

  return (
    <div>
      {podeEditar ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          {/* Só "Atualização": Observação × Atualização ficava ambíguo na prática. As
              observações antigas continuam no histórico com a etiqueta delas. */}
          <p className="mb-1.5 text-xs font-medium text-slate-600">Atualização</p>
          <textarea
            rows={3}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="O que avançou e o que ainda falta…"
            className="block w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm"
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <p className="text-[11px] text-slate-500">
              {meetingId ? "Fica registrado como dito nesta reunião." : "Registrado fora de reunião."}
            </p>
            <button
              type="button"
              disabled={salvando || !texto.trim()}
              onClick={() => void registrar()}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {salvando ? "Registrando…" : "Registrar atualização"}
            </button>
          </div>
        </div>
      ) : null}

      {erro ? <p className="mt-2 text-xs text-red-700">{erro}</p> : null}

      <div className="mt-3">
        {lista === null ? (
          <p className="py-3 text-center text-xs text-slate-500">Carregando…</p>
        ) : lista.length === 0 ? (
          <p className="py-3 text-center text-xs text-slate-500">Nenhum andamento registrado ainda.</p>
        ) : (
          <ol className="space-y-3 border-l-2 border-slate-200 pl-3">
            {lista.map((u) => (
              <li key={u.id} className="relative">
                <span className="absolute -left-[17px] top-1.5 h-2 w-2 rounded-full bg-slate-300" />
                <div className="flex items-start justify-between gap-2">
                  <UpdateEntry u={u} />
                  {podeEditar && (u.author_id === user?.id || podeExcluirQualquer) ? (
                    <button
                      type="button"
                      onClick={() => void excluir(u)}
                      className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-red-50 hover:text-red-600"
                      title="Excluir andamento"
                    >
                      Excluir
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
