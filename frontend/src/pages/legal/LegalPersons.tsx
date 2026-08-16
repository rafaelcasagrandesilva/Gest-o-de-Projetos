import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { SortableTh } from "@/components/table";
import { Money } from "@/components/Money";
import { useTableSort } from "@/hooks/useTableSort";
import { useWorkspace } from "@/context/WorkspaceContext";
import { LegalCaseModal } from "@/components/legal/LegalCaseModal";
import { LegalPersonModal } from "@/components/legal/LegalPersonModal";
import { FilterChip, FilterGroup, KpiCard, formatCount } from "@/components/legal/LegalPanelPieces";
import { LEGAL_PERSON_SORT_COLUMNS, defaultLegalPersonSort } from "@/tableSort/legal";
import { formatApiError } from "@/utils/apiError";
import { formatCurrencyOrDash, sumCurrencyOrNull } from "@/utils/currency";
import {
  fetchLegalPerson,
  fetchLegalPersonFacets,
  listLegalPersons,
  type LegalCase,
  type LegalFacets,
  type LegalPerson,
  type LegalPersonDetail,
} from "@/services/legal";

/**
 * Pessoas — mesma experiência da tela de Processos, aplicada às pessoas: filtros
 * reativos, indicadores que acompanham o recorte e abertura em modal, sem trocar de tela.
 *
 * Os totais por pessoa são DERIVADOS dos processos no backend; os cards desta tela somam as
 * linhas já filtradas (`sumCurrencyOrNull` devolve `null` — e a UI mostra "—" — quando todos os
 * valores vieram omitidos por Dados sensíveis, em vez de um enganoso R$ 0,00).
 */

const TYPING_DEBOUNCE_MS = 350;

type HasCasesFilter = "all" | "with" | "without";

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export function LegalPersons() {
  const { setWorkspace } = useWorkspace();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    setWorkspace("legal");
  }, [setWorkspace]);

  const [companies, setCompanies] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [hasCases, setHasCases] = useState<HasCasesFilter>("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  const [facets, setFacets] = useState<LegalFacets | null>(null);
  const [people, setPeople] = useState<LegalPerson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [detail, setDetail] = useState<LegalPersonDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedCase, setSelectedCase] = useState<LegalCase | null>(null);

  useEffect(() => {
    const id = setTimeout(() => setSearch(searchInput), TYPING_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [searchInput]);

  useEffect(() => {
    void (async () => {
      try {
        setFacets(await fetchLegalPersonFacets());
      } catch {
        // Filtros vazios não impedem a listagem — a tabela continua utilizável.
      }
    })();
  }, []);

  const filters = useMemo(
    () => ({
      company: companies,
      project: projects,
      has_cases: hasCases === "all" ? null : hasCases === "with",
      q: search,
    }),
    [companies, projects, hasCases, search],
  );

  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    try {
      const rows = await listLegalPersons(filters);
      if (seq !== requestSeq.current) return;
      setPeople(rows);
    } catch (e) {
      if (seq !== requestSeq.current) return;
      setError(formatApiError(e));
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  const openPerson = useCallback(async (personId: string) => {
    setDetailLoading(true);
    try {
      setDetail(await fetchLegalPerson(personId));
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // Deep link vindo da tela de Processos: /legal/persons?person_id=…
  const deepLinkId = searchParams.get("person_id");
  useEffect(() => {
    if (!deepLinkId) return;
    void openPerson(deepLinkId);
    const next = new URLSearchParams(searchParams);
    next.delete("person_id");
    setSearchParams(next, { replace: true });
  }, [deepLinkId, openPerson, searchParams, setSearchParams]);

  const { sortedRows, headerSort } = useTableSort(people, LEGAL_PERSON_SORT_COLUMNS, {
    defaultCompare: defaultLegalPersonSort,
  });

  const totals = useMemo(
    () => ({
      people: people.length,
      cases: people.reduce((sum, p) => sum + p.case_count, 0),
      withCases: people.filter((p) => p.case_count > 0).length,
      claimed: sumCurrencyOrNull(people.map((p) => p.total_claimed)),
      considered: sumCurrencyOrNull(people.map((p) => p.total_considered)),
    }),
    [people],
  );

  const hasFilters = companies.length > 0 || projects.length > 0 || hasCases !== "all" || !!search;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Desligados</h1>
          <p className="text-sm text-slate-500">
            {loading
              ? "Carregando…"
              : `${formatCount(totals.people)} desligado(s) · ${formatCount(totals.withCases)} com processo`}
          </p>
        </div>
      </div>

      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4" aria-label="Filtros">
        <FilterGroup label="Situação">
          {(
            [
              ["all", "Todos"],
              ["with", "Possui processo"],
              ["without", "Sem processo"],
            ] as [HasCasesFilter, string][]
          ).map(([value, label]) => (
            <FilterChip
              key={value}
              label={label}
              active={hasCases === value}
              onClick={() => setHasCases(value)}
            />
          ))}
        </FilterGroup>

        <div className="flex flex-wrap items-end gap-x-6 gap-y-3 border-t border-slate-100 pt-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Empresa</span>
            <select
              value=""
              onChange={(e) => {
                if (e.target.value) setCompanies((prev) => toggle(prev, e.target.value));
              }}
              className="w-56 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Adicionar empresa…</option>
              {(facets?.companies ?? [])
                .filter((c) => !companies.includes(c))
                .map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Projeto</span>
            <select
              value=""
              onChange={(e) => {
                if (e.target.value) setProjects((prev) => toggle(prev, e.target.value));
              }}
              className="w-56 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Adicionar projeto…</option>
              {(facets?.projects ?? [])
                .filter((p) => !projects.includes(p))
                .map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Pesquisa</span>
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Nome, CPF, empresa, projeto…"
              className="w-72 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>

          {hasFilters ? (
            <button
              type="button"
              onClick={() => {
                setCompanies([]);
                setProjects([]);
                setHasCases("all");
                setSearchInput("");
                setSearch("");
              }}
              className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Limpar filtros
            </button>
          ) : null}
        </div>

        {companies.length > 0 || projects.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            {[...companies, ...projects].map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => {
                  setCompanies((prev) => prev.filter((c) => c !== tag));
                  setProjects((prev) => prev.filter((p) => p !== tag));
                }}
                className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-200"
              >
                {tag} <span aria-hidden>×</span>
              </button>
            ))}
          </div>
        ) : null}
      </section>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Desligados" value={formatCount(totals.people)} meta="na seleção atual" />
        <KpiCard
          label="Com processo"
          value={formatCount(totals.withCases)}
          meta={`${formatCount(totals.cases)} processo(s)`}
          stripe="bg-amber-500"
        />
        <KpiCard label="Valor total" value={formatCurrencyOrDash(totals.claimed)} meta="valor da causa" />
        <KpiCard
          label="Valor considerado"
          value={formatCurrencyOrDash(totals.considered)}
          meta="sem duplicidade"
          stripe="bg-emerald-500"
        />
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <span className="text-xs text-slate-600">
            {loading ? "Carregando…" : `${formatCount(sortedRows.length)} desligado(s) exibido(s)`}
          </span>
          {detailLoading ? <span className="text-xs text-slate-400">Abrindo ficha…</span> : null}
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <SortableTh label="Nome" column="name" {...headerSort} />
                <SortableTh label="CPF" column="cpf" {...headerSort} />
                <SortableTh label="Empresa" column="company" {...headerSort} />
                <SortableTh label="Projeto" column="project" {...headerSort} />
                <SortableTh label="Processos" column="case_count" align="right" {...headerSort} />
                <SortableTh label="Valor total" column="claimed" align="right" {...headerSort} />
                <SortableTh label="Valor considerado" column="considered" align="right" {...headerSort} />
              </tr>
            </thead>
            <tbody>
              {sortedRows.length === 0 && !loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-slate-400">
                    Nenhum desligado com esses filtros.
                  </td>
                </tr>
              ) : null}
              {sortedRows.map((p) => (
                <tr key={p.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="max-w-[18rem] truncate px-2 py-2" title={p.full_name}>
                    <button
                      type="button"
                      onClick={() => void openPerson(p.id)}
                      className="font-medium text-indigo-600 hover:underline"
                    >
                      {p.full_name}
                    </button>
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-600">{p.cpf ?? "—"}</td>
                  <td className="max-w-[15rem] truncate px-2 py-2 text-slate-600" title={p.company ?? ""}>
                    {p.company ?? "—"}
                  </td>
                  <td className="max-w-[15rem] truncate px-2 py-2 text-slate-600" title={p.project ?? ""}>
                    {p.project ?? "—"}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {p.case_count > 0 ? (
                      <button
                        type="button"
                        onClick={() => navigate(`/legal/cases?person_id=${p.id}`)}
                        className="font-medium text-indigo-600 hover:underline"
                        title="Ver os processos desta pessoa"
                      >
                        {formatCount(p.case_count)}
                      </button>
                    ) : (
                      <span className="text-slate-400">0</span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <Money value={p.total_claimed} />
                  </td>
                  <td className="px-2 py-2">
                    <Money value={p.total_considered} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {detail ? (
        <LegalPersonModal
          person={detail}
          onClose={() => setDetail(null)}
          onOpenCase={(c) => setSelectedCase(c)}
          onSeeAllCases={(id) => {
            setDetail(null);
            navigate(`/legal/cases?person_id=${id}`);
          }}
        />
      ) : null}

      {selectedCase ? (
        <LegalCaseModal legalCase={selectedCase} onClose={() => setSelectedCase(null)} />
      ) : null}
    </div>
  );
}
