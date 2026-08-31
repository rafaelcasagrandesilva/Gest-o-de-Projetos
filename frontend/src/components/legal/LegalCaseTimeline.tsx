import { useCallback, useEffect, useState } from "react";
import { formatApiError } from "@/utils/apiError";
import { addCaseNote, fetchCaseTimeline, type LegalTimelineEntry } from "@/services/legalOperation";

/**
 * Timeline do processo — o histórico oficial (M3).
 *
 * Só FATOS consumados: compromisso futuro mora na agenda (M4). A entrada não se edita — corrigir
 * é registrar um fato novo (O6) —, por isso aqui só existe "acrescentar".
 */

const TIPO_ROTULO: Record<string, string> = {
  CARGA_INICIAL: "Carga inicial",
  ANDAMENTO: "Andamento",
  EVENTO_REALIZADO: "Evento",
  MUDANCA_ESTADO: "Estado",
  DOCUMENTO: "Documento",
  NOTA: "Observação",
  FINANCEIRO: "Financeiro",
  BLOQUEIO: "Bloqueio",
};

const TIPO_COR: Record<string, string> = {
  CARGA_INICIAL: "bg-slate-100 text-slate-600 border-slate-200",
  ANDAMENTO: "bg-sky-100 text-sky-800 border-sky-200",
  EVENTO_REALIZADO: "bg-indigo-100 text-indigo-800 border-indigo-200",
  MUDANCA_ESTADO: "bg-violet-100 text-violet-800 border-violet-200",
  DOCUMENTO: "bg-slate-100 text-slate-700 border-slate-200",
  NOTA: "bg-amber-50 text-amber-800 border-amber-200",
  FINANCEIRO: "bg-emerald-100 text-emerald-800 border-emerald-200",
  BLOQUEIO: "bg-red-100 text-red-800 border-red-200",
};

export function LegalCaseTimeline({ caseId, canWrite }: { caseId: string; canWrite: boolean }) {
  const [entries, setEntries] = useState<LegalTimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [novaNota, setNovaNota] = useState("");
  const [salvando, setSalvando] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await fetchCaseTimeline(caseId));
      setError(null);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleAdd() {
    const texto = novaNota.trim();
    if (!texto) return;
    setSalvando(true);
    try {
      await addCaseNote(caseId, { title: texto });
      setNovaNota("");
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Linha do tempo
        </h3>
        <span className="text-[11px] text-slate-400">
          {entries.length} {entries.length === 1 ? "fato" : "fatos"}
        </span>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
          {error}
        </div>
      )}

      {canWrite && (
        <div className="mb-4 flex gap-2">
          <input
            value={novaNota}
            onChange={(e) => setNovaNota(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleAdd();
            }}
            placeholder="Registrar um fato ou observação…"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
          <button
            type="button"
            disabled={salvando || !novaNota.trim()}
            onClick={() => void handleAdd()}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            Registrar
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Carregando…</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-slate-500">Nenhum fato registrado.</p>
      ) : (
        <ol className="relative space-y-4 border-l border-slate-200 pl-5">
          {entries.map((e) => (
            <li key={e.id} className="relative">
              <span
                className={`absolute -left-[23px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-white ${
                  e.is_milestone ? "bg-indigo-600" : "bg-slate-300"
                }`}
              />
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium tabular-nums text-slate-500">
                  {new Date(e.occurred_at).toLocaleDateString("pt-BR")}
                </span>
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
                    TIPO_COR[e.entry_type] ?? TIPO_COR.NOTA
                  }`}
                >
                  {TIPO_ROTULO[e.entry_type] ?? e.entry_type}
                </span>
                {e.source === "CARGA_INICIAL" && (
                  <span className="text-[10px] text-slate-400">importado</span>
                )}
              </div>
              <p className="mt-0.5 text-sm text-slate-800">{e.title}</p>
              {e.description && (
                <p className="mt-0.5 whitespace-pre-line text-xs text-slate-500">{e.description}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
