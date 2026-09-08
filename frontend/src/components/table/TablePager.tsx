import { PAGE_SIZE_OPTIONS, type PageSize, type Pagination } from "@/hooks/usePagination";

/**
 * Controles de paginação das tabelas (par com `usePagination`).
 *
 * São dois pedaços, de propósito separados: o seletor de tamanho mora em CIMA, junto dos
 * filtros (é uma preferência de exibição, como filtrar), e a navegação mora EMBAIXO da
 * tabela, onde a leitura termina.
 */

const SIZE_LABEL = (size: PageSize): string => (size === "ALL" ? "Todas" : String(size));

export function PageSizeSelect({
  value,
  onChange,
  label = "Linhas por página",
}: {
  value: PageSize;
  onChange: (size: PageSize) => void;
  label?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <select
        value={String(value)}
        onChange={(e) => onChange(e.target.value === "ALL" ? "ALL" : Number(e.target.value))}
        className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
      >
        {PAGE_SIZE_OPTIONS.map((size) => (
          <option key={String(size)} value={String(size)}>
            {SIZE_LABEL(size)}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Janela de no máximo 7 números em volta da página corrente, com "…" nas pontas quando há
 * mais páginas do que isso — assim a barra não cresce sem limite conforme a lista aumenta.
 */
function pageWindow(page: number, totalPages: number): (number | "gap")[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const out = new Set<number>([1, totalPages, page, page - 1, page + 1]);
  if (page <= 3) [2, 3, 4].forEach((n) => out.add(n));
  if (page >= totalPages - 2) [totalPages - 3, totalPages - 2, totalPages - 1].forEach((n) => out.add(n));
  const pages = [...out].filter((n) => n >= 1 && n <= totalPages).sort((a, b) => a - b);
  const withGaps: (number | "gap")[] = [];
  pages.forEach((n, i) => {
    if (i > 0 && n - pages[i - 1] > 1) withGaps.push("gap");
    withGaps.push(n);
  });
  return withGaps;
}

const navBtn =
  "rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40";

export function TablePager<T>({
  pagination,
  /** Nome do que está sendo listado, no plural (ex.: "operações"). */
  itemLabel = "itens",
}: {
  pagination: Pagination<T>;
  itemLabel?: string;
}) {
  const { page, setPage, totalPages, total, from, to, pageSize } = pagination;

  // Sem nada a paginar não há o que navegar; o contador ainda ajuda a ler o recorte.
  if (total === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-3 py-2 text-xs text-slate-600">
      <span className="tabular-nums">
        Mostrando <strong className="font-semibold text-slate-800">{from}</strong>–
        <strong className="font-semibold text-slate-800">{to}</strong> de{" "}
        <strong className="font-semibold text-slate-800">{total}</strong> {itemLabel}
      </span>

      {pageSize === "ALL" || totalPages <= 1 ? null : (
        <div className="flex flex-wrap items-center gap-1">
          <button type="button" className={navBtn} disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ‹ Anterior
          </button>

          {pageWindow(page, totalPages).map((n, i) =>
            n === "gap" ? (
              <span key={`gap-${i}`} className="px-1 text-slate-400">
                …
              </span>
            ) : (
              <button
                key={n}
                type="button"
                aria-current={n === page ? "page" : undefined}
                onClick={() => setPage(n)}
                className={`min-w-[1.85rem] rounded-lg border px-2 py-1 text-xs font-medium tabular-nums ${
                  n === page
                    ? "border-indigo-600 bg-indigo-600 text-white"
                    : "border-slate-300 text-slate-700 hover:bg-slate-50"
                }`}
              >
                {n}
              </button>
            ),
          )}

          <button type="button" className={navBtn} disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Próxima ›
          </button>

          <span className="ml-1 whitespace-nowrap tabular-nums text-slate-500">
            Página {page} de {totalPages}
          </span>
        </div>
      )}
    </div>
  );
}
