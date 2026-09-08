/**
 * Valida a matemática da paginação das tabelas.
 * Espelha frontend/src/hooks/usePagination.ts (mesma convenção dos demais test-*.mjs:
 * o .mjs replica a fórmula porque não importa TypeScript direto).
 *
 * Os casos usam o cenário real que motivou a paginação: as 26 operações de antecipação
 * da tela de Antecipações.
 *
 * Rodar: node scripts/test-pagination.mjs
 */

/** Réplica de usePagination, sem React: só a aritmética das páginas. */
function paginate(rows, pageSize, page) {
  const total = rows.length;
  const totalPages = pageSize === "ALL" ? 1 : Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageRows = pageSize === "ALL" ? rows : rows.slice((safePage - 1) * pageSize, (safePage - 1) * pageSize + pageSize);
  return {
    pageRows,
    page: safePage,
    totalPages,
    total,
    from: total === 0 ? 0 : pageSize === "ALL" ? 1 : (safePage - 1) * pageSize + 1,
    to: pageSize === "ALL" ? total : Math.min(total, safePage * pageSize),
  };
}

/** Réplica da janela de números do TablePager. */
function pageWindow(page, totalPages) {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const out = new Set([1, totalPages, page, page - 1, page + 1]);
  if (page <= 3) [2, 3, 4].forEach((n) => out.add(n));
  if (page >= totalPages - 2) [totalPages - 3, totalPages - 2, totalPages - 1].forEach((n) => out.add(n));
  const pages = [...out].filter((n) => n >= 1 && n <= totalPages).sort((a, b) => a - b);
  const withGaps = [];
  pages.forEach((n, i) => {
    if (i > 0 && n - pages[i - 1] > 1) withGaps.push("gap");
    withGaps.push(n);
  });
  return withGaps;
}

let failures = 0;
function check(label, got, expected) {
  const ok = JSON.stringify(got) === JSON.stringify(expected);
  if (!ok) failures += 1;
  console.log(`${ok ? "  ok  " : "FALHOU"} ${label}: ${JSON.stringify(got)}${ok ? "" : ` (esperado ${JSON.stringify(expected)})`}`);
}

// As 26 operações de hoje, identificadas por posição para conferir o recorte.
const ops = Array.from({ length: 26 }, (_, i) => i + 1);

console.log("— 26 operações, 10 por página (o padrão) —");
check("total de páginas", paginate(ops, 10, 1).totalPages, 3);
check("página 1 traz as 10 primeiras", paginate(ops, 10, 1).pageRows, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
check("rótulo da página 1", [paginate(ops, 10, 1).from, paginate(ops, 10, 1).to], [1, 10]);
check("página 2 continua de onde parou", paginate(ops, 10, 2).pageRows[0], 11);
check("última página traz só o resto", paginate(ops, 10, 3).pageRows, [21, 22, 23, 24, 25, 26]);
check("rótulo da última página", [paginate(ops, 10, 3).from, paginate(ops, 10, 3).to], [21, 26]);

console.log("\n— Nenhuma linha se perde nem aparece duas vezes —");
for (const size of [5, 10, 15, 20]) {
  const { totalPages } = paginate(ops, size, 1);
  const visitadas = [];
  for (let p = 1; p <= totalPages; p += 1) visitadas.push(...paginate(ops, size, p).pageRows);
  check(`${size} por página cobre as 26 exatamente uma vez`, visitadas, ops);
}
check("Todas → uma página só", paginate(ops, "ALL", 1).totalPages, 1);
check("Todas → mostra as 26", paginate(ops, "ALL", 1).pageRows.length, 26);
check("Todas → rótulo 1–26", [paginate(ops, "ALL", 1).from, paginate(ops, "ALL", 1).to], [1, 26]);

console.log("\n— Casos de borda —");
check("lista vazia ainda tem 1 página", paginate([], 10, 1).totalPages, 1);
check("lista vazia não mostra intervalo", [paginate([], 10, 1).from, paginate([], 10, 1).to], [0, 0]);
// Filtrar por instituição encolhe a lista: quem estava na página 3 não pode ver tabela vazia.
check("filtro encolheu → cai na última página", paginate(ops.slice(0, 8), 10, 3).page, 1);
check("filtro encolheu → e ainda mostra linhas", paginate(ops.slice(0, 8), 10, 3).pageRows.length, 8);
check("divisão exata não cria página vazia", paginate(ops.slice(0, 20), 10, 1).totalPages, 2);
check("1 linha a mais cria a página seguinte", paginate(ops.slice(0, 21), 10, 1).totalPages, 3);

console.log("\n— Janela de números —");
check("3 páginas → todas visíveis", pageWindow(2, 3), [1, 2, 3]);
check("7 páginas → todas visíveis", pageWindow(4, 7), [1, 2, 3, 4, 5, 6, 7]);
check("20 páginas, no começo", pageWindow(2, 20), [1, 2, 3, 4, "gap", 20]);
check("20 páginas, no meio", pageWindow(10, 20), [1, "gap", 9, 10, 11, "gap", 20]);
check("20 páginas, no fim", pageWindow(19, 20), [1, "gap", 17, 18, 19, 20]);

console.log(failures === 0 ? "\nTodos os casos passaram.\n" : `\n${failures} caso(s) falharam.\n`);
process.exit(failures === 0 ? 0 : 1);
