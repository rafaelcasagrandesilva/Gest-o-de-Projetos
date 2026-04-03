import { useEffect, useState } from "react";
import { fetchSettings, updateSettings, type SystemSettings } from "@/services/settings";
import { isAxiosError } from "axios";

function NumInput({
  label,
  value,
  onChange,
  step = "0.0001",
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  step?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>
      <input
        type="number"
        step={step}
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
      />
    </div>
  );
}

export function Settings() {
  const [s, setS] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    let c = false;
    (async () => {
      try {
        const data = await fetchSettings();
        if (!c) setS(data);
      } catch (e) {
        if (!c) {
          setError(
            isAxiosError(e) && e.response?.status === 403
              ? "Apenas Admin ou Diretor."
              : "Erro ao carregar configurações."
          );
        }
      } finally {
        if (!c) setLoading(false);
      }
    })();
    return () => {
      c = true;
    };
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!s) return;
    setSaving(true);
    setError(null);
    setOk(false);
    try {
      const next = await updateSettings({
        tax_rate: s.tax_rate,
        overhead_rate: s.overhead_rate,
        anticipation_rate: s.anticipation_rate,
        clt_charges_rate: s.clt_charges_rate,
        vehicle_light_cost: s.vehicle_light_cost,
        vehicle_pickup_cost: s.vehicle_pickup_cost,
        vehicle_sedan_cost: s.vehicle_sedan_cost,
        vr_value: s.vr_value,
        fuel_ethanol: s.fuel_ethanol,
        fuel_gasoline: s.fuel_gasoline,
        fuel_diesel: s.fuel_diesel,
        consumption_light: s.consumption_light,
        consumption_pickup: s.consumption_pickup,
        consumption_sedan: s.consumption_sedan,
      });
      setS(next);
      setOk(true);
    } catch {
      setError("Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="text-slate-500">Carregando…</div>;
  }
  if (error && !s) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</div>
    );
  }
  if (!s) return null;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Configurações</h2>
        <p className="text-sm text-slate-500">Regras financeiras e parâmetros de custo (singleton)</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}
      {ok && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          Salvo com sucesso.
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-8">
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">Percentuais (0–1)</h3>
          <p className="mb-4 text-xs text-slate-500">Ex.: 9% imposto → 0,09</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <NumInput label="Impostos (tax_rate)" value={s.tax_rate} onChange={(v) => setS({ ...s, tax_rate: v })} />
            <NumInput
              label="Rateio / overhead (overhead_rate)"
              value={s.overhead_rate}
              onChange={(v) => setS({ ...s, overhead_rate: v })}
            />
            <NumInput
              label="Antecipação (anticipation_rate)"
              value={s.anticipation_rate}
              onChange={(v) => setS({ ...s, anticipation_rate: v })}
            />
            <NumInput
              label="Encargos CLT (clt_charges_rate) — reserva"
              value={s.clt_charges_rate}
              onChange={(v) => setS({ ...s, clt_charges_rate: v })}
            />
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">Veículos (custo fixo mensal R$)</h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <NumInput
              label="Leve"
              value={s.vehicle_light_cost}
              onChange={(v) => setS({ ...s, vehicle_light_cost: v })}
              step="0.01"
            />
            <NumInput
              label="Pickup"
              value={s.vehicle_pickup_cost}
              onChange={(v) => setS({ ...s, vehicle_pickup_cost: v })}
              step="0.01"
            />
            <NumInput
              label="Sedan"
              value={s.vehicle_sedan_cost}
              onChange={(v) => setS({ ...s, vehicle_sedan_cost: v })}
              step="0.01"
            />
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">Combustível (R$/L)</h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <NumInput label="Etanol" value={s.fuel_ethanol} onChange={(v) => setS({ ...s, fuel_ethanol: v })} />
            <NumInput label="Gasolina" value={s.fuel_gasoline} onChange={(v) => setS({ ...s, fuel_gasoline: v })} />
            <NumInput label="Diesel" value={s.fuel_diesel} onChange={(v) => setS({ ...s, fuel_diesel: v })} />
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">Consumo (km/L)</h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <NumInput
              label="Leve"
              value={s.consumption_light}
              onChange={(v) => setS({ ...s, consumption_light: v })}
            />
            <NumInput
              label="Pickup"
              value={s.consumption_pickup}
              onChange={(v) => setS({ ...s, consumption_pickup: v })}
            />
            <NumInput
              label="Sedan"
              value={s.consumption_sedan}
              onChange={(v) => setS({ ...s, consumption_sedan: v })}
            />
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">Benefícios</h3>
          <div className="mt-4 max-w-xs">
            <NumInput
              label="Vale refeição diário (R$)"
              value={s.vr_value}
              onChange={(v) => setS({ ...s, vr_value: v })}
              step="0.01"
            />
          </div>
        </section>

        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {saving ? "Salvando…" : "Salvar configurações"}
        </button>
      </form>
    </div>
  );
}
