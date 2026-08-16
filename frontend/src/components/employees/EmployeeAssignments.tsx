import { useCallback, useEffect, useMemo, useState } from "react";
import { formatApiError } from "@/utils/apiError";
import { formatCurrencyOrDash } from "@/utils/currency";
import { listCostCenterRefs } from "@/services/costCenters";
import { listProjects, type Project } from "@/services/projects";
import {
  cancelEmployeeAssignment,
  closeEmployeeAssignment,
  createEmployeeAssignment,
  listEmployeeAssignments,
  reopenEmployeeAssignment,
  updateEmployeeAssignment,
  type AllocationType,
  type EmployeeAssignment,
  type EmployeeAssignmentInput,
} from "@/services/employees";

/**
 * Seção ALOCAÇÕES dentro do cadastro do colaborador — não abre outra tela.
 *
 * Uma Alocação é o vínculo CONTRATUAL com um projeto/centro de custo. O tipo é explícito e
 * troca os campos exibidos, para o usuário nunca ficar em dúvida sobre qual modelo está usando:
 *
 *   Remuneração independente (padrão) → contrato próprio, valor próprio, sem percentual
 *   Participação em rateio            → um custo dividido, percentual visível
 *
 * Encerrar nunca apaga: vira ENCERRADA com data de fim, e o histórico continua listado.
 */

const inputClass =
  "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none";

function money(v: string): number | null {
  const t = v.replace(/\./g, "").replace(",", ".").trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function fromMoney(v: number | null | undefined): string {
  return v == null ? "" : String(v).replace(".", ",");
}

type Draft = {
  id?: string;
  project_id: string;
  cost_center: string;
  allocation_type: AllocationType;
  role_title: string;
  salary_base: string;
  allowance: string;
  hours_per_month: string;
  allocation_percent: string;
  start_date: string;
  notes: string;
};

const EMPTY: Draft = {
  project_id: "",
  cost_center: "",
  // Padrão pedido: a esmagadora maioria é contrato próprio.
  allocation_type: "INDEPENDENTE",
  role_title: "",
  salary_base: "",
  allowance: "",
  hours_per_month: "",
  allocation_percent: "100",
  start_date: "",
  notes: "",
};

function toDraft(a: EmployeeAssignment): Draft {
  return {
    id: a.id,
    project_id: a.project_id ?? "",
    cost_center: a.cost_center ?? "",
    allocation_type: a.allocation_type,
    role_title: a.role_title ?? "",
    salary_base: fromMoney(a.salary_base),
    allowance: fromMoney(a.allowance),
    hours_per_month: fromMoney(a.hours_per_month),
    allocation_percent: String(a.allocation_percent ?? 100),
    start_date: a.start_date ?? "",
    notes: a.notes ?? "",
  };
}

export function EmployeeAssignments({
  employeeId,
  employmentType,
  canEdit,
}: {
  employeeId: string;
  employmentType: "CLT" | "PJ";
  canEdit: boolean;
}) {
  const [rows, setRows] = useState<EmployeeAssignment[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [costCenters, setCostCenters] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Canceladas ficam fora por padrão — foram criadas por engano.
  const [showCancelled, setShowCancelled] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listEmployeeAssignments(employeeId, showCancelled));
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [employeeId, showCancelled]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void (async () => {
      try {
        const [p, cc] = await Promise.all([listProjects(), listCostCenterRefs()]);
        setProjects(p);
        setCostCenters(cc.map((c) => c.label));
      } catch {
        /* seletores vazios não impedem o cadastro */
      }
    })();
  }, []);

  const ativas = useMemo(() => rows.filter((r) => r.status === "ATIVA"), [rows]);
  const encerradas = useMemo(() => rows.filter((r) => r.status === "ENCERRADA"), [rows]);
  const canceladas = useMemo(() => rows.filter((r) => r.status === "CANCELADA"), [rows]);

  async function persist() {
    if (!draft) return;
    const independente = draft.allocation_type === "INDEPENDENTE";
    const payload: EmployeeAssignmentInput = {
      project_id: draft.project_id || null,
      cost_center: draft.cost_center.trim() || null,
      allocation_type: draft.allocation_type,
      role_title: draft.role_title.trim() || null,
      start_date: draft.start_date || null,
      notes: draft.notes.trim() || null,
      // O backend também normaliza; aqui só evitamos mandar campo que não pertence ao tipo.
      ...(independente
        ? {
            salary_base: money(draft.salary_base),
            allowance: money(draft.allowance),
            hours_per_month: money(draft.hours_per_month),
          }
        : { allocation_percent: money(draft.allocation_percent) ?? 100 }),
    };
    setSaving(true);
    setError(null);
    try {
      if (draft.id) await updateEmployeeAssignment(employeeId, draft.id, payload);
      else await createEmployeeAssignment(employeeId, payload);
      setDraft(null);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setSaving(false);
    }
  }

  async function cancel(row: EmployeeAssignment) {
    const reason = window.prompt(
      "Cancelar esta alocação (use apenas se foi criada por engano).\n\nMotivo:",
    );
    if (reason === null) return; // desistiu
    setBusyId(row.id);
    setError(null);
    try {
      await cancelEmployeeAssignment(employeeId, row.id, reason);
      await load();
    } catch (e) {
      // Com efeito financeiro o backend recusa e explica que o caminho é Encerrar.
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  async function toggleStatus(row: EmployeeAssignment) {
    setBusyId(row.id);
    setError(null);
    try {
      if (row.status === "ATIVA") await closeEmployeeAssignment(employeeId, row.id);
      else await reopenEmployeeAssignment(employeeId, row.id);
      await load();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      {/* Sempre visível: a Alocação É o vínculo do colaborador com o contrato. Quem tem uma vê
          uma; quem tem cinco vê cinco. Não há mais checkbox para revelar a seção. */}
      <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Alocações</h4>
              <p className="text-xs text-slate-500">
                Onde o colaborador atua e quanto recebe em cada contrato.
              </p>
            </div>
            {canEdit && !draft ? (
              <button
                type="button"
                onClick={() => setDraft({ ...EMPTY })}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
              >
                + Nova alocação
              </button>
            ) : null}
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {loading ? <p className="text-sm text-slate-400">Carregando…</p> : null}

          {ativas.length === 0 && !loading ? (
            <p className="rounded-lg border border-dashed border-slate-200 py-5 text-center text-sm text-slate-400">
              Nenhuma alocação ativa.
            </p>
          ) : null}

          {ativas.map((a) => (
            <AssignmentCard
              key={a.id}
              a={a}
              canEdit={canEdit}
              busy={busyId === a.id}
              onEdit={() => setDraft(toDraft(a))}
              onToggle={() => void toggleStatus(a)}
              onCancel={() => void cancel(a)}
            />
          ))}

          {draft ? (
            <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-4">
              <p className="mb-3 text-sm font-medium text-slate-800">
                {draft.id ? "Editar alocação" : "Nova alocação"}
              </p>

              <fieldset className="mb-3">
                <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Tipo da alocação
                </legend>
                <div className="flex flex-col gap-1.5 sm:flex-row sm:gap-5">
                  {(
                    [
                      ["INDEPENDENTE", "Remuneração independente", "Contrato próprio, com valor próprio."],
                      ["RATEIO", "Participação em rateio", "Um mesmo custo dividido por percentual."],
                    ] as [AllocationType, string, string][]
                  ).map(([value, label, hint]) => (
                    <label key={value} className="flex items-start gap-2 text-sm text-slate-700">
                      <input
                        type="radio"
                        name="allocation_type"
                        checked={draft.allocation_type === value}
                        onChange={() => setDraft({ ...draft, allocation_type: value })}
                        className="mt-1"
                      />
                      <span>
                        {label}
                        <span className="block text-xs text-slate-500">{hint}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Projeto / Contrato">
                  <select
                    value={draft.project_id}
                    onChange={(e) => setDraft({ ...draft, project_id: e.target.value })}
                    className={inputClass}
                  >
                    <option value="">Sem projeto (apenas centro de custo)</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Centro de custo">
                  <input
                    list="assignment-cost-centers"
                    value={draft.cost_center}
                    onChange={(e) => setDraft({ ...draft, cost_center: e.target.value })}
                    className={inputClass}
                  />
                  <datalist id="assignment-cost-centers">
                    {costCenters.map((c) => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                </Field>
                <Field label="Cargo">
                  <input
                    value={draft.role_title}
                    onChange={(e) => setDraft({ ...draft, role_title: e.target.value })}
                    className={inputClass}
                  />
                </Field>
                {/* Início/fim descrevem o CONTRATO e valem nos dois tipos. */}
                <Field label="Início">
                  <input
                    type="date"
                    value={draft.start_date}
                    onChange={(e) => setDraft({ ...draft, start_date: e.target.value })}
                    className={inputClass}
                  />
                </Field>

                {/* Campos MUTUAMENTE EXCLUSIVOS: é impossível configurar um híbrido inválido. */}
                {draft.allocation_type === "INDEPENDENTE" ? (
                  <>
                    <Field
                      label={employmentType === "PJ" ? "Valor hora" : "Valor base (salário)"}
                      hint="Substitui o valor do cadastro NESTE contrato."
                    >
                      <input
                        value={draft.salary_base}
                        onChange={(e) => setDraft({ ...draft, salary_base: e.target.value })}
                        placeholder="0,00"
                        className={inputClass}
                      />
                    </Field>
                    <Field label="Ajuda de custo">
                      <input
                        value={draft.allowance}
                        onChange={(e) => setDraft({ ...draft, allowance: e.target.value })}
                        placeholder="0,00"
                        className={inputClass}
                      />
                    </Field>
                    <Field label="Horas / mês" hint={employmentType === "PJ" ? "Multiplica o valor hora." : "Opcional."}>
                      <input
                        value={draft.hours_per_month}
                        onChange={(e) => setDraft({ ...draft, hours_per_month: e.target.value })}
                        placeholder="0"
                        className={inputClass}
                      />
                    </Field>
                  </>
                ) : (
                  <Field
                    label="Percentual do rateio (%)"
                    hint="A soma dos rateios do colaborador não pode passar de 100%."
                  >
                    <input
                      value={draft.allocation_percent}
                      onChange={(e) => setDraft({ ...draft, allocation_percent: e.target.value })}
                      placeholder="100"
                      className={inputClass}
                    />
                  </Field>
                )}

                <Field label="Observações" wide>
                  <textarea
                    rows={2}
                    value={draft.notes}
                    onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
                    className={inputClass}
                  />
                </Field>
              </div>

              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void persist()}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
                >
                  {saving ? "Salvando…" : "Salvar alocação"}
                </button>
                <button
                  type="button"
                  onClick={() => setDraft(null)}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm"
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : null}

          {encerradas.length > 0 ? (
            <details className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
              <summary className="cursor-pointer text-xs font-medium text-slate-600">
                Histórico — {encerradas.length} alocação(ões) encerrada(s)
              </summary>
              <div className="mt-2 space-y-2">
                {encerradas.map((a) => (
                  <AssignmentCard
                    key={a.id}
                    a={a}
                    canEdit={canEdit}
                    busy={busyId === a.id}
                    onEdit={() => setDraft(toDraft(a))}
                    onToggle={() => void toggleStatus(a)}
                  />
                ))}
              </div>
            </details>
          ) : null}

          {/* Canceladas: escondidas por padrão, mas nunca apagadas — auditoria continua íntegra. */}
          <label className="flex items-center gap-2 text-xs text-slate-500">
            <input
              type="checkbox"
              checked={showCancelled}
              onChange={(e) => setShowCancelled(e.target.checked)}
              className="rounded border-slate-300"
            />
            Mostrar alocações canceladas
          </label>
          {showCancelled && canceladas.length > 0 ? (
            <div className="space-y-2">
              {canceladas.map((a) => (
                <AssignmentCard key={a.id} a={a} canEdit={false} busy={false} onEdit={() => {}} onToggle={() => {}} />
              ))}
            </div>
          ) : null}
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  wide,
  children,
}: {
  label: string;
  hint?: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={`flex flex-col gap-1 ${wide ? "sm:col-span-2" : ""}`}>
      <span className="text-xs font-medium text-slate-600">{label}</span>
      {children}
      {hint ? <span className="text-[11px] text-slate-400">{hint}</span> : null}
    </label>
  );
}

function AssignmentCard({
  a,
  canEdit,
  busy,
  onEdit,
  onToggle,
  onCancel,
}: {
  a: EmployeeAssignment;
  canEdit: boolean;
  busy: boolean;
  onEdit: () => void;
  onToggle: () => void;
  onCancel?: () => void;
}) {
  const ativa = a.status === "ATIVA";
  const cancelada = a.status === "CANCELADA";
  const independente = a.allocation_type === "INDEPENDENTE";
  return (
    <div className={`rounded-lg border p-3 ${ativa ? "border-slate-200 bg-white" : "border-slate-200 bg-slate-50 opacity-75"}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-800">
            {a.project_name ?? a.cost_center ?? "Sem projeto"}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                independente ? "bg-indigo-100 text-indigo-800" : "bg-amber-100 text-amber-900"
              }`}
            >
              {independente ? "Remuneração independente" : `Rateio · ${a.allocation_percent}%`}
            </span>
            {cancelada ? (
              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-700">
                Cancelada
                {a.cancelled_at ? ` em ${a.cancelled_at.slice(0, 10).split("-").reverse().join("/")}` : ""}
              </span>
            ) : !ativa ? (
              <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                Encerrada{a.end_date ? ` em ${a.end_date.slice(0, 10).split("-").reverse().join("/")}` : ""}
              </span>
            ) : null}
            {a.is_backfilled ? (
              <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[11px] text-slate-500">
                criada pela migração
              </span>
            ) : null}
          </div>
        </div>
        {canEdit ? (
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={onEdit}
              className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
            >
              Editar
            </button>
            <button
              type="button"
              onClick={onToggle}
              disabled={busy}
              className={`rounded-md border px-2 py-1 text-xs disabled:opacity-50 ${
                ativa
                  ? "border-amber-200 text-amber-700 hover:bg-amber-50"
                  : "border-emerald-200 text-emerald-700 hover:bg-emerald-50"
              }`}
            >
              {ativa ? "Encerrar" : "Reativar"}
            </button>
            {ativa && onCancel ? (
              <button
                type="button"
                onClick={onCancel}
                disabled={busy}
                title="Só para alocações criadas por engano, sem nenhum lançamento financeiro"
                className="rounded-md border border-rose-200 px-2 py-1 text-xs text-rose-700 hover:bg-rose-50 disabled:opacity-50"
              >
                Cancelar
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600 sm:grid-cols-4">
        {a.role_title ? <Info label="Cargo">{a.role_title}</Info> : null}
        {independente ? (
          <>
            <Info label="Valor base">{formatCurrencyOrDash(a.salary_base)}</Info>
            <Info label="Ajuda">{formatCurrencyOrDash(a.allowance)}</Info>
            {a.hours_per_month != null ? <Info label="Horas/mês">{a.hours_per_month}</Info> : null}
          </>
        ) : null}
        {a.start_date ? (
          <Info label="Início">{a.start_date.slice(0, 10).split("-").reverse().join("/")}</Info>
        ) : null}
      </dl>
    </div>
  );
}

function Info({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="truncate text-slate-700">{children}</dd>
    </div>
  );
}
