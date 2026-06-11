import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { AssetOperationalAlertCard } from "@/components/assets/AssetOperationalAlertCard";
import { AssetsDashboardCharts } from "@/components/assets/AssetsDashboardCharts";
import { formatBRL, PHYSICAL_CONDITION_LABELS } from "@/components/assets/assetLabels";
import { useWorkspace } from "@/context/WorkspaceContext";
import {
  fetchAssetsDashboard,
  type AssetDashboardCountValue,
  type AssetDashboardRead,
} from "@/services/assetsDashboard";

function KpiDual({
  label,
  data,
  accent,
}: {
  label: string;
  data: AssetDashboardCountValue;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums text-slate-900 ${accent ?? ""}`}>{data.count}</p>
      <p className="mt-1 text-sm tabular-nums text-slate-600">{formatBRL(data.value)}</p>
    </div>
  );
}

function KpiSimple({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-lg font-semibold tabular-nums text-slate-900 ${accent ?? ""}`}>{value}</p>
    </div>
  );
}

export function AssetsDashboard() {
  const { setWorkspace } = useWorkspace();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AssetDashboardRead | null>(null);

  useEffect(() => {
    setWorkspace("assets");
  }, [setWorkspace]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAssetsDashboard());
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível carregar o dashboard patrimonial.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="flex items-center gap-3 text-slate-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        Carregando…
      </div>
    );
  }

  const s = data?.status;
  const alerts = data?.alerts;
  const fair = alerts?.fair_condition;

  return (
    <div className="mx-auto max-w-[1400px] space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Dashboard Patrimonial</h1>
          <p className="mt-1 text-sm text-slate-600">Visão consolidada de ativos, valores e alertas operacionais.</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="h-[42px] rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50"
        >
          Atualizar
        </button>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      ) : null}

      {s ? (
        <>
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Quantidade</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <KpiDual label="Total de ativos" data={s.total} />
              <KpiDual label="Em uso" data={s.in_use} />
              <KpiDual label="Disponíveis" data={s.available} />
              <KpiDual label="Em manutenção" data={s.maintenance} />
              <KpiDual label="Perdidos / baixados" data={s.lost_or_discarded} accent="text-red-800" />
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Financeiro</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <KpiSimple label="Valor patrimonial total" value={formatBRL(s.total.value)} />
              <KpiSimple label="Valor em uso" value={formatBRL(s.in_use.value)} />
              <KpiSimple label="Valor disponível" value={formatBRL(s.available.value)} />
              <KpiSimple label="Valor em manutenção" value={formatBRL(s.maintenance.value)} />
              <KpiSimple label="Valor perdido / baixado" value={formatBRL(s.lost_or_discarded.value)} accent="text-red-800" />
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Estado físico</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {(data?.physical_condition ?? []).map((row) => (
                <KpiDual
                  key={row.condition}
                  label={
                    row.label ||
                    PHYSICAL_CONDITION_LABELS[row.condition as keyof typeof PHYSICAL_CONDITION_LABELS] ||
                    row.condition
                  }
                  data={{ count: row.count, value: row.value }}
                  accent={
                    row.condition === "DAMAGED"
                      ? "text-red-800"
                      : row.condition === "FAIR"
                        ? "text-amber-800"
                        : undefined
                  }
                />
              ))}
            </div>
          </section>
        </>
      ) : null}

      {data ? (
        <AssetsDashboardCharts
          byCategory={data.by_category}
          byCostCenter={data.by_cost_center}
          physicalCondition={data.physical_condition}
        />
      ) : null}

      {alerts ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Alertas operacionais</h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <AssetOperationalAlertCard
              title="Inspeções vencidas"
              count={alerts.expired_inspections.count}
              amountTotal={alerts.expired_inspections.amount_total}
              tone="red"
              viewHref="/assets?expiration=expired"
              emptyLabel="Nenhuma inspeção vencida."
            />
            <AssetOperationalAlertCard
              title="Vence em 30 dias"
              count={alerts.expiring_inspections.count}
              amountTotal={alerts.expiring_inspections.amount_total}
              tone="amber"
              viewHref="/assets?expiration=30"
              emptyLabel="Nenhuma inspeção a vencer em 30 dias."
            />
            <AssetOperationalAlertCard
              title="Sem responsável"
              count={alerts.without_holder.count}
              amountTotal={alerts.without_holder.amount_total}
              tone="slate"
              viewHref="/assets?without_holder=true"
              emptyLabel="Todos os ativos possuem responsável."
              badge="Sem rastreabilidade"
            />
            <AssetOperationalAlertCard
              title="Mau estado"
              count={alerts.fair_condition.count}
              amountTotal={alerts.fair_condition.amount_total}
              tone="amber"
              viewHref="/assets?physical_condition=FAIR"
              emptyLabel="Nenhum ativo em mau estado."
              extraLine={
                fair && (fair.damaged_count ?? 0) > 0
                  ? `${fair.damaged_count} quebrado${fair.damaged_count === 1 ? "" : "s"} no patrimônio`
                  : undefined
              }
            />
          </div>
        </section>
      ) : null}
    </div>
  );
}
