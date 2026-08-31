import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "@/utils/apiError";
import { createEvent, EVENT_TYPES } from "@/services/legalOperation";
import { listLegalCases, type LegalCase } from "@/services/legal";

/**
 * Cadastro de compromisso. Vinculado a um processo (opcional) porque nem todo compromisso
 * pertence a um — reunião interna e prazo administrativo existem sem processo.
 */
export function LegalEventForm({
  onClose,
  onCreated,
  initialDate,
}: {
  onClose: () => void;
  onCreated: () => void;
  initialDate?: Date;
}) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState("AUDIENCIA");
  const [date, setDate] = useState(() => (initialDate ?? new Date()).toISOString().slice(0, 10));
  const [time, setTime] = useState("09:00");
  const [location, setLocation] = useState("");
  const [modality, setModality] = useState("PRESENCIAL");
  const [notes, setNotes] = useState("");
  const [caseId, setCaseId] = useState("");
  const [caseSearch, setCaseSearch] = useState("");
  const [cases, setCases] = useState<LegalCase[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void listLegalCases({ q: caseSearch || undefined })
        .then((rows) => {
          // Combo é auxiliar: 30 opções bastam para escolher; o resto se acha buscando.
          if (!cancelled) setCases(rows.slice(0, 30));
        })
        .catch(() => {
          if (!cancelled) setCases([]);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [caseSearch]);

  const podeSalvar = useMemo(() => title.trim().length > 0 && date, [title, date]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await createEvent({
        title: title.trim(),
        event_type: type,
        scheduled_for: new Date(`${date}T${time || "00:00"}`).toISOString(),
        location: location.trim() || null,
        modality,
        notes: notes.trim() || null,
        case_id: caseId || null,
      });
      onCreated();
      onClose();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Novo compromisso"
      onClick={onClose}
    >
      <div className="my-10 w-full max-w-xl rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Novo compromisso</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            Fechar
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Título</label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex.: Audiência inicial — 3ª Vara do Trabalho"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Tipo</label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Data</label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Hora</label>
              <input
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-600">Local</label>
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="Fórum, sala, endereço ou link"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Modalidade</label>
              <select
                value={modality}
                onChange={(e) => setModality(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="PRESENCIAL">Presencial</option>
                <option value="VIRTUAL">Virtual</option>
                <option value="HIBRIDA">Híbrida</option>
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Processo relacionado <span className="text-slate-400">(opcional)</span>
            </label>
            <input
              value={caseSearch}
              onChange={(e) => setCaseSearch(e.target.value)}
              placeholder="Buscar por número ou reclamante…"
              className="mb-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <select
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="">Sem processo vinculado</option>
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.case_number} — {c.person_name ?? c.claimant_name ?? "sem reclamante"}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Observação</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 border-t border-slate-200 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={!podeSalvar || saving}
            onClick={() => void handleSave()}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:opacity-60"
          >
            {saving ? "Salvando…" : "Salvar compromisso"}
          </button>
        </div>
      </div>
    </div>
  );
}
