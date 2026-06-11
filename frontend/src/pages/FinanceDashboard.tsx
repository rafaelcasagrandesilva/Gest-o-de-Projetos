import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { fetchReceivableKpis } from "@/services/receivables";

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function FinanceDashboard() {
  console.log("FinanceDashboard renderizou");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [kpis, setKpis] = useState<Awaited<ReturnType<typeof fetchReceivableKpis>> | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchReceivableKpis({ period_field: "due" });
        setKpis(data);
      } catch (err) {
        if (isAxiosError(err)) setError(String(err.response?.data?.detail ?? err.message));
        else setError("Não foi possível carregar o dashboard financeiro.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-3 text-slate-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        Carregando…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Dashboard Financeiro</h1>
        <p className="mt-1 text-sm text-slate-600">Indicadores rápidos (baseado em contas a receber).</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <Kpi label="Total Líquido a receber" value={kpis ? formatBRL(kpis.total_a_receber) : "—"} />
        <Kpi label="Total Bruto a receber" value={kpis ? formatBRL(kpis.total_bruto_a_receber) : "—"} />
        <Kpi label="Recebido no mês" value={kpis ? formatBRL(kpis.recebido_no_mes) : "—"} />
        <Kpi label="Em atraso" value={kpis ? formatBRL(kpis.em_atraso_valor) : "—"} accent="text-red-800" />
      </section>
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-lg font-semibold tabular-nums text-slate-900 ${accent ?? ""}`}>{value}</p>
    </div>
  );
}

