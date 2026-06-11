import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useAuth } from "@/context/AuthContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useScenario, type ScenarioKind } from "@/context/ScenarioContext";
import { hasPermission } from "@/permissions";
import { currentMonth, monthMinus, monthToCompetencia, startOfYear } from "@/utils/roiFormat";
import {
  fetchConsolidatedRoi,
  fetchRoiEvolution,
  fetchRoiOperacionalRanking,
  type ConsolidatedRoi,
  type ProjectRoi,
  type RoiEvolutionPoint,
} from "@/services/indicators";
import { ConsolidatedRoiCard } from "@/components/indicators/ConsolidatedRoiCard";
import { ProjectFilterDropdown } from "@/components/indicators/ProjectFilterDropdown";
import { RoiProjectCard } from "@/components/indicators/RoiProjectCard";
import { RoiEvolutionChart } from "@/components/indicators/RoiEvolutionChart";

type RangePreset = "custom" | "single" | "last3" | "last6" | "last12" | "ytd";

export function RoiOperacional() {
  const { setWorkspace } = useWorkspace();
  const { user } = useAuth();
  const { globalScenario, setGlobalScenario } = useScenario();

  const canDirector = hasPermission(user?.permission_names, "indicators.director");

  // Único contexto temporal da tela.
  const [dataInicial, setDataInicial] = useState<string>(() => currentMonth());
  const [dataFinal, setDataFinal] = useState<string>(() => currentMonth());
  const [preset, setPreset] = useState<RangePreset>("single");

  // Ranking de TODOS os projetos ativos (fonte dos cards e das opções do filtro).
  const [allItems, setAllItems] = useState<ProjectRoi[]>([]);
  // Projetos selecionados (default: todos os ativos).
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const didInitSelection = useRef(false);

  const [consolidated, setConsolidated] = useState<ConsolidatedRoi | null>(null);
  const [evolution, setEvolution] = useState<RoiEvolutionPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Sequência para descartar respostas assíncronas fora de ordem (cliques rápidos no filtro).
  const derivedReqId = useRef(0);

  useEffect(() => {
    setWorkspace("indicators");
  }, [setWorkspace]);

  const di = monthToCompetencia(dataInicial);
  const df = monthToCompetencia(dataFinal);
  const selectedKey = useMemo(() => [...selected].sort().join(","), [selected]);

  // Carrega o ranking de todos os ativos quando muda período/cenário.
  const loadRanking = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ranking = await fetchRoiOperacionalRanking({ dataInicial: di, dataFinal: df, scenario: globalScenario });
      setAllItems(ranking.items);
      // Default: na primeira carga, todos os projetos vêm selecionados.
      if (!didInitSelection.current) {
        setSelected(new Set(ranking.items.map((i) => i.project_id)));
        didInitSelection.current = true;
      }
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível carregar o ROI Operacional.");
    } finally {
      setLoading(false);
    }
  }, [di, df, globalScenario]);

  useEffect(() => {
    void loadRanking();
  }, [loadRanking]);

  // Recalcula consolidado + evolução para os projetos selecionados.
  const loadDerived = useCallback(async () => {
    const ids = selectedKey ? selectedKey.split(",") : [];
    const myId = ++derivedReqId.current;
    if (ids.length === 0) {
      setConsolidated(null);
      setEvolution([]);
      return;
    }
    try {
      const [evo, consol] = await Promise.all([
        fetchRoiEvolution({ dataInicial: di, dataFinal: df, scenario: globalScenario, projectIds: ids }),
        canDirector
          ? fetchConsolidatedRoi({ dataInicial: di, dataFinal: df, scenario: globalScenario, projectIds: ids })
          : Promise.resolve(null),
      ]);
      // Ignora respostas obsoletas (uma requisição mais recente já foi disparada).
      if (myId !== derivedReqId.current) return;
      setEvolution(evo.points);
      setConsolidated(consol);
    } catch {
      if (myId !== derivedReqId.current) return;
      setConsolidated(null);
      setEvolution([]);
    }
  }, [di, df, globalScenario, selectedKey, canDirector]);

  useEffect(() => {
    void loadDerived();
  }, [loadDerived]);

  function applyPreset(p: RangePreset) {
    setPreset(p);
    const anchor = currentMonth();
    if (p === "single") {
      setDataInicial(anchor);
      setDataFinal(anchor);
    } else if (p === "last3") {
      setDataInicial(monthMinus(anchor, 2));
      setDataFinal(anchor);
    } else if (p === "last6") {
      setDataInicial(monthMinus(anchor, 5));
      setDataFinal(anchor);
    } else if (p === "last12") {
      setDataInicial(monthMinus(anchor, 11));
      setDataFinal(anchor);
    } else if (p === "ytd") {
      setDataInicial(startOfYear(anchor));
      setDataFinal(anchor);
    }
  }

  function toggleProject(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const projectOptions = useMemo(
    () => allItems.map((i) => ({ id: i.project_id, name: i.project_name })),
    [allItems],
  );
  const cards = useMemo(() => allItems.filter((i) => selected.has(i.project_id)), [allItems, selected]);

  const isRange = dataInicial !== dataFinal;
  const noneSelected = selected.size === 0;
  const hasCardData = cards.some((i) => i.roi !== null);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">ROI Operacional</h1>
        <p className="mt-1 text-sm text-slate-500">
          Lucro Operacional ÷ Custo Total{" "}
          {isRange ? "(acumulado no período selecionado)" : "(competência selecionada)"}. Consolidado, cards e
          gráficos respondem ao mesmo período e aos projetos selecionados.
        </p>
      </div>

      {/* FILTROS — período, projetos e cenário (única fonte) */}
      <div className="flex flex-wrap items-end gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-600">Data inicial</span>
          <input
            type="month"
            value={dataInicial}
            onChange={(e) => {
              setPreset("custom");
              setDataInicial(e.target.value || dataInicial);
            }}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-600">Data final</span>
          <input
            type="month"
            value={dataFinal}
            onChange={(e) => {
              setPreset("custom");
              setDataFinal(e.target.value || dataFinal);
            }}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none"
          />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-600">Projetos</span>
          <ProjectFilterDropdown options={projectOptions} selected={selected} onToggle={toggleProject} />
        </div>
        <div className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-600">Atalhos</span>
          <div className="inline-flex flex-wrap gap-1">
            {(
              [
                ["single", "Mês atual"],
                ["last3", "3 meses"],
                ["last6", "6 meses"],
                ["last12", "12 meses"],
                ["ytd", "Ano atual"],
              ] as [RangePreset, string][]
            ).map(([p, label]) => (
              <button
                key={p}
                type="button"
                onClick={() => applyPreset(p)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
                  preset === p
                    ? "border-indigo-600 bg-indigo-600 text-white"
                    : "border-slate-300 text-slate-700 hover:bg-slate-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-600">Cenário</span>
          <div className="inline-flex overflow-hidden rounded-lg border border-slate-300">
            {(["REALIZADO", "PREVISTO"] as ScenarioKind[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setGlobalScenario(s)}
                className={`px-3 py-1.5 text-sm font-medium ${
                  globalScenario === s ? "bg-indigo-600 text-white" : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                {s === "REALIZADO" ? "Realizado" : "Previsto"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : loading ? (
        <p className="text-sm text-slate-500">Carregando…</p>
      ) : noneSelected ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
          Selecione ao menos um projeto para visualizar as métricas.
        </div>
      ) : (
        <>
          {/* 1) CONSOLIDADO DA EMPRESA */}
          {canDirector && consolidated ? (
            <ConsolidatedRoiCard
              data={consolidated}
              title="Consolidado da empresa"
              subtitle={
                selected.size === projectOptions.length
                  ? isRange
                    ? "Acumulado do período · todos os projetos ativos"
                    : "Todos os projetos ativos"
                  : `${selected.size} de ${projectOptions.length} projeto(s) selecionado(s)`
              }
            />
          ) : null}

          {/* 2) CARDS DE ROI POR PROJETO */}
          {cards.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
              Nenhum projeto selecionado.
            </div>
          ) : !hasCardData ? (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
              Não há dados para o período selecionado.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {cards.map((item) => (
                <RoiProjectCard key={item.project_id} item={item} />
              ))}
            </div>
          )}

          {/* 3) GRÁFICOS — ROI (%) e Financeira, mesmo período e projetos */}
          <RoiEvolutionChart points={evolution} />
        </>
      )}
    </div>
  );
}
