import type { ReactNode } from "react";

function tooltipFromChildren(children: ReactNode, explicit?: string): string | undefined {
  if (explicit !== undefined && explicit !== "") return explicit;
  if (typeof children === "string" || typeof children === "number") {
    const s = String(children).trim();
    return s.length > 0 ? s : undefined;
  }
  return undefined;
}

export type TruncatedTextProps = {
  children: ReactNode;
  /** Texto do tooltip; se omitido e `children` for string/número, usa o próprio texto */
  title?: string;
  className?: string;
  /** Largura máxima Tailwind (padrão 300px — coluna “Nome” típica) */
  maxWidthClass?: string;
};

/**
 * Texto em uma linha com ellipsis + `title` nativo para ver o conteúdo completo no hover.
 * Use dentro de `<td>` com layout estável (tabela não quebra linhas na coluna).
 */
export function TruncatedText({
  children,
  title,
  className = "",
  maxWidthClass = "max-w-[300px]",
}: TruncatedTextProps) {
  const tip = tooltipFromChildren(children, title);
  return (
    <span
      title={tip}
      className={`inline-block min-w-0 align-middle ${maxWidthClass} truncate whitespace-nowrap ${className}`}
    >
      {children}
    </span>
  );
}

export type TruncatedCellProps = {
  value: string | null | undefined;
  empty?: ReactNode;
  className?: string;
  maxWidthClass?: string;
};

/** Atalho para células cujo valor é string opcional (mesmo comportamento + fallback). */
export function TruncatedCell({
  value,
  empty = "—",
  className = "",
  maxWidthClass = "max-w-[300px]",
}: TruncatedCellProps) {
  const s = value?.trim();
  if (!s) return <span className={className}>{empty}</span>;
  return (
    <span
      title={s}
      className={`inline-block min-w-0 align-middle ${maxWidthClass} truncate whitespace-nowrap ${className}`}
    >
      {s}
    </span>
  );
}
