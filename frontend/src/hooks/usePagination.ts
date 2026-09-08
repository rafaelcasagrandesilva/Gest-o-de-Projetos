import { useEffect, useMemo, useState } from "react";

/**
 * Paginação client-side de uma lista já filtrada e ordenada.
 *
 * As telas financeiras carregam a lista inteira de uma vez (um GET só) e fazem filtro,
 * ordenação e agora paginação sobre esse mesmo array — por isso a paginação entra DEPOIS
 * da ordenação: a página 1 tem que ser o topo da tabela como ela está ordenada na tela.
 *
 * Os indicadores (cards de taxa, KPIs) continuam recebendo a lista FILTRADA inteira, nunca
 * a página: paginar é recorte de leitura, não recorte de cálculo.
 */

/** "ALL" = uma página só, com tudo (opção "Todas"). */
export type PageSize = number | "ALL";

export const PAGE_SIZE_OPTIONS: readonly PageSize[] = [5, 10, 15, 20, "ALL"];

export interface Pagination<T> {
  /** As linhas da página corrente — é isto que a tabela renderiza. */
  pageRows: T[];
  page: number;
  setPage: (page: number) => void;
  pageSize: PageSize;
  setPageSize: (size: PageSize) => void;
  totalPages: number;
  /** Total de linhas no recorte (todas as páginas somadas). */
  total: number;
  /** Intervalo exibido, 1-based, para o rótulo "1–10 de 26". */
  from: number;
  to: number;
}

export function usePagination<T>(rows: T[], initialSize: PageSize = 10): Pagination<T> {
  const [pageSize, setPageSizeState] = useState<PageSize>(initialSize);
  const [page, setPage] = useState(1);

  const total = rows.length;
  const totalPages = pageSize === "ALL" ? 1 : Math.max(1, Math.ceil(total / pageSize));

  // Trocar o filtro (mês, instituição) encolhe a lista debaixo do usuário. Sem este
  // ajuste ele ficaria numa página que não existe mais e veria a tabela vazia.
  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  // Enquanto o efeito acima não roda, o render corrente já usa a página corrigida.
  const safePage = Math.min(page, totalPages);

  const pageRows = useMemo(() => {
    if (pageSize === "ALL") return rows;
    const start = (safePage - 1) * pageSize;
    return rows.slice(start, start + pageSize);
  }, [rows, pageSize, safePage]);

  // Mudar quantas linhas cabem por página muda o significado de "página 3": volta ao topo.
  function setPageSize(size: PageSize): void {
    setPageSizeState(size);
    setPage(1);
  }

  return {
    pageRows,
    page: safePage,
    setPage,
    pageSize,
    setPageSize,
    totalPages,
    total,
    from: total === 0 ? 0 : pageSize === "ALL" ? 1 : (safePage - 1) * pageSize + 1,
    to: pageSize === "ALL" ? total : Math.min(total, safePage * pageSize),
  };
}
