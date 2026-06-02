import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { usePermission } from "@/hooks/usePermission";
import { downloadAuditLogExport } from "@/services/audit";
import { fetchSettings, updateSettings, type SystemSettings } from "@/services/settings";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";

function NumInput({
  label,
  value,
  onChange,
  step = "0.0001",
  disabled,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  step?: string;
  disabled?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>
      <input
        type="number"
        step={step}
        disabled={disabled}
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-60"
      />
    </div>
  );
}

function toUtcStart(isoDate: string): string {
  return `${isoDate}T00:00:00.000Z`;
}

function toUtcEnd(isoDate: string): string {
  return `${isoDate}T23:59:59.999Z`;
}

export function Settings() {
  const canEditSettings = usePermission("settings.edit");
  const canViewSettings = usePermission("settings.view");
  const canExportAudit = usePermission("audit.export");
  const location = useLocation();
  const auditSectionRef = useRef<HTMLElement | null>(null);

  const [s, setS] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const [auditDateStart, setAuditDateStart] = useState("");
  const [auditDateEnd, setAuditDateEnd] = useState("");
  const [auditEntity, setAuditEntity] = useState("");
  const [auditExporting, setAuditExporting] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  useEffect(() => {
    if (!canViewSettings) {
      setLoading(false);
      return;
    }
    let c = false;
    (async () => {
      try {
        const data = await fetchSettings();
        if (!c) setS(data);
      } catch (e) {
        if (!c) {
          setError(
            isAxiosError(e) && e.response?.status === 403
              ? "Sem permissão para visualizar configurações."
              : "Erro ao carregar configurações.",
          );
        }
      } finally {
        if (!c) setLoading(false);
      }
    })();
    return () => {
      c = true;
    };
  }, [canViewSettings]);

  useEffect(() => {
    if (!canExportAudit || loading) return;
    if (location.hash !== "#auditoria") return;
    auditSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [canExportAudit, loading, location.hash]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!canEditSettings) return;
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
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleAuditExport() {
    if (!canExportAudit) return;
    setAuditExporting(true);
    setAuditError(null);
    try {
      await downloadAuditLogExport({
        date_start: auditDateStart ? toUtcStart(auditDateStart) : undefined,
        date_end: auditDateEnd ? toUtcEnd(auditDateEnd) : undefined,
        entity: auditEntity.trim() || undefined,
      });
    } catch (e) {
      setAuditError(formatApiError(e));
    } finally {
      setAuditExporting(false);
    }
  }

  if (!canViewSettings && !canExportAudit) {
    return <p className="text-slate-600">Sem permissão para acessar esta página.</p>;
  }

  if (loading) {
    return <div className="text-slate-500">Carregando…</div>;
  }

  const pageTitle = canViewSettings ? "Configurações" : "Log de auditoria";
  const pageSubtitle = canViewSettings
    ? "Regras financeiras e parâmetros de custo (singleton)"
    : "Exportação do histórico de alterações rastreadas pelo sistema";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">{pageTitle}</h2>
        <p className="text-sm text-slate-500">{pageSubtitle}</p>
      </div>

      {canExportAudit && (
        <section
          id="auditoria"
          ref={auditSectionRef}
          className="scroll-mt-6 rounded-xl border border-indigo-200 bg-white p-6 shadow-sm ring-1 ring-indigo-100"
        >
          <h3 className="text-sm font-semibold text-slate-800">Relatório de auditoria</h3>
          <p className="mt-1 text-xs text-slate-500">
            Registro de criações, alterações e exclusões rastreadas pelo sistema (usuários, projetos,
            colaboradores, veículos, receitas, permissões, login, etc.), com diff de campos, IP e
            user-agent. Alguns módulos (ex.: histórico textual de NFs) usam log próprio no registro.
          </p>

          {auditError && (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              {auditError}
            </div>
          )}

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Data inicial (opcional)</label>
              <input
                type="date"
                value={auditDateStart}
                onChange={(e) => setAuditDateStart(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Data final (opcional)</label>
              <input
                type="date"
                value={auditDateEnd}
                onChange={(e) => setAuditDateEnd(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Entidade (opcional, ex.: user, project, employee)
              </label>
              <input
                type="text"
                value={auditEntity}
                onChange={(e) => setAuditEntity(e.target.value)}
                placeholder="Filtrar por tipo de registro"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <button
            type="button"
            disabled={auditExporting}
            onClick={() => void handleAuditExport()}
            className="mt-4 rounded-lg bg-slate-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
          >
            {auditExporting ? "Gerando relatório…" : "Exportar log (.txt)"}
          </button>
        </section>
      )}

      {canViewSettings && s && (
        <>
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
                <NumInput
                  label="Impostos (tax_rate)"
                  value={s.tax_rate}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, tax_rate: v })}
                />
                <NumInput
                  label="Rateio / overhead (overhead_rate)"
                  value={s.overhead_rate}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, overhead_rate: v })}
                />
                <NumInput
                  label="Antecipação (anticipation_rate)"
                  value={s.anticipation_rate}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, anticipation_rate: v })}
                />
                <NumInput
                  label="Encargos CLT (clt_charges_rate) — reserva"
                  value={s.clt_charges_rate}
                  disabled={!canEditSettings}
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
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, vehicle_light_cost: v })}
                  step="0.01"
                />
                <NumInput
                  label="Pickup"
                  value={s.vehicle_pickup_cost}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, vehicle_pickup_cost: v })}
                  step="0.01"
                />
                <NumInput
                  label="Sedan"
                  value={s.vehicle_sedan_cost}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, vehicle_sedan_cost: v })}
                  step="0.01"
                />
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-800">Combustível (R$/L)</h3>
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <NumInput
                  label="Etanol"
                  value={s.fuel_ethanol}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, fuel_ethanol: v })}
                />
                <NumInput
                  label="Gasolina"
                  value={s.fuel_gasoline}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, fuel_gasoline: v })}
                />
                <NumInput
                  label="Diesel"
                  value={s.fuel_diesel}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, fuel_diesel: v })}
                />
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-800">Consumo (km/L)</h3>
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <NumInput
                  label="Leve"
                  value={s.consumption_light}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, consumption_light: v })}
                />
                <NumInput
                  label="Pickup"
                  value={s.consumption_pickup}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, consumption_pickup: v })}
                />
                <NumInput
                  label="Sedan"
                  value={s.consumption_sedan}
                  disabled={!canEditSettings}
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
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, vr_value: v })}
                  step="0.01"
                />
              </div>
            </section>

            <button
              type="submit"
              disabled={saving || !canEditSettings}
              className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
            >
              {saving ? "Salvando…" : "Salvar configurações"}
            </button>
          </form>
        </>
      )}

      {canViewSettings && !s && error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</div>
      )}
    </div>
  );
}
