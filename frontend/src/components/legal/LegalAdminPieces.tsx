import type { ReactNode } from "react";

/**
 * Peças compartilhadas das telas de Administração do Jurídico.
 *
 * Todas as quatro entidades (Pessoas, Processos, Empresas, Projetos) usam o MESMO esqueleto —
 * barra de ações, tabela, formulário em modal e botão desativar/restaurar — para que o
 * comportamento seja idêntico em qualquer aba e não haja quatro variações para manter.
 */

/** Rótulo + controle, empilhados. `wide` ocupa a linha inteira do grid do formulário. */
export function Field({
  label,
  hint,
  wide,
  children,
}: {
  label: string;
  hint?: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`flex min-w-0 flex-col gap-1 ${wide ? "sm:col-span-2" : ""}`}>
      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      {children}
      {hint ? <span className="text-[11px] text-slate-400">{hint}</span> : null}
    </label>
  );
}

export const inputClass =
  "rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none disabled:bg-slate-50 disabled:text-slate-400";

/** Modal de formulário: cabeçalho, corpo em grid de 2 colunas e rodapé com Salvar/Cancelar. */
export function FormModal({
  title,
  subtitle,
  onClose,
  onSubmit,
  submitting,
  error,
  submitLabel = "Salvar",
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  onSubmit: () => void;
  submitting?: boolean;
  error?: string | null;
  submitLabel?: string;
  children: ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <form
        className="my-8 w-full max-w-2xl rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p> : null}
        </div>
        <div className="grid gap-3 px-5 py-4 sm:grid-cols-2">{children}</div>
        {error ? <p className="px-5 pb-2 text-sm text-red-600">{error}</p> : null}
        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {submitting ? "Salvando…" : submitLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

/** Pílula Ativo/Inativo. */
export function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        active ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600"
      }`}
    >
      {active ? "Ativo" : "Inativo"}
    </span>
  );
}

/** Ações da linha: Editar + Desativar/Restaurar (nunca excluir). */
export function RowActions({
  active,
  onEdit,
  onToggle,
  canEdit,
  canToggle,
  busy,
}: {
  active: boolean;
  onEdit: () => void;
  onToggle: () => void;
  canEdit: boolean;
  canToggle: boolean;
  busy?: boolean;
}) {
  return (
    <div className="flex justify-end gap-1.5">
      {canEdit ? (
        <button
          type="button"
          onClick={onEdit}
          className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          Editar
        </button>
      ) : null}
      {canToggle ? (
        <button
          type="button"
          onClick={onToggle}
          disabled={busy}
          className={`rounded-md border px-2 py-1 text-xs font-medium disabled:opacity-50 ${
            active
              ? "border-amber-200 text-amber-700 hover:bg-amber-50"
              : "border-emerald-200 text-emerald-700 hover:bg-emerald-50"
          }`}
        >
          {active ? "Desativar" : "Restaurar"}
        </button>
      ) : null}
    </div>
  );
}

/** Cabeçalho de uma aba: descrição + busca + "mostrar inativos" + botão de criação. */
export function AdminToolbar({
  description,
  search,
  onSearch,
  showInactive,
  onShowInactive,
  onCreate,
  createLabel,
  canCreate,
  count,
}: {
  description: string;
  search: string;
  onSearch: (v: string) => void;
  showInactive: boolean;
  onShowInactive: (v: boolean) => void;
  onCreate: () => void;
  createLabel: string;
  canCreate: boolean;
  count: number;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4">
      <div className="min-w-0">
        <p className="text-sm text-slate-600">{description}</p>
        <p className="mt-0.5 text-xs text-slate-400">{count} registro(s)</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Buscar…"
          className={`${inputClass} w-56`}
        />
        <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-600">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => onShowInactive(e.target.checked)}
            className="h-4 w-4 accent-indigo-600"
          />
          Mostrar inativos
        </label>
        {canCreate ? (
          <button
            type="button"
            onClick={onCreate}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            {createLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** Casca da tabela das abas de Administração. */
export function AdminTable({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>{head}</tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </div>
  );
}

export function Th({
  children,
  align = "left",
}: {
  children: ReactNode;
  align?: "left" | "right" | "center";
}) {
  const cls = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return <th className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide ${cls}`}>{children}</th>;
}

export function EmptyRow({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-10 text-center text-sm text-slate-400">
        {children}
      </td>
    </tr>
  );
}
