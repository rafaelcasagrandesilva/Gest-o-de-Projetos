import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  addInvoicePayment,
  createReceivableInvoice,
  deleteInvoicePayment,
  deleteReceivableInvoice,
  fetchInvoicePayments,
  fetchReceivableInvoices,
  fetchReceivableKpis,
  type NfStatus,
  type ReceivableInvoice,
  type ReceivablePayment,
} from "@/services/receivables";
import { usePermission } from "@/hooks/usePermission";
import { listProjects, type Project } from "@/services/projects";
import { isAxiosError } from "axios";

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function parseMoneyInput(raw: string): number {
  const t = raw.replace(/\s/g, "").replace(/R\$\s?/i, "");
  const n = Number.parseFloat(t.replace(/\./g, "").replace(",", "."));
  return Number.isFinite(n) ? Math.max(0, n) : 0;
}

function statusBadge(status: NfStatus): string {
  if (status === "PAGA") return "bg-emerald-100 text-emerald-900 ring-emerald-200";
  if (status === "ATRASADA") return "bg-red-100 text-red-900 ring-red-200";
  return "bg-slate-100 text-slate-800 ring-slate-200";
}

function monthToYm(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function Invoices() {
  const canEditInvoices = usePermission("invoices.edit");
  const [projects, setProjects] = useState<Project[]>([]);
  const [period, setPeriod] = useState(() => monthToYm(new Date()));
  const [projectId, setProjectId] = useState("");
  const [statusFilter, setStatusFilter] = useState<NfStatus | "">("");

  const [rows, setRows] = useState<ReceivableInvoice[]>([]);
  const [kpis, setKpis] = useState<Awaited<ReturnType<typeof fetchReceivableKpis>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [payCache, setPayCache] = useState<Record<string, ReceivablePayment[]>>({});
  const [payLoading, setPayLoading] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    project_id: "",
    numero_nf: "",
    data_emissao: "",
    valor_bruto: "",
    vencimento: "",
    data_prevista_pagamento: "",
    numero_pedido: "",
    numero_conformidade: "",
    observacao: "",
    antecipada: false,
    instituicao: "",
    taxa_juros_mensal: "",
  });

  const [payDraft, setPayDraft] = useState<{ data: string; valor: string }>({ data: "", valor: "" });

  const ym = useMemo(() => {
    const [y, m] = period.split("-").map(Number);
    return { year: y, month: m };
  }, [period]);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const [list, k] = await Promise.all([
        fetchReceivableInvoices({
          project_id: projectId || undefined,
          status: statusFilter || undefined,
          year: ym.year,
          month: ym.month,
        }),
        fetchReceivableKpis({
          project_id: projectId || undefined,
          year: ym.year,
          month: ym.month,
        }),
      ]);
      setRows(list);
      setKpis(k);
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Erro ao carregar.");
    } finally {
      setLoading(false);
    }
  }, [projectId, statusFilter, ym.year, ym.month]);

  useEffect(() => {
    void listProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function loadPayments(invoiceId: string) {
    setPayLoading(invoiceId);
    try {
      const list = await fetchInvoicePayments(invoiceId);
      setPayCache((c) => ({ ...c, [invoiceId]: list }));
    } finally {
      setPayLoading(null);
    }
  }

  useEffect(() => {
    if (expandedId) {
      void loadPayments(expandedId);
      const d = new Date();
      setPayDraft({ data: d.toISOString().slice(0, 10), valor: "" });
    }
  }, [expandedId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!canEditInvoices) return;
    if (!form.project_id || !form.numero_nf || !form.data_emissao || !form.vencimento) return;
    const vb = parseMoneyInput(form.valor_bruto);
    if (vb <= 0) return;
    setSaving(true);
    setError(null);
    try {
      await createReceivableInvoice({
        project_id: form.project_id,
        numero_nf: form.numero_nf.trim(),
        data_emissao: form.data_emissao,
        valor_bruto: vb,
        vencimento: form.vencimento,
        data_prevista_pagamento: form.data_prevista_pagamento || null,
        numero_pedido: form.numero_pedido || null,
        numero_conformidade: form.numero_conformidade || null,
        observacao: form.observacao || null,
        antecipada: form.antecipada,
        instituicao: form.instituicao || null,
        taxa_juros_mensal: form.taxa_juros_mensal.trim()
          ? Number.parseFloat(form.taxa_juros_mensal.replace(",", "."))
          : null,
      });
      setShowForm(false);
      setForm({
        project_id: "",
        numero_nf: "",
        data_emissao: "",
        valor_bruto: "",
        vencimento: "",
        data_prevista_pagamento: "",
        numero_pedido: "",
        numero_conformidade: "",
        observacao: "",
        antecipada: false,
        instituicao: "",
        taxa_juros_mensal: "",
      });
      await load();
    } catch (err) {
      if (isAxiosError(err)) setError(String(err.response?.data?.detail ?? err.message));
      else setError("Não foi possível cadastrar.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!canEditInvoices) return;
    if (!window.confirm("Excluir esta NF e todos os recebimentos?")) return;
    try {
      await deleteReceivableInvoice(id);
      if (expandedId === id) setExpandedId(null);
      await load();
    } catch {
      setError("Não foi possível excluir.");
    }
  }

  async function handleAddPayment(invoiceId: string) {
    if (!canEditInvoices) return;
    const valor = parseMoneyInput(payDraft.valor);
    if (!payDraft.data || valor <= 0) return;
    try {
      await addInvoicePayment(invoiceId, { data_recebimento: payDraft.data, valor });
      setPayDraft({ data: "", valor: "" });
      await loadPayments(invoiceId);
      await load();
    } catch {
      setError("Não foi possível registrar o recebimento.");
    }
  }

  async function handleDeletePayment(paymentId: string, invoiceId: string) {
    if (!canEditInvoices) return;
    if (!window.confirm("Remover este recebimento?")) return;
    try {
      await deleteInvoicePayment(paymentId);
      await loadPayments(invoiceId);
      await load();
    } catch {
      setError("Não foi possível remover o recebimento.");
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Notas fiscais (contas a receber)</h1>
        <p className="mt-1 text-sm text-slate-600">
          Controle de NFs por projeto, vencimentos, recebimentos parciais e atrasos.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {/* KPIs */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Total a receber" value={kpis ? formatBRL(kpis.total_a_receber) : "—"} />
        <Kpi label="Recebido no mês" value={kpis ? formatBRL(kpis.recebido_no_mes) : "—"} />
        <Kpi label="Em atraso" value={kpis ? formatBRL(kpis.em_atraso_valor) : "—"} accent="text-red-800" />
        <Kpi label="Total de NFs" value={kpis ? String(kpis.total_nfs) : "—"} />
      </section>

      {/* Filtros */}
      <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:flex-wrap sm:items-end">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">Período (emissão)</span>
          <input
            type="month"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="flex min-w-[200px] flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">Projeto</span>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">Todos</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-[180px] flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">Status</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as NfStatus | "")}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">Todos</option>
            <option value="PAGA">Paga</option>
            <option value="PENDENTE">Pendente</option>
            <option value="ATRASADA">Atrasada</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
        >
          Atualizar
        </button>
      </section>

      <div className="flex justify-end">
        <button
          type="button"
          disabled={!canEditInvoices}
          onClick={() => setShowForm((s) => !s)}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {showForm ? "Fechar formulário" : "+ Nova NF"}
        </button>
      </div>

      {showForm && canEditInvoices && (
        <form
          onSubmit={handleCreate}
          className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50/80 p-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <Field label="Projeto *">
            <select
              required
              value={form.project_id}
              onChange={(e) => setForm((f) => ({ ...f, project_id: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="">Selecione</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Nº NF *">
            <input
              required
              value={form.numero_nf}
              onChange={(e) => setForm((f) => ({ ...f, numero_nf: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Data emissão *">
            <input
              type="date"
              required
              value={form.data_emissao}
              onChange={(e) => setForm((f) => ({ ...f, data_emissao: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Valor bruto *">
            <input
              value={form.valor_bruto}
              onChange={(e) => setForm((f) => ({ ...f, valor_bruto: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              placeholder="0,00"
              inputMode="decimal"
            />
          </Field>
          <Field label="Vencimento *">
            <input
              type="date"
              required
              value={form.vencimento}
              onChange={(e) => setForm((f) => ({ ...f, vencimento: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Previsão pagamento">
            <input
              type="date"
              value={form.data_prevista_pagamento}
              onChange={(e) => setForm((f) => ({ ...f, data_prevista_pagamento: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Nº pedido">
            <input
              value={form.numero_pedido}
              onChange={(e) => setForm((f) => ({ ...f, numero_pedido: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Nº conformidade">
            <input
              value={form.numero_conformidade}
              onChange={(e) => setForm((f) => ({ ...f, numero_conformidade: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Observação">
            <textarea
              value={form.observacao}
              onChange={(e) => setForm((f) => ({ ...f, observacao: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              rows={2}
            />
          </Field>
          <Field label="Antecipada">
            <select
              value={form.antecipada ? "sim" : "nao"}
              onChange={(e) => setForm((f) => ({ ...f, antecipada: e.target.value === "sim" }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="nao">Não</option>
              <option value="sim">Sim</option>
            </select>
          </Field>
          <Field label="Instituição">
            <input
              value={form.instituicao}
              onChange={(e) => setForm((f) => ({ ...f, instituicao: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Taxa juros mensal (%)">
            <input
              value={form.taxa_juros_mensal}
              onChange={(e) => setForm((f) => ({ ...f, taxa_juros_mensal: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              placeholder="ex: 1,2"
            />
          </Field>
          <div className="sm:col-span-2 lg:col-span-3">
            <button
              type="submit"
              disabled={saving || !canEditInvoices}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Salvando…" : "Cadastrar NF"}
            </button>
          </div>
        </form>
      )}

      {/* Tabela */}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-3">Projeto</th>
              <th className="px-3 py-3">Nº NF</th>
              <th className="px-3 py-3">Emissão</th>
              <th className="px-3 py-3 text-right">Valor</th>
              <th className="px-3 py-3">Vencimento</th>
              <th className="px-3 py-3 text-right">Recebido</th>
              <th className="px-3 py-3 text-right">Saldo</th>
              <th className="px-3 py-3">Status</th>
              <th className="px-3 py-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-slate-500">
                  Carregando…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-slate-500">
                  Nenhuma NF no período.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <Fragment key={row.id}>
                  <tr className="hover:bg-slate-50/80">
                    <td className="max-w-[180px] truncate px-3 py-2.5 text-slate-900">{row.project_name ?? "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-medium">{row.numero_nf}</td>
                    <td className="whitespace-nowrap px-3 py-2.5">{formatDateBr(row.data_emissao)}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{formatBRL(row.valor_bruto)}</td>
                    <td className="whitespace-nowrap px-3 py-2.5">{formatDateBr(row.vencimento)}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{formatBRL(row.total_recebido)}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{formatBRL(row.saldo)}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${statusBadge(row.status)}`}
                      >
                        {row.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => setExpandedId((id) => (id === row.id ? null : row.id))}
                        className="mr-2 text-indigo-600 hover:underline"
                      >
                        {expandedId === row.id ? "Ocultar" : "Detalhes"}
                      </button>
                      <button
                        type="button"
                        disabled={!canEditInvoices}
                        onClick={() => void handleDelete(row.id)}
                        className="text-red-700 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Excluir
                      </button>
                    </td>
                  </tr>
                  {expandedId === row.id && (
                    <tr className="bg-slate-50/90">
                      <td colSpan={9} className="px-4 py-4">
                        <div className="space-y-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Recebimentos</p>
                          {payLoading === row.id ? (
                            <p className="text-sm text-slate-500">Carregando recebimentos…</p>
                          ) : (
                            <div className="overflow-x-auto rounded border border-slate-200 bg-white">
                              <table className="min-w-[320px] text-sm">
                                <thead>
                                  <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-600">
                                    <th className="px-3 py-2">Data</th>
                                    <th className="px-3 py-2 text-right">Valor</th>
                                    <th className="px-3 py-2 text-right">Ações</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(payCache[row.id] ?? []).length === 0 ? (
                                    <tr>
                                      <td colSpan={3} className="px-3 py-3 text-slate-500">
                                        Nenhum recebimento registrado.
                                      </td>
                                    </tr>
                                  ) : (
                                    (payCache[row.id] ?? []).map((p) => (
                                      <tr key={p.id} className="border-t border-slate-100">
                                        <td className="px-3 py-2">{formatDateBr(p.data_recebimento)}</td>
                                        <td className="px-3 py-2 text-right tabular-nums">{formatBRL(p.valor)}</td>
                                        <td className="px-3 py-2 text-right">
                                          <button
                                            type="button"
                                            disabled={!canEditInvoices}
                                            onClick={() => void handleDeletePayment(p.id, row.id)}
                                            className="text-red-700 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                                          >
                                            Remover
                                          </button>
                                        </td>
                                      </tr>
                                    ))
                                  )}
                                </tbody>
                              </table>
                            </div>
                          )}
                          <div className="flex flex-col gap-2 rounded border border-dashed border-slate-300 bg-white p-3 sm:flex-row sm:items-end">
                            <label className="flex flex-col gap-1 text-xs">
                              <span className="font-medium text-slate-700">Data</span>
                              <input
                                type="date"
                                value={payDraft.data}
                                onChange={(e) => setPayDraft((d) => ({ ...d, data: e.target.value }))}
                                className="rounded border border-slate-300 px-2 py-1.5"
                              />
                            </label>
                            <label className="flex flex-col gap-1 text-xs">
                              <span className="font-medium text-slate-700">Valor</span>
                              <input
                                value={payDraft.valor}
                                onChange={(e) => setPayDraft((d) => ({ ...d, valor: e.target.value }))}
                                className="rounded border border-slate-300 px-2 py-1.5"
                                placeholder="0,00"
                              />
                            </label>
                            <button
                              type="button"
                              disabled={!canEditInvoices}
                              onClick={() => void handleAddPayment(row.id)}
                              className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              + Adicionar recebimento
                            </button>
                          </div>
                          {(row.observacao || row.numero_pedido || row.antecipada) && (
                            <div className="text-xs text-slate-600">
                              {row.numero_pedido && <p>Pedido: {row.numero_pedido}</p>}
                              {row.observacao && <p className="mt-1">Obs.: {row.observacao}</p>}
                              {row.antecipada && <p className="mt-1">Antecipada {row.instituicao ? `— ${row.instituicao}` : ""}</p>}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}
