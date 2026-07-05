import { useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  initializeCompetencia,
  type CostCategory,
  type InitializeCompetenciaResult,
  type InitializeOrigin,
} from "@/services/projectStructure";

const MONTHS_PT = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

/** "YYYY-MM-DD" → "Julho/2026" (opcionalmente do mês anterior). */
function monthLabel(competencia: string, previous = false): string {
  const [y, m] = competencia.split("-").map(Number);
  const d = new Date(y, (m - 1) - (previous ? 1 : 0), 1);
  return `${MONTHS_PT[d.getMonth()]}/${d.getFullYear()}`;
}

const CATEGORIES: { id: CostCategory; label: string }[] = [
  { id: "labor", label: "Mão de obra" },
  { id: "vehicles", label: "Veículos" },
  { id: "systems", label: "Sistemas" },
  { id: "misc", label: "Custos diversos" },
];

/**
 * Modal reutilizável "Inicializar Competência" — o MESMO modal para todas as abas
 * de custo do projeto (mão de obra, veículos, sistemas, custos diversos). O
 * frontend apenas orquestra: a cópia é feita 100% pelo backend.
 */
export function InitializeCompetenciaModal({
  open,
  onClose,
  projectId,
  competencia,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  /** competência destino "YYYY-MM-DD" (mês atual da tela) */
  competencia: string;
  onDone: (result: InitializeCompetenciaResult) => void;
}) {
  const [origin, setOrigin] = useState<InitializeOrigin>("previous_realizado");
  const [selected, setSelected] = useState<Set<CostCategory>>(
    () => new Set<CostCategory>(CATEGORIES.map((c) => c.id)),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reabre sempre com o padrão (todas as categorias, origem = comportamento atual).
  useEffect(() => {
    if (open) {
      setOrigin("previous_realizado");
      setSelected(new Set(CATEGORIES.map((c) => c.id)));
      setError(null);
      setBusy(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [open, busy, onClose]);

  const curLabel = useMemo(() => monthLabel(competencia), [competencia]);
  const prevLabel = useMemo(() => monthLabel(competencia, true), [competencia]);

  const origins: { id: InitializeOrigin; title: string; from: string; to: string }[] = [
    { id: "previous_realizado", title: "Realizado da competência anterior", from: `${prevLabel} (Realizado)`, to: `${curLabel} (Realizado)` },
    { id: "current_previsto", title: "Previsto da competência atual", from: `${curLabel} (Previsto)`, to: `${curLabel} (Realizado)` },
    { id: "previous_previsto", title: "Previsto da competência anterior", from: `${prevLabel} (Previsto)`, to: `${curLabel} (Previsto)` },
  ];

  function toggle(id: CostCategory) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function confirm() {
    if (selected.size === 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await initializeCompetencia(projectId, {
        competencia,
        origin,
        categories: CATEGORIES.map((c) => c.id).filter((id) => selected.has(id)),
      });
      onDone(result);
      onClose();
    } catch (e) {
      if (isAxiosError(e) && e.response?.data?.detail) {
        const d = e.response.data.detail;
        setError(typeof d === "string" ? d : "Não foi possível inicializar. Tente novamente.");
      } else {
        setError("Não foi possível inicializar. Tente novamente.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div className="flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-900">Inicializar Competência</h2>
          <p className="mt-1 text-sm text-slate-500">
            Selecione a origem dos dados e quais categorias deseja copiar para esta competência.
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">Origem dos dados</legend>
            <div className="mt-2 space-y-2">
              {origins.map((o) => (
                <label
                  key={o.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${
                    origin === o.id ? "border-indigo-500 bg-indigo-50/50" : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="radio"
                    name="origin"
                    checked={origin === o.id}
                    onChange={() => setOrigin(o.id)}
                    className="mt-0.5 accent-indigo-600"
                  />
                  <span className="min-w-0">
                    <span className="block font-medium text-slate-900">{o.title}</span>
                    <span className="mt-0.5 block text-xs text-slate-500">
                      {o.from} <span aria-hidden>→</span> {o.to}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="mt-4">
            <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">Categorias</legend>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {CATEGORIES.map((c) => (
                <label
                  key={c.id}
                  className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 hover:bg-slate-50"
                >
                  <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} className="accent-indigo-600" />
                  {c.label}
                </label>
              ))}
            </div>
            <p className="mt-2 text-xs text-slate-500">
              As categorias selecionadas serão <strong>substituídas por completo</strong> nesta competência. As demais
              permanecem como estão.
            </p>
          </fieldset>

          {error ? <p className="mt-3 text-sm text-rose-600">{error}</p> : null}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={confirm}
            disabled={busy || selected.size === 0}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy ? "Inicializando…" : "Inicializar"}
          </button>
        </div>
      </div>
    </div>
  );
}
