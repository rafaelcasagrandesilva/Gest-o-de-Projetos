import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  createReceivableInvoice,
  deleteReceivableInvoice,
  deleteInvoicePdf,
  downloadInvoicePdfBlob,
  fetchReceivableInvoices,
  fetchReceivableKpis,
  openPdfBlobInNewTab,
  updateReceivableInvoice,
  uploadInvoicePdf,
  type InvoiceStatus,
  type PeriodField,
  type ReceivableInvoice,
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

function addCalendarDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  if (!y || !m || !d) return "";
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + days);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

function todayIsoLocal(): string {
  const t = new Date();
  const y = t.getFullYear();
  const m = String(t.getMonth() + 1).padStart(2, "0");
  const d = String(t.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function isOverdue(row: ReceivableInvoice): boolean {
  if (row.status === "FINALIZADA" || row.status === "CANCELADA") return false;
  const due = row.due_date.slice(0, 10);
  return due < todayIsoLocal();
}

function statusBadgeClass(s: InvoiceStatus): string {
  if (s === "FINALIZADA") return "bg-emerald-100 text-emerald-900 ring-emerald-200";
  if (s === "CANCELADA") return "bg-slate-200 text-slate-700 ring-slate-300";
  if (s === "ANTECIPADA") return "bg-amber-100 text-amber-900 ring-amber-200";
  return "bg-slate-100 text-slate-800 ring-slate-200";
}

const STATUS_LABELS: Record<InvoiceStatus, string> = {
  EMITIDA: "Emitida",
  ANTECIPADA: "Antecipada",
  FINALIZADA: "Finalizada",
  CANCELADA: "Cancelada",
};

function monthToYm(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

type DueChoice = 30 | 60 | 90;

type EditDraft = {
  number: string;
  issue_date: string;
  due_days: DueChoice;
  gross_amount: string;
  net_amount: string;
  client_name: string;
  notes: string;
  received_amount: string;
  received_date: string;
  is_anticipated: boolean;
  institution: string;
};

function emptyEditDraft(): EditDraft {
  return {
    number: "",
    issue_date: "",
    due_days: 30,
    gross_amount: "",
    net_amount: "",
    client_name: "",
    notes: "",
    received_amount: "",
    received_date: "",
    is_anticipated: false,
    institution: "",
  };
}

export function Invoices() {
  const canEditInvoices = usePermission("invoices.edit");
  const [projects, setProjects] = useState<Project[]>([]);
  const [period, setPeriod] = useState(() => monthToYm(new Date()));
  const [periodField, setPeriodField] = useState<PeriodField>("issue");
  const [projectId, setProjectId] = useState("");
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | "">("");
  const [clienteFilter, setClienteFilter] = useState("");

  const [rows, setRows] = useState<ReceivableInvoice[]>([]);
  const [kpis, setKpis] = useState<Awaited<ReturnType<typeof fetchReceivableKpis>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft>(emptyEditDraft);
  const [pdfUploading, setPdfUploading] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    project_id: "",
    number: "",
    issue_date: "",
    due_days: 30 as DueChoice,
    gross_amount: "",
    net_amount: "",
    client_name: "",
    notes: "",
  });

  const ym = useMemo(() => {
    const [y, m] = period.split("-").map(Number);
    return { year: y, month: m };
  }, [period]);

  const previewDue = useMemo(
    () => (form.issue_date ? addCalendarDays(form.issue_date, form.due_days) : ""),
    [form.issue_date, form.due_days],
  );

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const params: Parameters<typeof fetchReceivableInvoices>[0] = {
        project_id: projectId || undefined,
        year: ym.year,
        month: ym.month,
        period_field: periodField,
      };
      if (statusFilter) params.status = statusFilter;
      if (clienteFilter.trim()) params.client = clienteFilter.trim();

      const [list, k] = await Promise.all([
        fetchReceivableInvoices(params),
        fetchReceivableKpis({
          project_id: projectId || undefined,
          year: ym.year,
          month: ym.month,
          period_field: periodField,
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
  }, [projectId, statusFilter, clienteFilter, ym.year, ym.month, periodField]);

  useEffect(() => {
    void listProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!expandedId) {
      setEditDraft(emptyEditDraft());
      return;
    }
    const row = rows.find((r) => r.id === expandedId);
    if (!row) return;
    setEditDraft({
      number: row.number,
      issue_date: row.issue_date.slice(0, 10),
      due_days: row.due_days as DueChoice,
      gross_amount: row.gross_amount.toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      net_amount: row.net_amount.toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      client_name: row.client_name ?? "",
      notes: row.notes ?? "",
      received_amount: row.received_amount.toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      received_date: row.received_date ? row.received_date.slice(0, 10) : "",
      is_anticipated: row.is_anticipated,
      institution: row.institution ?? "",
    });
  }, [expandedId, rows]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!canEditInvoices) return;
    if (!form.project_id || !form.number.trim() || !form.issue_date) return;
    const gross = parseMoneyInput(form.gross_amount);
    if (gross <= 0) return;
    const netRaw = form.net_amount.trim();
    const net = netRaw ? parseMoneyInput(netRaw) : gross;
    if (net <= 0) return;
    setSaving(true);
    setError(null);
    try {
      await createReceivableInvoice({
        project_id: form.project_id,
        number: form.number.trim(),
        issue_date: form.issue_date,
        due_days: form.due_days,
        gross_amount: gross,
        net_amount: net,
        client_name: form.client_name.trim() || null,
        notes: form.notes.trim() || null,
      });
      setShowForm(false);
      setForm({
        project_id: "",
        number: "",
        issue_date: "",
        due_days: 30,
        gross_amount: "",
        net_amount: "",
        client_name: "",
        notes: "",
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
    if (!window.confirm("Excluir esta nota fiscal?")) return;
    try {
      await deleteReceivableInvoice(id);
      if (expandedId === id) setExpandedId(null);
      await load();
    } catch {
      setError("Não foi possível excluir.");
    }
  }

  async function saveExpanded(invoiceId: string, row: ReceivableInvoice) {
    if (!canEditInvoices) return;
    if (row.status === "CANCELADA") {
      try {
        await updateReceivableInvoice(invoiceId, { notes: editDraft.notes.trim() || null });
        await load();
      } catch (e) {
        if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
        else setError("Não foi possível salvar.");
      }
      return;
    }

    const gross = parseMoneyInput(editDraft.gross_amount);
    const net = parseMoneyInput(editDraft.net_amount);
    const recv = parseMoneyInput(editDraft.received_amount);
    if (gross <= 0 || net <= 0) {
      setError("Valores bruto e líquido devem ser positivos.");
      return;
    }
    const tol = 0.01;
    if (recv > tol && Math.abs(recv - net) > tol) {
      setError("Recebimento deve ser integral: informe 0 ou o valor líquido completo.");
      return;
    }
    if (recv > 0 && !editDraft.received_date) {
      setError("Informe a data do recebimento.");
      return;
    }

    setError(null);
    try {
      await updateReceivableInvoice(invoiceId, {
        number: editDraft.number.trim(),
        issue_date: editDraft.issue_date,
        due_days: editDraft.due_days,
        gross_amount: gross,
        net_amount: net,
        client_name: editDraft.client_name.trim() || null,
        notes: editDraft.notes.trim() || null,
        is_anticipated: editDraft.is_anticipated,
        institution: editDraft.institution.trim() || null,
        received_amount: recv,
        received_date: recv > 0 ? editDraft.received_date : null,
      });
      await load();
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível salvar.");
    }
  }

  async function handleCancelInvoice(invoiceId: string) {
    if (!canEditInvoices) return;
    if (!window.confirm("Cancelar esta NF? O status passará a CANCELADA.")) return;
    setError(null);
    try {
      await updateReceivableInvoice(invoiceId, { status: "CANCELADA" });
      await load();
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível cancelar.");
    }
  }

  async function handlePdfUpload(invoiceId: string, file: File | null) {
    if (!file || !canEditInvoices) return;
    if (file.type !== "application/pdf") {
      setError("Selecione um arquivo PDF.");
      return;
    }
    setPdfUploading(invoiceId);
    setError(null);
    try {
      await uploadInvoicePdf(invoiceId, file);
      await load();
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Falha no upload do PDF.");
    } finally {
      setPdfUploading(null);
    }
  }

  async function handlePdfView(invoiceId: string) {
    setError(null);
    try {
      const blob = await downloadInvoicePdfBlob(invoiceId);
      openPdfBlobInNewTab(blob);
    } catch {
      setError("Não foi possível abrir o PDF.");
    }
  }

  async function handlePdfDownload(invoiceId: string, numeroNf: string) {
    setError(null);
    try {
      const blob = await downloadInvoicePdfBlob(invoiceId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `NF-${numeroNf.replace(/\//g, "-")}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Não foi possível baixar o PDF.");
    }
  }

  async function handlePdfDelete(invoiceId: string) {
    if (!canEditInvoices) return;
    if (!window.confirm("Remover o PDF desta NF?")) return;
    try {
      await deleteInvoicePdf(invoiceId);
      await load();
    } catch (e) {
      if (isAxiosError(e)) setError(String(e.response?.data?.detail ?? e.message));
      else setError("Não foi possível remover o PDF.");
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Notas fiscais (contas a receber)</h1>
        <p className="mt-1 text-sm text-slate-600">
          Cadastro enxuto, vencimento por prazo (30/60/90), recebimento integral e antecipação quando aplicável.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Total a receber" value={kpis ? formatBRL(kpis.total_a_receber) : "—"} />
        <Kpi label="Recebido no mês" value={kpis ? formatBRL(kpis.recebido_no_mes) : "—"} />
        <Kpi label="Em atraso" value={kpis ? formatBRL(kpis.em_atraso_valor) : "—"} accent="text-red-800" />
        <Kpi label="Total de NFs" value={kpis ? String(kpis.total_nfs) : "—"} />
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Período</span>
            <input
              type="month"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Campo do período</span>
            <select
              value={periodField}
              onChange={(e) => setPeriodField(e.target.value as PeriodField)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="issue">Data de emissão</option>
              <option value="due">Data de vencimento</option>
            </select>
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
          <label className="flex min-w-[160px] flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Status</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as InvoiceStatus | "")}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="">Todos</option>
              {(Object.keys(STATUS_LABELS) as InvoiceStatus[]).map((k) => (
                <option key={k} value={k}>
                  {STATUS_LABELS[k]}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Cliente</span>
            <input
              value={clienteFilter}
              onChange={(e) => setClienteFilter(e.target.value)}
              placeholder="Buscar…"
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="w-fit rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
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
              value={form.number}
              onChange={(e) => setForm((f) => ({ ...f, number: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Data emissão *">
            <input
              type="date"
              required
              value={form.issue_date}
              onChange={(e) => setForm((f) => ({ ...f, issue_date: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Prazo (dias) *">
            <select
              value={form.due_days}
              onChange={(e) => setForm((f) => ({ ...f, due_days: Number(e.target.value) as DueChoice }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value={30}>30 dias</option>
              <option value={60}>60 dias</option>
              <option value={90}>90 dias</option>
            </select>
          </Field>
          <Field label="Vencimento (calculado)">
            <input
              readOnly
              value={previewDue ? formatDateBr(previewDue) : "—"}
              className="w-full rounded border border-slate-200 bg-slate-100 px-2 py-1.5 text-sm text-slate-700"
            />
          </Field>
          <Field label="Valor bruto *">
            <input
              value={form.gross_amount}
              onChange={(e) => setForm((f) => ({ ...f, gross_amount: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              placeholder="0,00"
              inputMode="decimal"
            />
          </Field>
          <Field label="Valor líquido (opcional — padrão = bruto)">
            <input
              value={form.net_amount}
              onChange={(e) => setForm((f) => ({ ...f, net_amount: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              placeholder="igual ao bruto se vazio"
              inputMode="decimal"
            />
          </Field>
          <Field label="Cliente">
            <input
              value={form.client_name}
              onChange={(e) => setForm((f) => ({ ...f, client_name: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Observações">
            <textarea
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              rows={2}
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

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1000px] w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-2 py-3">Projeto</th>
              <th className="px-2 py-3">Cliente</th>
              <th className="px-2 py-3">Nº NF</th>
              <th className="px-2 py-3">Emissão</th>
              <th className="px-2 py-3">Prazo</th>
              <th className="px-2 py-3">Venc.</th>
              <th className="px-2 py-3 text-right">Bruto</th>
              <th className="px-2 py-3 text-right">Líquido</th>
              <th className="px-2 py-3 text-right">Recebido</th>
              <th className="px-2 py-3">Status</th>
              <th className="px-2 py-3">PDF</th>
              <th className="px-2 py-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && rows.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-3 py-8 text-center text-slate-500">
                  Carregando…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-3 py-8 text-center text-slate-500">
                  Nenhuma NF no período.
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const overdue = isOverdue(row);
                const rowClass =
                  row.status === "CANCELADA"
                    ? "opacity-60"
                    : row.status === "FINALIZADA"
                      ? "bg-emerald-50/40"
                      : overdue
                        ? "bg-red-50/50"
                        : "";
                return (
                  <Fragment key={row.id}>
                    <tr className={`hover:bg-slate-50/80 ${rowClass}`}>
                      <td className="max-w-[120px] truncate px-2 py-2 text-slate-900">{row.project_name ?? "—"}</td>
                      <td className="max-w-[160px] truncate px-2 py-2 text-slate-700">{row.client_name || "—"}</td>
                      <td className="whitespace-nowrap px-2 py-2 font-medium">{row.number}</td>
                      <td className="whitespace-nowrap px-2 py-2">{formatDateBr(row.issue_date)}</td>
                      <td className="whitespace-nowrap px-2 py-2">{row.due_days} d</td>
                      <td className="whitespace-nowrap px-2 py-2">{formatDateBr(row.due_date)}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">{formatBRL(row.gross_amount)}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">{formatBRL(row.net_amount)}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">
                        {formatBRL(row.received_amount)}
                      </td>
                      <td className="px-2 py-2">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${statusBadgeClass(row.status)}`}
                        >
                          {STATUS_LABELS[row.status]}
                        </span>
                        {overdue && row.status !== "CANCELADA" && (
                          <span className="ml-1 text-[10px] font-semibold text-red-700">Atraso</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-2 py-2">
                        {row.has_pdf ? (
                          <div className="flex flex-wrap gap-1">
                            <button
                              type="button"
                              className="text-xs text-indigo-600 hover:underline"
                              onClick={() => void handlePdfView(row.id)}
                            >
                              Ver
                            </button>
                            <button
                              type="button"
                              className="text-xs text-slate-600 hover:underline"
                              onClick={() => void handlePdfDownload(row.id, row.number)}
                            >
                              Baixar
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-2 py-2 text-right">
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
                        <td colSpan={12} className="px-4 py-4">
                          <div className="grid gap-6 lg:grid-cols-2">
                            <div className="space-y-4">
                              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Dados da NF</p>
                              <div className="grid gap-3 sm:grid-cols-2">
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Nº NF</span>
                                  <input
                                    value={editDraft.number}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, number: e.target.value }))}
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  />
                                </label>
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Emissão</span>
                                  <input
                                    type="date"
                                    value={editDraft.issue_date}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, issue_date: e.target.value }))}
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  />
                                </label>
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Prazo</span>
                                  <select
                                    value={editDraft.due_days}
                                    onChange={(e) =>
                                      setEditDraft((d) => ({ ...d, due_days: Number(e.target.value) as DueChoice }))
                                    }
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  >
                                    <option value={30}>30 dias</option>
                                    <option value={60}>60 dias</option>
                                    <option value={90}>90 dias</option>
                                  </select>
                                </label>
                                <div className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Vencimento (calculado)</span>
                                  <span className="rounded border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-800">
                                    {editDraft.issue_date
                                      ? formatDateBr(addCalendarDays(editDraft.issue_date, editDraft.due_days))
                                      : "—"}
                                  </span>
                                </div>
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Valor bruto</span>
                                  <input
                                    value={editDraft.gross_amount}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, gross_amount: e.target.value }))}
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                    inputMode="decimal"
                                  />
                                </label>
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Valor líquido</span>
                                  <input
                                    value={editDraft.net_amount}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, net_amount: e.target.value }))}
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                    inputMode="decimal"
                                  />
                                </label>
                                <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                                  <span className="font-medium text-slate-700">Cliente</span>
                                  <input
                                    value={editDraft.client_name}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, client_name: e.target.value }))}
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  />
                                </label>
                                <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                                  <span className="font-medium text-slate-700">Observações</span>
                                  <textarea
                                    value={editDraft.notes}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, notes: e.target.value }))}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                    rows={2}
                                  />
                                </label>
                              </div>

                              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Recebimento</p>
                              <p className="text-xs text-slate-500">
                                Informe 0 ou o valor líquido integral (pagamento parcial não é permitido).
                              </p>
                              <div className="grid gap-3 sm:grid-cols-2">
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Valor recebido</span>
                                  <input
                                    value={editDraft.received_amount}
                                    onChange={(e) =>
                                      setEditDraft((d) => ({ ...d, received_amount: e.target.value }))
                                    }
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                    inputMode="decimal"
                                  />
                                </label>
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Data recebimento</span>
                                  <input
                                    type="date"
                                    value={editDraft.received_date}
                                    onChange={(e) =>
                                      setEditDraft((d) => ({ ...d, received_date: e.target.value }))
                                    }
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  />
                                </label>
                              </div>

                              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                                Antecipação
                              </p>
                              <div className="grid gap-3 sm:grid-cols-2">
                                <label className="flex items-center gap-2 text-xs sm:col-span-2">
                                  <input
                                    type="checkbox"
                                    checked={editDraft.is_anticipated}
                                    onChange={(e) =>
                                      setEditDraft((d) => ({ ...d, is_anticipated: e.target.checked }))
                                    }
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="h-4 w-4 rounded border-slate-300"
                                  />
                                  <span>Nota antecipada</span>
                                </label>
                                {editDraft.is_anticipated && (
                                  <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                                    <span className="font-medium text-slate-700">Instituição</span>
                                    <input
                                      value={editDraft.institution}
                                      onChange={(e) =>
                                        setEditDraft((d) => ({ ...d, institution: e.target.value }))
                                      }
                                      disabled={!canEditInvoices || row.status === "CANCELADA"}
                                      className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                    />
                                  </label>
                                )}
                              </div>

                              <div className="rounded border border-slate-200 bg-white p-3 text-xs text-slate-700">
                                <p className="font-semibold text-slate-800">Indicadores</p>
                                <p className="mt-1">
                                  Taxa implícita mensal (bruto → líquido):{" "}
                                  <span className="font-mono tabular-nums">
                                    {row.implied_monthly_rate_percent != null
                                      ? `${row.implied_monthly_rate_percent.toFixed(4)} %`
                                      : "—"}
                                  </span>
                                </p>
                                <p className="mt-1">
                                  Juros / desconto (antecipação):{" "}
                                  <span className="font-mono tabular-nums">{formatBRL(row.interest_amount)}</span>
                                </p>
                              </div>

                              <div className="flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  disabled={!canEditInvoices || row.status === "CANCELADA"}
                                  onClick={() => void saveExpanded(row.id, row)}
                                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  Salvar alterações
                                </button>
                                {row.status !== "CANCELADA" && (
                                  <button
                                    type="button"
                                    disabled={!canEditInvoices}
                                    onClick={() => void handleCancelInvoice(row.id)}
                                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-50"
                                  >
                                    Cancelar NF
                                  </button>
                                )}
                              </div>
                            </div>

                            <div className="space-y-3 text-sm">
                              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">PDF</p>
                              <div className="rounded border border-slate-200 bg-white p-3">
                                <input
                                  type="file"
                                  accept="application/pdf"
                                  disabled={!canEditInvoices || pdfUploading === row.id || row.status === "CANCELADA"}
                                  onChange={(e) => void handlePdfUpload(row.id, e.target.files?.[0] ?? null)}
                                  className="text-xs"
                                />
                                {pdfUploading === row.id && <p className="mt-1 text-xs text-slate-500">Enviando…</p>}
                                {row.has_pdf && canEditInvoices && row.status !== "CANCELADA" && (
                                  <button
                                    type="button"
                                    className="mt-2 text-xs text-red-600 hover:underline"
                                    onClick={() => void handlePdfDelete(row.id)}
                                  >
                                    Remover PDF
                                  </button>
                                )}
                              </div>

                              {row.activity_log && (
                                <div>
                                  <p className="mb-1 text-xs font-semibold text-slate-600">Histórico</p>
                                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-slate-200 bg-white p-2 text-[11px] text-slate-700">
                                    {row.activity_log}
                                  </pre>
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
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
