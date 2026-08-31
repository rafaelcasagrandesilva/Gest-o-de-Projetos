import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { SortableTh } from "@/components/table";
import { Money } from "@/components/Money";
import { useTableSort } from "@/hooks/useTableSort";
import { useWorkspace } from "@/context/WorkspaceContext";
import { LegalCaseModal } from "@/components/legal/LegalCaseModal";
import {
  BarChartCard,
  FilterChip,
  FilterGroup,
  KpiCard,
  StatusPill,
  formatCount,
} from "@/components/legal/LegalPanelPieces";
import { LEGAL_CASE_SORT_COLUMNS, defaultLegalCaseSort } from "@/tableSort/legal";
import { formatApiError } from "@/utils/apiError";
import { formatCurrencyOrDash, formatCurrencyShortOrDash } from "@/utils/currency";
import {
  LEGAL_STATUS_LABELS,
  LEGAL_STATUS_STYLES,
  LEGAL_TYPE_LABELS,
  fetchLegalOverview,
  getLegalCase,
  listLegalCases,
  type LegalCase,
  type LegalCaseFilters,
  type LegalCaseStatus,
  type LegalCaseType,
  type LegalOverview,
  type LegalValueBasis,
} from "@/services/legal";

/**
 * Processos — tela principal do Workspace Jurídico.
 *
 * Segue o Painel de Passivo: filtros em chips, faixa de valor, busca, KPIs e gráficos que reagem
 * a TODOS os filtros, e barras clicáveis que também filtram. A diferença arquitetural é que os
 * indicadores são calculados no BACKEND sobre os mesmos filtros da lista (`/legal/cases/overview`),
 * não no navegador — assim o número do card nunca diverge da tabela e a tela escala com o acervo.
 */

/** Debounce dos campos de digitação: evita uma consulta por tecla. */
const TYPING_DEBOUNCE_MS = 350;

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function parseAmount(raw: string): number | null {
  const cleaned = raw.replace(/[^\d]/g, "");
  if (!cleaned) return null;
  return Number(cleaned);
}

export function LegalCases() {
  const { setWorkspace } = useWorkspace();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    setWorkspace("legal");
  }, [setWorkspace]);

  // Filtros iniciais vindos da URL: o Dashboard executivo abre esta tela já com o recorte
  // que o diretor clicou (?status=…&uf=…&company=…&project=…&q=…). Lido só na montagem —
  // depois o estado local manda, para não brigar com as interações do usuário.
  const initial = useRef(searchParams);
  const [statuses, setStatuses] = useState<string[]>(() => initial.current.getAll("status"));
  const [types, setTypes] = useState<string[]>(() => initial.current.getAll("type"));
  const [ufs, setUfs] = useState<string[]>(() => initial.current.getAll("uf"));
  const [companies, setCompanies] = useState<string[]>(() => initial.current.getAll("company"));
  const [projects, setProjects] = useState<string[]>(() => initial.current.getAll("project"));
  const [basis, setBasis] = useState<LegalValueBasis>("considered");

  // Campos de texto: estado imediato (input) + estado "aplicado" (dispara a consulta).
  const [searchInput, setSearchInput] = useState(() => initial.current.get("q") ?? "");
  const [minInput, setMinInput] = useState("");
  const [maxInput, setMaxInput] = useState("");
  const [search, setSearch] = useState(() => initial.current.get("q") ?? "");
  const [valueMin, setValueMin] = useState<number | null>(null);
  const [valueMax, setValueMax] = useState<number | null>(null);

  const [cases, setCases] = useState<LegalCase[]>([]);
  const [overview, setOverview] = useState<LegalOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<LegalCase | null>(null);

  // Deep link `?case=<id>`: a Central de Trabalho leva direto ao processo do item clicado.
  // Sem isso, "Abrir caso" deixaria o usuário na lista, procurando de novo o que já achou.
  const deepLinkCase = searchParams.get("case");
  useEffect(() => {
    if (!deepLinkCase || selected) return;
    const found = cases.find((c) => c.id === deepLinkCase);
    if (found) {
      setSelected(found);
      return;
    }
    // Fora da página carregada (filtro ou paginação): busca o processo direto.
    let cancelled = false;
    void getLegalCase(deepLinkCase)
      .then((c) => {
        if (!cancelled) setSelected(c);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [deepLinkCase, cases, selected]);

  useEffect(() => {
    const id = setTimeout(() => {
      setSearch(searchInput);
      setValueMin(parseAmount(minInput));
      setValueMax(parseAmount(maxInput));
    }, TYPING_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [searchInput, minInput, maxInput]);

  // Deep link: /legal/cases?person_id=… (vindo da tela de Pessoas).
  const personId = searchParams.get("person_id") ?? undefined;

  const filters = useMemo<LegalCaseFilters>(
    () => ({
      status: statuses,
      type: types,
      uf: ufs,
      company: companies,
      project: projects,
      person_id: personId,
      value_min: valueMin,
      value_max: valueMax,
      q: search,
      basis,
    }),
    [statuses, types, ufs, companies, projects, personId, valueMin, valueMax, search, basis],
  );

  // Guarda contra respostas fora de ordem: só a requisição mais recente pode escrever no estado.
  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    try {
      const [rows, ov] = await Promise.all([listLegalCases(filters), fetchLegalOverview(filters)]);
      if (seq !== requestSeq.current) return;
      setCases(rows);
      setOverview(ov);
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

  const { sortedRows, headerSort } = useTableSort(cases, LEGAL_CASE_SORT_COLUMNS, {
    defaultCompare: defaultLegalCaseSort,
  });

  const facets = overview?.facets;
  const kpis = overview?.kpis;
  const basisLabel = basis === "considered" ? "considerado" : "valor da causa";

  const hasFilters =
    statuses.length > 0 ||
    types.length > 0 ||
    ufs.length > 0 ||
    companies.length > 0 ||
    projects.length > 0 ||
    !!search ||
    valueMin != null ||
    valueMax != null ||
    !!personId;

  function clearAll() {
    setStatuses([]);
    setTypes([]);
    setUfs([]);
    setCompanies([]);
    setProjects([]);
    setSearchInput("");
    setMinInput("");
    setMaxInput("");
    setSearch("");
    setValueMin(null);
    setValueMax(null);
    // Limpa também o recorte que veio pela URL (Dashboard/Pessoas), senão person_id continuaria ativo.
    if (Array.from(searchParams.keys()).length > 0) setSearchParams(new URLSearchParams());
  }

  const personFilterLabel = personId
    ? (cases[0]?.person_name ?? "pessoa selecionada")
    : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Processos</h1>
          <p className="text-sm text-slate-500">
            {kpis
              ? `${formatCount(kpis.case_count)} processo(s) · passivo ${basisLabel} ${formatCurrencyShortOrDash(
                  basis === "considered" ? kpis.total_considered : kpis.total_claimed,
                )}`
              : "Carregando…"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
          {(Object.keys(LEGAL_STATUS_LABELS) as LegalCaseStatus[])
            .filter((s) => facets?.statuses.includes(s))
            .map((s) => (
              <span key={s} className="inline-flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-sm ${LEGAL_STATUS_STYLES[s].dot}`} aria-hidden />
                {LEGAL_STATUS_LABELS[s]}
              </span>
            ))}
        </div>
      </div>

      {/* ---------------- Filtros ---------------- */}
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4" aria-label="Filtros">
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          <FilterGroup label="Status">
            {(facets?.statuses ?? []).map((s) => (
              <FilterChip
                key={s}
                label={LEGAL_STATUS_LABELS[s]}
                active={statuses.includes(s)}
                onClick={() => setStatuses((prev) => toggle(prev, s))}
                tone={LEGAL_STATUS_STYLES[s].bar}
              />
            ))}
          </FilterGroup>
          <FilterGroup label="Tipo">
            {(facets?.types ?? []).map((t) => (
              <FilterChip
                key={t}
                label={LEGAL_TYPE_LABELS[t as LegalCaseType]}
                active={types.includes(t)}
                onClick={() => setTypes((prev) => toggle(prev, t))}
              />
            ))}
          </FilterGroup>
          <FilterGroup label="Estado">
            {(facets?.ufs ?? []).map((uf) => (
              <FilterChip
                key={uf}
                label={uf}
                active={ufs.includes(uf)}
                onClick={() => setUfs((prev) => toggle(prev, uf))}
              />
            ))}
          </FilterGroup>
        </div>

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

          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Faixa de valor (R$)
            </span>
            <div className="flex items-center gap-2">
              <input
                type="text"
                inputMode="numeric"
                value={minInput}
                onChange={(e) => setMinInput(e.target.value)}
                placeholder="mín"
                aria-label="Valor mínimo"
                className="w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm tabular-nums"
              />
              <span className="text-sm text-slate-400">até</span>
              <input
                type="text"
                inputMode="numeric"
                value={maxInput}
                onChange={(e) => setMaxInput(e.target.value)}
                placeholder="máx"
                aria-label="Valor máximo"
                className="w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm tabular-nums"
              />
            </div>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Pesquisa</span>
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Nome, CPF, processo, empresa, projeto…"
              className="w-72 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>

          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Somar por</span>
            <div className="inline-flex overflow-hidden rounded-lg border border-slate-300">
              {(
                [
                  ["considered", "Considerado"],
                  ["claimed", "Valor da causa"],
                ] as [LegalValueBasis, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={basis === value}
                  onClick={() => setBasis(value)}
                  className={`px-3 py-2 text-xs font-medium ${
                    basis === value ? "bg-indigo-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {hasFilters ? (
            <button
              type="button"
              onClick={clearAll}
              className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Limpar filtros
            </button>
          ) : null}
        </div>

        {companies.length > 0 || projects.length > 0 || personId ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            {personId ? (
              <button
                type="button"
                onClick={() => {
                  const next = new URLSearchParams(searchParams);
                  next.delete("person_id");
                  setSearchParams(next);
                }}
                className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-800 hover:bg-indigo-100"
              >
                Pessoa: {personFilterLabel} <span aria-hidden>×</span>
              </button>
            ) : null}
            {companies.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setCompanies((prev) => toggle(prev, c))}
                className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-200"
              >
                {c} <span aria-hidden>×</span>
              </button>
            ))}
            {projects.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setProjects((prev) => toggle(prev, p))}
                className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-200"
              >
                {p} <span aria-hidden>×</span>
              </button>
            ))}
          </div>
        ) : null}
      </section>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {/* ---------------- Indicadores ---------------- */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <KpiCard
          label="Processos"
          value={kpis ? formatCount(kpis.case_count) : "—"}
          meta={kpis ? `${formatCount(kpis.person_count)} pessoa(s)` : undefined}
        />
        <KpiCard
          label="Valor considerado"
          value={formatCurrencyOrDash(kpis?.total_considered)}
          meta="sem duplicidade"
        />
        <KpiCard label="Valor da causa" value={formatCurrencyOrDash(kpis?.total_claimed)} meta="somatório bruto" />
        <KpiCard
          label="Valor acordado"
          value={formatCurrencyOrDash(kpis?.total_agreed)}
          stripe="bg-violet-500"
        />
        <KpiCard label="Valor pago" value={formatCurrencyOrDash(kpis?.total_paid)} stripe="bg-emerald-500" />
        <KpiCard
          label="Valor pendente"
          value={formatCurrencyOrDash(kpis?.total_pending)}
          stripe="bg-rose-500"
        />
      </section>

      <section className="grid gap-3 lg:grid-cols-3">
        <BarChartCard
          title={`Valor por status (${basisLabel})`}
          buckets={overview?.by_status ?? []}
          selected={statuses}
          onToggle={(key) => setStatuses((prev) => toggle(prev, key))}
          statusColors
        />
        <BarChartCard
          title={`Valor por tipo (${basisLabel})`}
          buckets={overview?.by_type ?? []}
          selected={types}
          onToggle={(key) => setTypes((prev) => toggle(prev, key))}
        />
        <BarChartCard
          title={`Valor por estado (${basisLabel})`}
          buckets={overview?.by_uf ?? []}
          selected={ufs}
          onToggle={(key) => setUfs((prev) => toggle(prev, key))}
        />
      </section>

      {/* ---------------- Lista ---------------- */}
      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <span className="text-xs text-slate-600">
            {loading ? "Carregando…" : `${formatCount(sortedRows.length)} processo(s) exibido(s)`}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <SortableTh label="Processo" column="case_number" {...headerSort} />
                <SortableTh label="Nome" column="person" {...headerSort} />
                <SortableTh label="CPF" column="cpf" {...headerSort} />
                <SortableTh label="Empresa" column="company" {...headerSort} />
                <SortableTh label="Projeto" column="project" {...headerSort} />
                <SortableTh label="UF" column="uf" {...headerSort} />
                <SortableTh label="Status" column="status" {...headerSort} />
                <SortableTh label="Considerado" column="considered" align="right" {...headerSort} />
                <SortableTh label="Valor da causa" column="claimed" align="right" {...headerSort} />
                <SortableTh label="Última movimentação" column="last_movement" {...headerSort} />
                <th className="px-2 py-2 text-center text-xs font-semibold uppercase tracking-wide">
                  JusBrasil
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.length === 0 && !loading ? (
                <tr>
                  <td colSpan={11} className="px-4 py-10 text-center text-sm text-slate-400">
                    Nenhum processo com esses filtros.
                  </td>
                </tr>
              ) : null}
              {sortedRows.map((c) => (
                <tr key={c.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-2 py-2">
                    <button
                      type="button"
                      onClick={() => setSelected(c)}
                      className="font-medium tabular-nums text-indigo-600 hover:underline"
                    >
                      {c.case_number}
                    </button>
                  </td>
                  <td className="max-w-[15rem] truncate px-2 py-2" title={c.person_name ?? c.claimant_name ?? ""}>
                    {c.person_id ? (
                      <button
                        type="button"
                        onClick={() => navigate(`/legal/persons?person_id=${c.person_id}`)}
                        className="hover:underline"
                      >
                        {c.person_name ?? c.claimant_name ?? "—"}
                      </button>
                    ) : (
                      (c.claimant_name ?? "—")
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-600">{c.person_cpf ?? "—"}</td>
                  <td className="max-w-[13rem] truncate px-2 py-2 text-slate-600" title={c.company ?? ""}>
                    {c.company ?? "—"}
                  </td>
                  <td className="max-w-[13rem] truncate px-2 py-2 text-slate-600" title={c.project ?? ""}>
                    {c.project ?? "—"}
                  </td>
                  <td className="px-2 py-2 text-slate-600">{c.uf ?? "—"}</td>
                  <td className="px-2 py-2">
                    <StatusPill status={c.status} label={LEGAL_STATUS_LABELS[c.status]} />
                  </td>
                  <td className="px-2 py-2">
                    <Money value={c.amount_considered} />
                  </td>
                  <td className="px-2 py-2">
                    <Money value={c.amount_claimed} />
                  </td>
                  <td
                    className="max-w-[18rem] truncate px-2 py-2 text-xs text-slate-500"
                    title={c.last_movement ?? ""}
                  >
                    {c.last_movement ?? "—"}
                  </td>
                  <td className="px-2 py-2 text-center">
                    {c.jusbrasil_url ? (
                      <a
                        href={c.jusbrasil_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="Abrir no JusBrasil"
                        className="text-indigo-600 hover:underline"
                      >
                        ↗
                      </a>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selected ? (
        <LegalCaseModal
          legalCase={selected}
          onClose={() => setSelected(null)}
          onOpenPerson={(id) => {
            setSelected(null);
            navigate(`/legal/persons?person_id=${id}`);
          }}
        />
      ) : null}
    </div>
  );
}
