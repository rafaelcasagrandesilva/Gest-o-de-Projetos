import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  createReceivableInvoice,
  deleteReceivableInvoice,
  deleteInvoicePdf,
  downloadInvoicePdfBlob,
  fetchReceivableInvoices,
  fetchReceivableKpis,
  openPdfBlobInNewTab,
  reactivateReceivableInvoice,
  updateReceivableInvoice,
  uploadInvoicePdf,
  type InvoiceStatus,
  type OfficialFilter,
  type PeriodField,
  type ReceivableInvoice,
} from "@/services/receivables";
import { usePermission } from "@/hooks/usePermission";
import { listProjects, type Project } from "@/services/projects";
import { isAxiosError } from "axios";
import { PeriodFilter } from "@/components/PeriodFilter";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import { AdvanceBatchModal } from "@/components/AdvanceBatchModal";
import { defaultInvoiceSort, INVOICE_SORT_COLUMNS } from "@/tableSort/invoices";
import {
  formatCurrencyInputFromApi,
  formatCurrencyOrDash,
  normalizeCurrencyForApi,
} from "@/utils/currency";

function formatAxiosDetail(e: unknown): string {
  if (!isAxiosError(e)) return "Erro inesperado.";
  const detail = e.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail != null) {
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return e.message || "Falha na requisição.";
}

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function parseMoneyInput(raw: string): number {
  return normalizeCurrencyForApi(raw);
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
  if (row.status === "RECEBIDA" || row.status === "CANCELADA") return false;
  const due = row.due_date.slice(0, 10);
  return due < todayIsoLocal();
}

function statusBadgeClass(s: InvoiceStatus): string {
  if (s === "RECEBIDA") return "bg-emerald-100 text-emerald-900 ring-emerald-200";
  if (s === "CANCELADA") return "bg-slate-200 text-slate-700 ring-slate-300";
  if (s === "ANTECIPADA") return "bg-amber-100 text-amber-900 ring-amber-200";
  return "bg-slate-100 text-slate-800 ring-slate-200";
}

const STATUS_LABELS: Record<InvoiceStatus, string> = {
  EMITIDA: "Emitida",
  ANTECIPADA: "Antecipada",
  RECEBIDA: "Recebida",
  CANCELADA: "Cancelada",
};

/**
 * Rótulo do status exibido na coluna STATUS. Para NFs ANTECIPADAS que participaram de
 * mais de uma operação válida, mostra o contador automático "Antecipada Nx" (regra 7/8).
 */
function statusLabel(row: ReceivableInvoice): string {
  const base = STATUS_LABELS[row.status];
  const count = row.anticipation_count ?? 0;
  if (row.status === "ANTECIPADA" && count > 1) {
    return `Antecipada ${count}x`;
  }
  return base;
}

/** Badge discreto de classificação Oficial / Não Oficial. */
function officialBadgeClass(isOfficial: boolean): string {
  return isOfficial
    ? "bg-slate-100 text-slate-700 ring-slate-200"
    : "bg-amber-50 text-amber-800 ring-amber-200";
}

/** Rótulo do status do lote de antecipação (módulo Antecipações). */
function batchStatusLabel(s: string): string {
  if (s === "DRAFT") return "Rascunho";
  if (s === "OPEN") return "Em aberto";
  if (s === "SETTLED") return "Liquidado";
  if (s === "CANCELLED") return "Cancelado";
  return s;
}

const MESES_BR = [
  "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
  "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
];

/** Competência (primeiro-de-mês ISO) → rótulo MÊS/AAAA para exibição. */
function formatCompetenceBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m] = iso.slice(0, 7).split("-");
  const nome = MESES_BR[Number(m) - 1];
  if (!nome) return `${m}/${y}`;
  return `${nome}/${y}`;
}

function monthToYm(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

type DueChoice = 30 | 60 | 90;

type EditDraft = {
  number: string;
  issue_date: string;
  due_days: DueChoice;
  competence: string;
  gross_amount: string;
  net_amount: string;
  client_name: string;
  notes: string;
  is_official: boolean;
  received_date: string;
  received: boolean;
  include_in_dashboard: boolean;
};

function emptyEditDraft(): EditDraft {
  return {
    number: "",
    issue_date: "",
    due_days: 30,
    competence: "",
    gross_amount: "",
    net_amount: "",
    client_name: "",
    notes: "",
    is_official: true,
    received_date: "",
    received: false,
    include_in_dashboard: true,
  };
}

export function Invoices() {
  const canEditInvoices = usePermission("invoices.update");
  const canReactivateInvoices = usePermission("invoices.reactivate");
  const [reactivatingId, setReactivatingId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [periodMode, setPeriodMode] = useState<"MONTH" | "ALL">("MONTH");
  const [period, setPeriod] = useState(() => monthToYm(new Date()));
  const [periodField, setPeriodField] = useState<PeriodField>("issue");
  const [projectId, setProjectId] = useState("");
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | "">("");
  const [officialFilter, setOfficialFilter] = useState<OfficialFilter>("all");
  const [clienteFilter, setClienteFilter] = useState("");

  const [rows, setRows] = useState<ReceivableInvoice[]>([]);
  const [kpis, setKpis] = useState<Awaited<ReturnType<typeof fetchReceivableKpis>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft>(emptyEditDraft);
  const [pdfUploading, setPdfUploading] = useState<string | null>(null);

  // Filtro de competência — independente do filtro de período (emissão/vencimento).
  const [competenceMode, setCompetenceMode] = useState<"MONTH" | "ALL">("ALL");
  const [competencePeriod, setCompetencePeriod] = useState(() => monthToYm(new Date()));

  const [showForm, setShowForm] = useState(false);
  const [batchModalOpen, setBatchModalOpen] = useState(false);
  const [viewBatchId, setViewBatchId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    project_id: "",
    number: "",
    issue_date: "",
    due_days: 30 as DueChoice,
    competence: "",
    gross_amount: "",
    net_amount: "",
    client_name: "",
    notes: "",
    is_official: true,
    include_in_dashboard: true,
  });

  const { sortedRows, headerSort } = useTableSort(rows, INVOICE_SORT_COLUMNS, {
    defaultCompare: defaultInvoiceSort,
  });

  const ym = useMemo(() => {
    const [y, m] = period.split("-").map(Number);
    return { year: y, month: m };
  }, [period]);

  const competenceYm = useMemo(() => {
    const [y, m] = competencePeriod.split("-").map(Number);
    return { year: y, month: m };
  }, [competencePeriod]);

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
        period_field: periodField,
        official: officialFilter,
      };
      if (periodMode === "MONTH") {
        params.year = ym.year;
        params.month = ym.month;
      }
      if (competenceMode === "MONTH") {
        params.competence_year = competenceYm.year;
        params.competence_month = competenceYm.month;
      }
      if (statusFilter) params.status = statusFilter;
      if (clienteFilter.trim()) params.client = clienteFilter.trim();

      // Cards reutilizam exatamente os mesmos filtros da listagem.
      const [list, k] = await Promise.all([
        fetchReceivableInvoices(params),
        fetchReceivableKpis(params),
      ]);
      setRows(list);
      setKpis(k);
    } catch (e) {
      setError(formatAxiosDetail(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, statusFilter, officialFilter, clienteFilter, ym.year, ym.month, periodField, periodMode, competenceMode, competenceYm.year, competenceYm.month]);

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
      competence: row.competence_month ? row.competence_month.slice(0, 7) : "",
      gross_amount: formatCurrencyInputFromApi(row.gross_amount),
      net_amount: formatCurrencyInputFromApi(row.net_amount),
      client_name: row.client_name ?? "",
      notes: row.notes ?? "",
      is_official: row.is_official !== false,
      received_date: row.received_date ? row.received_date.slice(0, 10) : "",
      received: row.status === "RECEBIDA",
      include_in_dashboard: row.include_in_dashboard !== false,
    });
  }, [expandedId, rows]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!canEditInvoices) return;
    if (!form.project_id || !form.number.trim() || !form.issue_date) return;
    if (!form.competence) {
      setError("Informe a competência (mês/ano do serviço).");
      return;
    }
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
        competence_month: `${form.competence}-01`,
        gross_amount: gross,
        net_amount: net,
        client_name: form.client_name.trim() || null,
        notes: form.notes.trim() || null,
        is_official: form.is_official,
        include_in_dashboard: form.include_in_dashboard,
      });
      setShowForm(false);
      setForm({
        project_id: "",
        number: "",
        issue_date: "",
        due_days: 30,
        competence: "",
        gross_amount: "",
        net_amount: "",
        client_name: "",
        notes: "",
        is_official: true,
        include_in_dashboard: true,
      });
      await load();
    } catch (err) {
      setError(formatAxiosDetail(err));
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
        setError(formatAxiosDetail(e));
      }
      return;
    }

    const gross = parseMoneyInput(editDraft.gross_amount);
    const net = parseMoneyInput(editDraft.net_amount);
    if (gross <= 0 || net <= 0) {
      setError("Valores bruto e líquido devem ser positivos.");
      return;
    }
    if (editDraft.received && !editDraft.received_date) {
      setError("Informe a data do recebimento.");
      return;
    }

    setError(null);
    try {
      await updateReceivableInvoice(invoiceId, {
        number: editDraft.number.trim(),
        issue_date: editDraft.issue_date,
        due_days: editDraft.due_days,
        competence_month: editDraft.competence ? `${editDraft.competence}-01` : null,
        gross_amount: gross,
        net_amount: net,
        client_name: editDraft.client_name.trim() || null,
        notes: editDraft.notes.trim() || null,
        is_official: editDraft.is_official,
        received_amount: editDraft.received ? net : 0,
        received_date: editDraft.received ? editDraft.received_date : null,
        include_in_dashboard: editDraft.include_in_dashboard,
      });
      await load();
    } catch (e) {
      setError(formatAxiosDetail(e));
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
      setError(formatAxiosDetail(e));
    }
  }

  async function handleReactivateInvoice(invoiceId: string, nfNumber: string) {
    if (!canReactivateInvoices) return;
    if (
      !window.confirm(
        `Reativar a NF ${nfNumber}? O status voltará de CANCELADA para EMITIDA (ou derivado dos recebimentos).`,
      )
    ) {
      return;
    }
    setReactivatingId(invoiceId);
    setError(null);
    try {
      await reactivateReceivableInvoice(invoiceId);
      await load();
    } catch (e) {
      setError(formatAxiosDetail(e));
    } finally {
      setReactivatingId(null);
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
      setError(formatAxiosDetail(e));
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
      setError(formatAxiosDetail(e));
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Notas fiscais (contas a receber)</h1>
        <p className="mt-1 text-sm text-slate-600">
          Cadastro enxuto, vencimento por prazo (30/60/90), recebimento integral e antecipação quando aplicável.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <Kpi label="Total Líquido a receber" value={kpis ? formatCurrencyOrDash(kpis.total_a_receber) : "—"} />
        <Kpi label="Total Bruto a receber" value={kpis ? formatCurrencyOrDash(kpis.total_bruto_a_receber) : "—"} />
        <Kpi
          label={periodMode === "ALL" ? "Recebido (total)" : "Recebido no mês"}
          value={kpis ? formatCurrencyOrDash(kpis.recebido_no_mes) : "—"}
        />
        <Kpi label="Em atraso" value={kpis ? formatCurrencyOrDash(kpis.em_atraso_valor) : "—"} accent="text-red-800" />
        <Kpi label="Total de NFs" value={kpis ? String(kpis.total_nfs) : "—"} />
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <PeriodFilter mode={periodMode} value={period} onModeChange={setPeriodMode} onChange={setPeriod} />
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Campo do período</span>
            <select
              value={periodField}
              onChange={(e) => setPeriodField(e.target.value as PeriodField)}
              disabled={periodMode === "ALL"}
              className="rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-60"
            >
              <option value="issue">Data de emissão</option>
              <option value="due">Data de vencimento</option>
            </select>
          </label>
          <PeriodFilter
            label="Competência"
            monthOptionLabel="Competência"
            mode={competenceMode}
            value={competencePeriod}
            onModeChange={setCompetenceMode}
            onChange={setCompetencePeriod}
          />
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
          <label className="flex min-w-[160px] flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Tipo da NF</span>
            <select
              value={officialFilter}
              onChange={(e) => setOfficialFilter(e.target.value as OfficialFilter)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="all">Todos</option>
              <option value="official">Oficiais</option>
              <option value="unofficial">Não Oficiais</option>
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

      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          disabled={!canEditInvoices}
          onClick={() => {
            setViewBatchId(null);
            setBatchModalOpen(true);
          }}
          className="rounded-lg border border-indigo-200 bg-white px-4 py-2 text-sm font-medium text-indigo-800 shadow-sm hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Nova antecipação
        </button>
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
          <Field label="Competência *">
            <input
              type="month"
              required
              value={form.competence}
              onChange={(e) => setForm((f) => ({ ...f, competence: e.target.value }))}
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
          <Field label="Tipo da NF">
            <label className="flex items-center gap-2 py-1.5 text-sm">
              <input
                type="checkbox"
                checked={!form.is_official}
                onChange={(e) => setForm((f) => ({ ...f, is_official: !e.target.checked }))}
                className="h-4 w-4 rounded border-slate-300"
              />
              <span className="text-slate-700">NF Não Oficial</span>
            </label>
          </Field>
          <Field label="Observações">
            <textarea
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              rows={2}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm sm:col-span-2 lg:col-span-3">
            <input
              type="checkbox"
              checked={form.include_in_dashboard}
              onChange={(e) => setForm((f) => ({ ...f, include_in_dashboard: e.target.checked }))}
              className="h-4 w-4 rounded border-slate-300"
            />
            <span className="text-slate-700">Considerar no Dashboard Financeiro</span>
          </label>
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
          <thead className="bg-slate-50 text-left text-xs font-semibold tracking-wide text-slate-600">
            <tr>
              <SortableTh
                label="Projeto"
                column="project"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
              />
              <th className="px-2 py-3">Cliente</th>
              <SortableTh
                label="Nº NF"
                column="number"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
              />
              <SortableTh
                label="Emissão"
                column="issue_date"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
              />
              <th className="px-2 py-3">Competência</th>
              <SortableTh
                label="Prazo"
                column="due_days"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
              />
              <SortableTh
                label="Venc."
                column="due_date"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
              />
              <SortableTh
                label="Bruto"
                column="gross_amount"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
                align="right"
              />
              <SortableTh
                label="Líquido"
                column="net_amount"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
                align="right"
              />
              <SortableTh
                label="Recebido"
                column="received_amount"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
                align="right"
              />
              <SortableTh
                label="Status"
                column="status"
                activeColumn={headerSort.activeColumn}
                direction={headerSort.direction}
                onSort={headerSort.onSort}
              />
              <th className="px-2 py-3">Tipo</th>
              <th className="px-2 py-3">PDF</th>
              <th className="px-2 py-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && rows.length === 0 ? (
              <tr>
                <td colSpan={14} className="px-3 py-8 text-center text-slate-500">
                  Carregando…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={14} className="px-3 py-8 text-center text-slate-500">
                  {periodMode === "ALL" ? "Nenhuma NF encontrada." : "Nenhuma NF no período."}
                </td>
              </tr>
            ) : (
              sortedRows.map((row) => {
                const overdue = isOverdue(row);
                const rowClass =
                  row.status === "CANCELADA"
                    ? "opacity-60"
                    : row.status === "RECEBIDA"
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
                      <td className="whitespace-nowrap px-2 py-2 tabular-nums">{formatCompetenceBr(row.competence_month)}</td>
                      <td className="whitespace-nowrap px-2 py-2">{row.due_days} d</td>
                      <td className="whitespace-nowrap px-2 py-2">{formatDateBr(row.due_date)}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">{formatCurrencyOrDash(row.gross_amount)}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">{formatCurrencyOrDash(row.net_amount)}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">
                        {formatCurrencyOrDash(row.received_amount)}
                      </td>
                      <td className="px-2 py-2">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${statusBadgeClass(row.status)}`}
                        >
                          {statusLabel(row)}
                        </span>
                        {overdue && row.status !== "CANCELADA" && (
                          <span className="ml-1 text-[10px] font-semibold text-red-700">Atraso</span>
                        )}
                        {row.advance_batch ? (
                          <button
                            type="button"
                            className="mt-0.5 block text-left text-[10px] text-indigo-700 hover:underline"
                            onClick={() => {
                              setViewBatchId(row.advance_batch!.id);
                              setBatchModalOpen(true);
                            }}
                          >
                            {row.advance_batch.sgc_number != null
                              ? `Antecipação SGC ${row.advance_batch.sgc_number}`
                              : "Antecipação"}
                          </button>
                        ) : null}
                      </td>
                      <td className="px-2 py-2">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${officialBadgeClass(row.is_official)}`}
                        >
                          {row.is_official ? "OFICIAL" : "NÃO OFICIAL"}
                        </span>
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
                        {row.status === "CANCELADA" && canReactivateInvoices ? (
                          <button
                            type="button"
                            disabled={reactivatingId === row.id}
                            onClick={() => void handleReactivateInvoice(row.id, row.number)}
                            className="mr-2 rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-900 hover:bg-indigo-100 disabled:opacity-50"
                          >
                            {reactivatingId === row.id ? "Reativando…" : "Reativar NF"}
                          </button>
                        ) : null}
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
                        <td colSpan={14} className="px-4 py-4">
                          <div className="space-y-5">
                            <div className="space-y-4">
                              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Dados da NF</p>
                              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
                                  <span className="font-medium text-slate-700">Competência</span>
                                  <input
                                    type="month"
                                    value={editDraft.competence}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, competence: e.target.value }))}
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
                                <label className="flex flex-col gap-1 text-xs sm:col-span-2 lg:col-span-4">
                                  <span className="font-medium text-slate-700">Cliente</span>
                                  <input
                                    value={editDraft.client_name}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, client_name: e.target.value }))}
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  />
                                </label>
                                <label className="flex items-center gap-2 text-xs sm:col-span-2 lg:col-span-4">
                                  <input
                                    type="checkbox"
                                    checked={!editDraft.is_official}
                                    onChange={(e) =>
                                      setEditDraft((d) => ({ ...d, is_official: !e.target.checked }))
                                    }
                                    disabled={!canEditInvoices || row.status === "CANCELADA"}
                                    className="h-4 w-4 rounded border-slate-300"
                                  />
                                  <span className="text-slate-700">NF Não Oficial</span>
                                </label>
                                <label className="flex flex-col gap-1 text-xs sm:col-span-2 lg:col-span-4">
                                  <span className="font-medium text-slate-700">Observações</span>
                                  <textarea
                                    value={editDraft.notes}
                                    onChange={(e) => setEditDraft((d) => ({ ...d, notes: e.target.value }))}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                    rows={4}
                                  />
                                </label>
                                <label className="flex items-center gap-2 text-xs sm:col-span-2 lg:col-span-4">
                                  <input
                                    type="checkbox"
                                    checked={editDraft.include_in_dashboard}
                                    onChange={(e) =>
                                      setEditDraft((d) => ({ ...d, include_in_dashboard: e.target.checked }))
                                    }
                                    disabled={!canEditInvoices}
                                    className="h-4 w-4 rounded border-slate-300"
                                  />
                                  <span className="text-slate-700">Considerar no Dashboard Financeiro</span>
                                </label>
                              </div>

                              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Recebimento</p>
                              <div className="grid gap-3 sm:grid-cols-2">
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Status</span>
                                  <label className="flex items-center gap-2 text-xs">
                                    <input
                                      type="checkbox"
                                      checked={editDraft.received}
                                      onChange={(e) =>
                                        setEditDraft((d) => ({
                                          ...d,
                                          received: e.target.checked,
                                          received_date: e.target.checked ? (d.received_date || todayIsoLocal()) : "",
                                        }))
                                      }
                                      disabled={!canEditInvoices || row.status === "CANCELADA"}
                                      className="h-4 w-4 rounded border-slate-300"
                                    />
                                    <span>NF recebida</span>
                                  </label>
                                </label>
                                <label className="flex flex-col gap-1 text-xs">
                                  <span className="font-medium text-slate-700">Data recebimento</span>
                                  <input
                                    type="date"
                                    value={editDraft.received_date}
                                    onChange={(e) =>
                                      setEditDraft((d) => ({ ...d, received_date: e.target.value }))
                                    }
                                    disabled={!canEditInvoices || row.status === "CANCELADA" || !editDraft.received}
                                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  />
                                </label>
                              </div>

                              <div className="flex items-center justify-between">
                                <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                                  Histórico de Antecipações
                                </p>
                                <span className="text-[11px] text-slate-400">somente leitura — gerencie no módulo Antecipações</span>
                              </div>
                              <div className="space-y-3">
                                {(row.advance_operations?.length ?? 0) > 0 ? (
                                  <div className="overflow-x-auto rounded border border-slate-200 bg-white">
                                    <table className="w-full min-w-[640px] text-left text-xs">
                                      <thead className="border-b border-slate-100 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                                        <tr>
                                          <th className="px-3 py-2 font-medium">Operação SGC</th>
                                          <th className="px-3 py-2 font-medium">Instituição</th>
                                          <th className="px-3 py-2 font-medium">Data</th>
                                          <th className="px-3 py-2 font-medium">Status</th>
                                          <th className="px-3 py-2 text-right font-medium">Valor antecipado</th>
                                          <th className="px-3 py-2 text-right font-medium">Valor realizado</th>
                                        </tr>
                                      </thead>
                                      <tbody className="divide-y divide-slate-100">
                                        {(row.advance_operations ?? []).map((op) => (
                                          <tr key={op.id} className="text-slate-700">
                                            <td className="px-3 py-2 font-semibold">
                                              <button
                                                type="button"
                                                className="text-indigo-700 hover:underline"
                                                onClick={() => {
                                                  setViewBatchId(op.id);
                                                  setBatchModalOpen(true);
                                                }}
                                              >
                                                {op.sgc_number ?? op.batch_number}
                                              </button>
                                            </td>
                                            <td className="px-3 py-2">{op.institution}</td>
                                            <td className="px-3 py-2 tabular-nums">
                                              {op.receive_date ? formatDateBr(op.receive_date) : "—"}
                                            </td>
                                            <td className="px-3 py-2">
                                              <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                                                {batchStatusLabel(op.status)}
                                              </span>
                                            </td>
                                            <td className="px-3 py-2 text-right tabular-nums">
                                              {formatCurrencyOrDash(op.advanced_amount)}
                                            </td>
                                            <td className="px-3 py-2 text-right tabular-nums">
                                              {formatCurrencyOrDash(op.received_amount)}
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                ) : (
                                  <p className="text-xs text-slate-500">Nenhuma antecipação registrada.</p>
                                )}
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
                                {row.status !== "CANCELADA" ? (
                                  <button
                                    type="button"
                                    disabled={!canEditInvoices}
                                    onClick={() => void handleCancelInvoice(row.id)}
                                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-50"
                                  >
                                    Cancelar NF
                                  </button>
                                ) : canReactivateInvoices ? (
                                  <button
                                    type="button"
                                    disabled={reactivatingId === row.id}
                                    onClick={() => void handleReactivateInvoice(row.id, row.number)}
                                    className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-900 hover:bg-indigo-100 disabled:opacity-50"
                                  >
                                    {reactivatingId === row.id ? "Reativando…" : "Reativar NF"}
                                  </button>
                                ) : null}
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

      <AdvanceBatchModal
        open={batchModalOpen}
        viewBatchId={viewBatchId}
        onClose={() => {
          setBatchModalOpen(false);
          setViewBatchId(null);
        }}
        onCreated={() => void load()}
        onOpenOperation={(batchId) => setViewBatchId(batchId)}
      />
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
