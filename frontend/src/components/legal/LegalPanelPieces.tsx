import type { ReactNode } from "react";
import { formatCurrencyOrDash, formatCurrencyShortOrDash } from "@/utils/currency";
import type { LegalBucket, LegalCaseStatus } from "@/services/legal";
import { LEGAL_STATUS_STYLES } from "@/services/legal";

/**
 * Peças visuais do Workspace Jurídico — reproduzem a experiência do Painel de Passivo
 * (chips de filtro, cards de indicador e gráficos de barra clicáveis) com o visual do SGC.
 *
 * Ficam num arquivo único e compartilhado para que as telas de Processos e de Pessoas
 * usem exatamente os mesmos componentes: filtrar em qualquer eixo é sempre o mesmo gesto.
 */

/** Contagem inteira em pt-BR (não é moeda — moeda passa por `@/utils/currency`). */
export function formatCount(n: number): string {
  if (!Number.isFinite(n)) return "0";
  return Math.round(n).toLocaleString("pt-BR");
}

/** Chip de filtro multi-seleção (clique alterna). `tone` colore o estado ativo por status. */
export function FilterChip({
  label,
  active,
  onClick,
  tone,
  count,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  tone?: string;
  count?: number;
}) {
  const activeClass = tone ? `${tone} text-white border-transparent` : "bg-indigo-600 text-white border-indigo-600";
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition ${
        active
          ? activeClass
          : "border-slate-300 bg-white text-slate-600 hover:border-indigo-400 hover:text-slate-900"
      }`}
    >
      {label}
      {count != null ? (
        <span className={active ? "text-white/80" : "text-slate-400"}>{formatCount(count)}</span>
      ) : null}
    </button>
  );
}

/** Grupo de chips com rótulo em caixa alta (mesma hierarquia visual do painel). */
export function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

/** Card de indicador com faixa colorida à esquerda. `value` já vem formatado. */
export function KpiCard({
  label,
  value,
  meta,
  stripe = "bg-indigo-500",
  dot,
}: {
  label: string;
  value: string;
  meta?: string;
  stripe?: string;
  dot?: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-white p-4">
      <span className={`absolute inset-y-0 left-0 w-1 ${stripe}`} aria-hidden />
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {dot ? <span className={`h-2 w-2 rounded-sm ${dot}`} aria-hidden /> : null}
        {label}
      </div>
      <div
        className={`mt-1.5 font-semibold tabular-nums text-slate-900 ${
          value.length > 14 ? "text-lg" : "text-2xl"
        }`}
      >
        {value}
      </div>
      {meta ? <div className="mt-0.5 text-xs text-slate-500">{meta}</div> : null}
    </div>
  );
}

/**
 * Gráfico de barras horizontais. Cada barra é clicável e alterna o filtro daquele valor —
 * é o que faz "navegar sem trocar de tela" no painel original.
 */
export function BarChartCard({
  title,
  buckets,
  selected,
  onToggle,
  statusColors = false,
  emptyLabel = "Sem dados",
}: {
  title: string;
  buckets: LegalBucket[];
  selected: string[];
  onToggle: (key: string) => void;
  statusColors?: boolean;
  emptyLabel?: string;
}) {
  const max = Math.max(1, ...buckets.map((b) => b.value ?? 0));
  // Sem `legal.sensitive` o backend omite os valores: a barra vira proporcional à QUANTIDADE,
  // para o gráfico continuar informativo em vez de exibir barras vazias.
  const redacted = buckets.length > 0 && buckets.every((b) => b.value == null);
  const maxCount = Math.max(1, ...buckets.map((b) => b.count));

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {buckets.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">{emptyLabel}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {buckets.map((bucket) => {
            const isActive = selected.includes(bucket.key);
            const ratio = redacted
              ? bucket.count / maxCount
              : (bucket.value ?? 0) / max;
            const barColor =
              statusColors && bucket.key in LEGAL_STATUS_STYLES
                ? LEGAL_STATUS_STYLES[bucket.key as LegalCaseStatus].bar
                : "bg-indigo-500";
            return (
              <button
                key={bucket.key || "—"}
                type="button"
                onClick={() => onToggle(bucket.key)}
                aria-pressed={isActive}
                className={`grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-2 rounded-md px-1 py-0.5 text-left text-xs transition hover:bg-slate-50 ${
                  isActive ? "bg-indigo-50" : ""
                }`}
              >
                <span className={`truncate ${isActive ? "font-semibold text-indigo-800" : "text-slate-600"}`} title={bucket.label}>
                  {bucket.label}
                </span>
                <span className="h-4 overflow-hidden rounded border border-slate-200 bg-slate-50">
                  <span
                    className={`block h-full rounded-l ${barColor} transition-[width] duration-300`}
                    style={{ width: `${Math.max(2, ratio * 100)}%` }}
                  />
                </span>
                <span className="whitespace-nowrap tabular-nums text-slate-700">
                  {redacted ? "—" : formatCurrencyShortOrDash(bucket.value)}
                  <span className="ml-1 text-slate-400">· {formatCount(bucket.count)}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Pílula de status com a cor semântica do módulo. */
export function StatusPill({ status, label }: { status: LegalCaseStatus; label: string }) {
  const style = LEGAL_STATUS_STYLES[status] ?? LEGAL_STATUS_STYLES.SEM_PROCESSO;
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ${style.pill}`}>
      {label}
    </span>
  );
}

/** Linha rótulo/valor usada nos modais de detalhe. */
export function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-slate-800">{children ?? "—"}</dd>
    </div>
  );
}

/** Valor monetário para os modais: "—" quando omitido por Dados sensíveis. */
export function DetailMoney({ value }: { value: number | null | undefined }) {
  return <span className="tabular-nums">{formatCurrencyOrDash(value)}</span>;
}

/** Data ISO (yyyy-mm-dd) → dd/mm/aaaa. */
export function formatDateBR(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [year, month, day] = iso.slice(0, 10).split("-");
  if (!year || !month || !day) return "—";
  return `${day}/${month}/${year}`;
}
