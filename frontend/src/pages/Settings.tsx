import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { usePermission } from "@/hooks/usePermission";
import { MissingFilesSection } from "@/components/settings/MissingFilesSection";
import { PaymentComponentTypesSettings } from "@/components/settings/PaymentComponentTypesSettings";
import { downloadAuditLogExport } from "@/services/audit";
import {
  createTaxRegime,
  deleteTaxRegime,
  fetchSettings,
  fetchTaxRegimes,
  updateSettings,
  type SystemSettings,
  type TaxRegime,
  type TaxRegimePeriod,
} from "@/services/settings";
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

const TAX_REGIME_LABEL: Record<TaxRegime, string> = {
  LUCRO_PRESUMIDO: "Lucro Presumido",
  LUCRO_REAL: "Lucro Real",
};

/** "2026-09-01" → "09/2026" */
function formatMonthYear(isoDate: string): string {
  return `${isoDate.slice(5, 7)}/${isoDate.slice(0, 4)}`;
}

function todayIso(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function toUtcStart(isoDate: string): string {
  return `${isoDate}T00:00:00.000Z`;
}

function toUtcEnd(isoDate: string): string {
  return `${isoDate}T23:59:59.999Z`;
}

export function Settings() {
  const canEditSettings = usePermission("settings.update");
  const canViewSettings = usePermission("settings.read");
  const canExportAudit = usePermission("audit.export");
  const isSystemAdmin = usePermission("system.admin");
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

  const [regimes, setRegimes] = useState<TaxRegimePeriod[]>([]);
  const [regimeError, setRegimeError] = useState<string | null>(null);
  const [regimeBusy, setRegimeBusy] = useState(false);
  const [newRegime, setNewRegime] = useState<TaxRegime>("LUCRO_REAL");
  const [newRegimeMonth, setNewRegimeMonth] = useState("");
  const [newRegimeNote, setNewRegimeNote] = useState("");

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
        try {
          const periods = await fetchTaxRegimes();
          if (!c) setRegimes(periods);
        } catch (e) {
          if (!c) setRegimeError(formatApiError(e));
        }
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
        anticipation_mode: s.anticipation_mode,
        clt_charges_rate: s.clt_charges_rate,
        iss_rate: s.iss_rate,
        pis_presumido_rate: s.pis_presumido_rate,
        cofins_presumido_rate: s.cofins_presumido_rate,
        irpj_presumption_rate: s.irpj_presumption_rate,
        csll_presumption_rate: s.csll_presumption_rate,
        irpj_rate: s.irpj_rate,
        irpj_additional_rate: s.irpj_additional_rate,
        irpj_additional_monthly_threshold: s.irpj_additional_monthly_threshold,
        csll_rate: s.csll_rate,
        pis_real_rate: s.pis_real_rate,
        cofins_real_rate: s.cofins_real_rate,
        pis_cofins_credit_rate: s.pis_cofins_credit_rate,
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

  async function handleAddRegime() {
    if (!canEditSettings || regimeBusy) return;
    if (!newRegimeMonth) {
      setRegimeError("Informe o mês em que o regime passa a valer.");
      return;
    }
    setRegimeBusy(true);
    setRegimeError(null);
    try {
      await createTaxRegime({
        regime: newRegime,
        start_date: `${newRegimeMonth}-01`,
        note: newRegimeNote.trim() || null,
      });
      setRegimes(await fetchTaxRegimes());
      setNewRegimeMonth("");
      setNewRegimeNote("");
    } catch (e) {
      setRegimeError(formatApiError(e));
    } finally {
      setRegimeBusy(false);
    }
  }

  async function handleRemoveRegime(period: TaxRegimePeriod) {
    if (!canEditSettings || regimeBusy) return;
    const ok = window.confirm(
      `Remover o período ${TAX_REGIME_LABEL[period.regime]} a partir de ${formatMonthYear(period.start_date)}?`,
    );
    if (!ok) return;
    setRegimeBusy(true);
    setRegimeError(null);
    try {
      await deleteTaxRegime(period.id);
      setRegimes(await fetchTaxRegimes());
    } catch (e) {
      setRegimeError(formatApiError(e));
    } finally {
      setRegimeBusy(false);
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

  const today = todayIso();
  const currentRegimeId =
    [...regimes].filter((p) => p.start_date <= today).sort((a, b) => b.start_date.localeCompare(a.start_date))[0]
      ?.id ?? null;

  const pageTitle = canViewSettings ? "Configurações" : "Log de auditoria";
  const pageSubtitle = canViewSettings
    ? "Regras financeiras e parâmetros de custo (singleton)"
    : "Exportação do histórico de alterações rastreadas pelo sistema";

  return (
    <div className="space-y-5">
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

      {isSystemAdmin && <MissingFilesSection />}

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

          <form onSubmit={handleSave} className="space-y-4">
            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-800">Percentuais (0–1)</h3>
              <p className="mb-4 text-xs text-slate-500">Ex.: 9% imposto → 0,09</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <NumInput
                  label="Impostos — reserva (usado só em meses sem regime cadastrado)"
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
                <div className="sm:col-span-2 grid gap-4 rounded-lg border border-slate-100 bg-slate-50/60 p-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">
                      Custo de antecipação
                    </label>
                    <select
                      value={s.anticipation_mode ?? "AUTOMATICO"}
                      disabled={!canEditSettings}
                      onChange={(e) =>
                        setS({ ...s, anticipation_mode: e.target.value as SystemSettings["anticipation_mode"] })
                      }
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm disabled:opacity-60"
                    >
                      <option value="AUTOMATICO">Automático — custo real dos borderôs</option>
                      <option value="FIXO">Fixo — percentual ao lado</option>
                    </select>
                    <p className="mt-1 text-xs text-slate-500">
                      {(s.anticipation_mode ?? "AUTOMATICO") === "AUTOMATICO"
                        ? "O mês trabalhado usa o custo real das antecipações do mês SEGUINTE (Lepta + Daycoval, sem repasse) ÷ receita do mês; sem operações ainda, ou no previsto, usa a média dos meses já fechados."
                        : "Aplica o percentual fixo sobre a receita, como antes."}
                    </p>
                  </div>
                  <NumInput
                    label={
                      (s.anticipation_mode ?? "AUTOMATICO") === "AUTOMATICO"
                        ? "Antecipação fixa (reserva: usada só sem histórico)"
                        : "Antecipação fixa (anticipation_rate)"
                    }
                    value={s.anticipation_rate}
                    disabled={!canEditSettings}
                    onChange={(v) => setS({ ...s, anticipation_rate: v })}
                  />
                </div>
                <NumInput
                  label="Encargos CLT (clt_charges_rate) — reserva"
                  value={s.clt_charges_rate}
                  disabled={!canEditSettings}
                  onChange={(v) => setS({ ...s, clt_charges_rate: v })}
                />
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-800">Regime tributário</h3>
              <p className="mb-4 text-xs text-slate-500">
                Os impostos do Dashboard Operacional e do Resultado da Empresa são calculados pelo regime vigente em
                cada competência. Para mudar de regime, adicione um novo período com a data em que a mudança passa a
                valer — os meses anteriores continuam no regime antigo.
              </p>

              {regimeError && (
                <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                  {regimeError}
                </div>
              )}

              <div className="overflow-x-auto rounded-lg border border-slate-100">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs font-medium text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Regime</th>
                      <th className="px-3 py-2">Vigente a partir de</th>
                      <th className="px-3 py-2">Observação</th>
                      {canEditSettings && <th className="px-3 py-2 text-right" />}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {regimes.length === 0 && (
                      <tr>
                        <td colSpan={canEditSettings ? 4 : 3} className="px-3 py-3 text-xs text-slate-500">
                          Nenhum regime cadastrado — todos os meses usam o percentual de reserva.
                        </td>
                      </tr>
                    )}
                    {regimes.map((p) => (
                      <tr key={p.id}>
                        <td className="px-3 py-2 text-slate-800">
                          {TAX_REGIME_LABEL[p.regime] ?? p.regime}
                          {p.id === currentRegimeId && (
                            <span className="ml-2 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
                              vigente
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 tabular-nums text-slate-700">{formatMonthYear(p.start_date)}</td>
                        <td className="px-3 py-2 text-slate-600">{p.note ?? "—"}</td>
                        {canEditSettings && (
                          <td className="px-3 py-2 text-right">
                            {regimes.length > 1 && (
                              <button
                                type="button"
                                disabled={regimeBusy}
                                onClick={() => void handleRemoveRegime(p)}
                                className="text-xs font-medium text-red-600 hover:text-red-500 disabled:opacity-60"
                              >
                                Remover
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {canEditSettings && (
                <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_2fr_auto] sm:items-end">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Regime</label>
                    <select
                      value={newRegime}
                      onChange={(e) => setNewRegime(e.target.value as TaxRegime)}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      <option value="LUCRO_PRESUMIDO">Lucro Presumido</option>
                      <option value="LUCRO_REAL">Lucro Real</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Vigente a partir de</label>
                    <input
                      type="month"
                      value={newRegimeMonth}
                      onChange={(e) => setNewRegimeMonth(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Observação (opcional)</label>
                    <input
                      type="text"
                      maxLength={255}
                      value={newRegimeNote}
                      onChange={(e) => setNewRegimeNote(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void handleAddRegime();
                        }
                      }}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    />
                  </div>
                  <button
                    type="button"
                    disabled={regimeBusy}
                    onClick={() => void handleAddRegime()}
                    className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
                  >
                    Adicionar
                  </button>
                </div>
              )}

              <div className="mt-6 space-y-4">
                <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
                  <h4 className="text-xs font-semibold text-slate-700">Lucro Presumido</h4>
                  <p className="mb-3 text-xs text-slate-500">
                    IRPJ = receita × presunção × IRPJ (+ adicional acima do limite mensal); CSLL = receita × presunção ×
                    CSLL
                  </p>
                  <div className="grid gap-4 sm:grid-cols-4">
                    <NumInput
                      label="PIS"
                      value={s.pis_presumido_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, pis_presumido_rate: v })}
                    />
                    <NumInput
                      label="COFINS"
                      value={s.cofins_presumido_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, cofins_presumido_rate: v })}
                    />
                    <NumInput
                      label="Presunção IRPJ"
                      value={s.irpj_presumption_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, irpj_presumption_rate: v })}
                    />
                    <NumInput
                      label="Presunção CSLL"
                      value={s.csll_presumption_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, csll_presumption_rate: v })}
                    />
                  </div>
                </div>

                <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
                  <h4 className="text-xs font-semibold text-slate-700">Lucro Real</h4>
                  <p className="mb-3 text-xs text-slate-500">
                    IRPJ e CSLL no Lucro Real incidem sobre o lucro e são calculados apenas no Resultado da Empresa.
                  </p>
                  <div className="grid gap-4 sm:grid-cols-3">
                    <NumInput
                      label="PIS"
                      value={s.pis_real_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, pis_real_rate: v })}
                    />
                    <NumInput
                      label="COFINS"
                      value={s.cofins_real_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, cofins_real_rate: v })}
                    />
                    <NumInput
                      label="Créditos de PIS/COFINS (% da receita)"
                      value={s.pis_cofins_credit_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, pis_cofins_credit_rate: v })}
                    />
                  </div>
                </div>

                <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
                  <h4 className="text-xs font-semibold text-slate-700">Comuns aos dois regimes</h4>
                  <p className="mb-3 text-xs text-slate-500">
                    O adicional de IRPJ incide sobre a base que exceder o limite mensal.
                  </p>
                  <div className="grid gap-4 sm:grid-cols-5">
                    <NumInput
                      label="ISS"
                      value={s.iss_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, iss_rate: v })}
                    />
                    <NumInput
                      label="IRPJ"
                      value={s.irpj_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, irpj_rate: v })}
                    />
                    <NumInput
                      label="Adicional de IRPJ"
                      value={s.irpj_additional_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, irpj_additional_rate: v })}
                    />
                    <NumInput
                      label="Limite mensal do adicional (R$)"
                      value={s.irpj_additional_monthly_threshold}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, irpj_additional_monthly_threshold: v })}
                      step="0.01"
                    />
                    <NumInput
                      label="CSLL"
                      value={s.csll_rate}
                      disabled={!canEditSettings}
                      onChange={(v) => setS({ ...s, csll_rate: v })}
                    />
                  </div>
                </div>
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

          <PaymentComponentTypesSettings canEdit={canEditSettings} />
        </>
      )}

      {canViewSettings && !s && error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</div>
      )}
    </div>
  );
}
