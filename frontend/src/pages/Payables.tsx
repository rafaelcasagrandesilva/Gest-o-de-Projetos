import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  createManualPayableSnapshot,
  deletePayableSnapshot,
  formatMonthToYYYYMM,
  listPayableSnapshots,
  registerPayablePayment,
  reversePayablePayment,
  updatePayableSnapshot,
  type PayableSnapshotRow,
  type PayableSnapshotStatus,
  type PayableSnapshotType,
} from "@/services/payables";
import { usePermission } from "@/hooks/usePermission";
import { useAuth } from "@/context/AuthContext";
import { PeriodFilter } from "@/components/PeriodFilter";
import { TruncatedCell } from "@/components/TruncatedText";
import { listProjects, type Project } from "@/services/projects";
import { formatApiError } from "@/utils/apiError";

/** Centros fixos permitidos no manual — alinhado a `MANUAL_PAYABLE_FIXED_COST_CENTERS` no backend. */
const PAYABLES_MANUAL_FIXED_COST_CENTERS = ["Administrativo", "Financeiro"] as const;
const PAYABLES_MANUAL_CC_ADMIN = "Administrativo";
const PAYABLES_FIXED_CC_SET = new Set<string>(PAYABLES_MANUAL_FIXED_COST_CENTERS);

type ActionModal =
  | { open: false }
  | { open: true; mode: "register" | "reverse"; row: PayableSnapshotRow }
  | { open: true; mode: "delete"; row: PayableSnapshotRow };

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Valor numérico para input (pt-BR: milhar com ponto, decimal com vírgula), alinhado ao restante da tela. */
function formatMoneyFieldBr(n: number): string {
  if (!Number.isFinite(n)) return "";
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function statusBadgeClass(s: PayableSnapshotStatus): string {
  if (s === "PAGO") return "bg-emerald-100 text-emerald-900 ring-emerald-200";
  if (s === "PARCIAL") return "bg-blue-100 text-blue-900 ring-blue-200";
  return "bg-amber-100 text-amber-900 ring-amber-200";
}

function typeLabel(t: PayableSnapshotType): string {
  if (t === "COLLABORATOR") return "Colaborador";
  if (t === "VEHICLE") return "Veículos";
  if (t === "FIXED_COST") return "Custo diverso";
  if (t === "ANTECIPACAO") return "Antecipação";
  return "Manual";
}

function parseMoneyInput(raw: string): number {
  const s0 = raw.trim().replace(/\s/g, "").replace(/R\$\s*/i, "");
  if (s0.includes(",")) {
    return Number.parseFloat(s0.replace(/\./g, "").replace(",", "."));
  }
  return Number.parseFloat(s0);
}

export function Payables() {
  const { user } = useAuth();
  const canView = usePermission("payables.view");
  const canEdit = usePermission("costs.edit");
  const canRegenerateSnapshot = Boolean(user?.is_superuser);

  const [periodMode, setPeriodMode] = useState<"MONTH" | "ALL">("MONTH");
  const [period, setPeriod] = useState(() => formatMonthToYYYYMM(new Date()));
  const [statusFilter, setStatusFilter] = useState<PayableSnapshotStatus | "">("");
  const [search, setSearch] = useState("");

  const [rows, setRows] = useState<PayableSnapshotRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    amount: "",
    due_date: "",
    category: "",
    cost_center: PAYABLES_MANUAL_CC_ADMIN,
  });

  const [projectOptions, setProjectOptions] = useState<Project[]>([]);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState(0);
  const [editDate, setEditDate] = useState("");

  const [actionModal, setActionModal] = useState<ActionModal>({ open: false });
  const [modalAmount, setModalAmount] = useState("");
  const [modalObs, setModalObs] = useState("");
  const [modalBusy, setModalBusy] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    if (!canEdit) return;
    let cancelled = false;
    void (async () => {
      try {
        const list = await listProjects({ status: "ALL", limit: 200 });
        if (!cancelled) {
          setProjectOptions([...list].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")));
        }
      } catch {
        if (!cancelled) setProjectOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canEdit]);

  useEffect(() => {
    const names = new Set(projectOptions.map((p) => p.name.trim()));
    setForm((f) => {
      const cc = f.cost_center.trim();
      if (cc && !PAYABLES_FIXED_CC_SET.has(cc) && !names.has(cc)) {
        return { ...f, cost_center: PAYABLES_MANUAL_CC_ADMIN };
      }
      return f;
    });
  }, [projectOptions]);

  const load = useCallback(async () => {
    if (!canView) return;
    // Evita dados stale: sempre limpa antes do fetch.
    setError(null);
    setEmptyMessage(null);
    setLoading(true);
    setRows([]);
    try {
      const list =
        periodMode === "ALL" ? await listPayableSnapshots() : await listPayableSnapshots({ month: period });
      setRows(list);
      setEmptyMessage(list.length === 0 ? "Nenhuma conta a pagar neste período." : null);
    } catch (e) {
      if (isAxiosError(e)) {
        const status = e.response?.status;
        const detail = formatApiError(e);
        if (status === 409) {
          // 409 = snapshot não gerado (ex.: nenhuma linha criada) → estado vazio, não erro.
          setRows([]);
          setError(null);
          setEmptyMessage("Nenhuma conta a pagar neste período.");
        } else {
          setError(detail);
          setRows([]);
          setEmptyMessage(null);
        }
      } else {
        setError("Erro ao carregar contas a pagar.");
        setRows([]);
        setEmptyMessage(null);
      }
    } finally {
      setLoading(false);
    }
  }, [canView, period, periodMode]);

  async function regenerateMonthSnapshot() {
    if (!canRegenerateSnapshot || periodMode !== "MONTH") return;
    const ok = window.confirm(
      "Regerar o snapshot deste mês?\n\n" +
        "Isso apaga todas as linhas do mês no servidor e gera de novo com as regras atuais " +
        "(nomes, centros de custo, etc.).\n\n" +
        "Pagamentos já registrados nessas linhas podem ser perdidos — use só se souber o impacto.",
    );
    if (!ok) return;
    setRegenerating(true);
    setError(null);
    try {
      const list = await listPayableSnapshots({ month: period, forceRegenerate: true });
      setRows(list);
      setEmptyMessage(list.length === 0 ? "Nenhuma conta a pagar neste período." : null);
    } catch (e) {
      if (isAxiosError(e)) {
        setError(formatApiError(e));
      } else {
        setError("Não foi possível regerar o snapshot.");
      }
      setRows([]);
      setEmptyMessage(null);
    } finally {
      setRegenerating(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (statusFilter && r.status !== statusFilter) return false;
      if (!q) return true;
      const hay = `${r.name} ${r.cost_center} ${r.category}`.toLowerCase();
      return hay.includes(q);
    });
  }, [rows, statusFilter, search]);

  const totals = useMemo(() => {
    let total = 0;
    let pago = 0;
    for (const r of filteredRows) {
      total += Number(r.amount_final ?? 0);
      pago += Number(r.amount_paid ?? 0);
    }
    total = Math.round(total * 100) / 100;
    pago = Math.round(pago * 100) / 100;
    const emAberto = Math.round((total - pago) * 100) / 100;
    return { total, pago, emAberto };
  }, [filteredRows]);

  function closeActionModal() {
    setActionModal({ open: false });
    setModalAmount("");
    setModalObs("");
    setModalBusy(false);
  }

  function openRegisterPayment(row: PayableSnapshotRow) {
    if (!canEdit) return;
    setError(null);
    setModalObs("");
    setModalAmount(row.amount_remaining > 0 ? formatMoneyFieldBr(row.amount_remaining) : "");
    setActionModal({ open: true, mode: "register", row });
  }

  function openReversePayment(row: PayableSnapshotRow) {
    if (!canEdit) return;
    setError(null);
    setModalObs("");
    setModalAmount(row.amount_paid > 0 ? formatMoneyFieldBr(row.amount_paid) : "");
    setActionModal({ open: true, mode: "reverse", row });
  }

  function openDeleteManual(row: PayableSnapshotRow) {
    if (!canEdit) return;
    setError(null);
    setActionModal({ open: true, mode: "delete", row });
  }

  async function submitPaymentModal() {
    if (!actionModal.open || actionModal.mode === "delete") return;
    const row = actionModal.row;
    const amt = parseMoneyInput(modalAmount.trim());
    if (!Number.isFinite(amt) || amt <= 0) {
      setError("Informe um valor maior que zero.");
      return;
    }
    setModalBusy(true);
    setError(null);
    try {
      const obs = modalObs.trim() ? modalObs.trim() : null;
      const updated =
        actionModal.mode === "register"
          ? await registerPayablePayment(row.id, { amount: amt, observation: obs })
          : await reversePayablePayment(row.id, { amount: amt, observation: obs });
      setRows((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      if (editingId === row.id) setEditingId(null);
      closeActionModal();
    } catch (e) {
      if (isAxiosError(e)) setError(formatApiError(e));
      else setError("Não foi possível concluir a operação.");
    } finally {
      setModalBusy(false);
    }
  }

  async function confirmDeleteManual() {
    if (!actionModal.open || actionModal.mode !== "delete") return;
    const row = actionModal.row;
    setModalBusy(true);
    setError(null);
    try {
      await deletePayableSnapshot(row.id);
      if (editingId === row.id) setEditingId(null);
      await load();
      closeActionModal();
    } catch (e) {
      if (isAxiosError(e)) setError(formatApiError(e));
      else setError("Não foi possível excluir.");
    } finally {
      setModalBusy(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!canEdit) return;
    const amount = Number.parseFloat(form.amount.replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Informe um valor válido.");
      return;
    }
    if (!form.name.trim()) {
      setError("Informe a descrição.");
      return;
    }
    if (!form.category.trim()) {
      setError("Informe a categoria.");
      return;
    }
    if (!form.cost_center.trim()) {
      setError("Informe o centro de custo.");
      return;
    }
    if (!form.due_date) {
      setError("Informe o vencimento.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await createManualPayableSnapshot({
        month: period,
        name: form.name.trim(),
        amount,
        due_date: form.due_date,
        category: form.category.trim(),
        cost_center: form.cost_center.trim(),
      });
      setShowForm(false);
      setForm({
        name: "",
        amount: "",
        due_date: "",
        category: "",
        cost_center: PAYABLES_MANUAL_CC_ADMIN,
      });
      await load();
    } catch (e) {
      if (isAxiosError(e)) setError(formatApiError(e));
      else setError("Não foi possível criar.");
    } finally {
      setSaving(false);
    }
  }

  function startEdit(row: PayableSnapshotRow) {
    if (!canEdit) return;
    setError(null);
    setEditingId(row.id);
    setEditValue(Number(row.amount_final));
    setEditDate(row.due_date.slice(0, 10));
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function saveEdit() {
    if (!canEdit || !editingId) return;
    if (!editDate.trim()) {
      setError("Informe o vencimento.");
      return;
    }
    if (!Number.isFinite(editValue) || editValue < 0) {
      setError("Valor não pode ser negativo.");
      return;
    }
    if (editValue <= 0) {
      setError("Informe um valor maior que zero.");
      return;
    }

    setEditSaving(true);
    setError(null);
    try {
      const updated = await updatePayableSnapshot(editingId, {
        amount_final: editValue,
        due_date: editDate,
      });
      setRows((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      setEditingId(null);
    } catch (e) {
      if (isAxiosError(e)) setError(formatApiError(e));
      else setError("Não foi possível salvar a edição.");
    } finally {
      setEditSaving(false);
    }
  }

  if (!canView) {
    return <p className="text-slate-600">Sem permissão para visualizar contas a pagar.</p>;
  }

  const modalPaymentTitle =
    actionModal.open && actionModal.mode !== "delete"
      ? actionModal.mode === "register"
        ? "Registrar pagamento"
        : "Estornar pagamento"
      : "";

  return (
    <div className="mx-auto max-w-[1600px] space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Contas a pagar</h1>
          <p className="mt-1 text-sm text-slate-600">
            Snapshot mensal: depois de gerado, descrições e centros de custo só mudam ao{" "}
            <strong>regerar o mês</strong> (ação restrita a super usuário). Pagamentos parciais e estornos atualizam o
            valor pago acumulado nas linhas atuais.
          </p>
        </div>
        <button
          type="button"
          disabled={!canEdit || periodMode === "ALL"}
          onClick={() => setShowForm((s) => !s)}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {showForm ? "Fechar" : "Adicionar despesa"}
        </button>
      </div>
      {periodMode === "ALL" && (
        <p className="text-sm text-slate-600">
          Para adicionar despesa manual, selecione um mês específico.
        </p>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Kpi label="Total (valor final)" value={formatBRL(totals.total)} />
        <Kpi label="Pago (acumulado)" value={formatBRL(totals.pago)} accent="text-emerald-800" />
        <Kpi label="Em aberto" value={formatBRL(totals.emAberto)} accent="text-amber-800" />
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <PeriodFilter
            label="Mês (pagamento)"
            mode={periodMode}
            value={period}
            onModeChange={setPeriodMode}
            onChange={setPeriod}
          />

          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Status</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="">Todos</option>
              <option value="ABERTO">Aberto</option>
              <option value="PARCIAL">Parcial</option>
              <option value="PAGO">Pago</option>
            </select>
          </label>

          <label className="flex min-w-[240px] flex-1 flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Buscar</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Nome, centro de custo ou categoria…"
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="w-fit rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            Atualizar
          </button>
          {periodMode === "MONTH" && canRegenerateSnapshot && (
            <button
              type="button"
              disabled={regenerating}
              onClick={() => void regenerateMonthSnapshot()}
              className="w-fit rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {regenerating ? "Regerando…" : "Regerar snapshot deste mês"}
            </button>
          )}
        </div>
      </section>

      {showForm && canEdit && (
        <form
          onSubmit={handleCreate}
          className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50/80 p-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <Field label="Descrição *">
            <input
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Valor *">
            <input
              required
              value={form.amount}
              onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              placeholder="0,00"
              inputMode="decimal"
            />
          </Field>
          <Field label="Vencimento *">
            <input
              type="date"
              required
              value={form.due_date}
              onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Categoria *">
            <input
              required
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Centro de custo *">
            <select
              required
              value={form.cost_center}
              onChange={(e) => setForm((f) => ({ ...f, cost_center: e.target.value }))}
              className="w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
            >
              {PAYABLES_MANUAL_FIXED_COST_CENTERS.map((label) => (
                <option key={label} value={label}>
                  {label}
                </option>
              ))}
              {projectOptions
                .filter((p) => !PAYABLES_FIXED_CC_SET.has(p.name.trim()))
                .map((p) => (
                  <option key={p.id} value={p.name}>
                    {p.name}
                  </option>
                ))}
            </select>
          </Field>
          <div className="sm:col-span-2 lg:col-span-3">
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Salvando…" : "Salvar despesa"}
            </button>
          </div>
        </form>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1380px] w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-2 py-3">Tipo</th>
              <th className="px-2 py-3">Nome</th>
              <th className="px-2 py-3">Mês</th>
              <th className="px-2 py-3">Centro de custo</th>
              <th className="px-2 py-3 text-right">Valor original</th>
              <th className="px-2 py-3 text-right">Valor final</th>
              <th className="px-2 py-3 text-right">Pago</th>
              <th className="px-2 py-3 text-right">Saldo</th>
              <th className="px-2 py-3">Vencimento</th>
              <th className="px-2 py-3">Status</th>
              <th className="px-2 py-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td colSpan={11} className="px-3 py-10 text-center text-slate-500">
                  <div className="flex items-center justify-center gap-2">
                    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
                    <span>Carregando…</span>
                  </div>
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td colSpan={11} className="px-3 py-10 text-center text-slate-500">
                  Não foi possível carregar os dados.
                </td>
              </tr>
            ) : filteredRows.length === 0 ? (
              <tr>
                <td colSpan={11} className="px-3 py-8 text-center text-slate-500">
                  {rows.length === 0
                    ? (emptyMessage ?? "Nenhuma conta a pagar neste período.")
                    : "Nenhum item para os filtros atuais."}
                </td>
              </tr>
            ) : (
              filteredRows.map((r) => {
                const isEditing = editingId === r.id;
                const saldoPositivo = r.amount_remaining > 0.005;
                const temPago = r.amount_paid > 0.005;
                return (
                  <tr key={r.id} className="hover:bg-slate-50/80">
                    <td className="whitespace-nowrap px-2 py-2 text-slate-700">{typeLabel(r.type)}</td>
                    <td className="min-w-0 max-w-[300px] px-2 py-2 align-middle text-slate-900">
                      <TruncatedCell value={r.name} maxWidthClass="max-w-[300px]" />
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-slate-700">{r.month.slice(0, 7)}</td>
                    <td className="min-w-0 max-w-[280px] px-2 py-2 align-middle text-slate-700">
                      <TruncatedCell value={r.cost_center} maxWidthClass="max-w-[280px]" />
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-700">
                      {formatBRL(r.amount_original)}
                    </td>
                    <td className="min-w-[120px] whitespace-nowrap px-2 py-2 text-right align-middle tabular-nums text-slate-900">
                      {isEditing ? (
                        <input
                          type="number"
                          min={0}
                          step="0.01"
                          inputMode="decimal"
                          value={Number.isFinite(editValue) ? editValue : 0}
                          onChange={(e) => {
                            const raw = e.target.value;
                            if (raw === "") {
                              setEditValue(0);
                              return;
                            }
                            const n = Number.parseFloat(raw);
                            if (Number.isFinite(n)) setEditValue(n);
                          }}
                          className="w-full min-w-[6.5rem] rounded border border-slate-300 px-2 py-1 text-right text-sm"
                        />
                      ) : (
                        formatBRL(r.amount_final)
                      )}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-800">
                      {formatBRL(r.amount_paid)}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums font-medium text-slate-900">
                      {formatBRL(r.amount_remaining)}
                    </td>
                    <td className="min-w-[130px] whitespace-nowrap px-2 py-2 align-middle">
                      {isEditing ? (
                        <input
                          type="date"
                          required
                          value={editDate}
                          onChange={(e) => setEditDate(e.target.value)}
                          className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
                        />
                      ) : (
                        formatDateBr(r.due_date)
                      )}
                    </td>
                    <td className="px-2 py-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${statusBadgeClass(r.status)}`}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-right">
                      {isEditing ? (
                        <span className="inline-flex flex-wrap items-center justify-end gap-1">
                          <button
                            type="button"
                            disabled={!canEdit || editSaving}
                            onClick={() => void saveEdit()}
                            className="rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-800 hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {editSaving ? "Salvando…" : "Salvar"}
                          </button>
                          <button
                            type="button"
                            disabled={editSaving}
                            onClick={cancelEdit}
                            className="rounded border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Cancelar
                          </button>
                        </span>
                      ) : (
                        <span className="inline-flex flex-wrap items-center justify-end gap-x-1 gap-y-1">
                          <button
                            type="button"
                            disabled={!canEdit}
                            onClick={() => startEdit(r)}
                            className="rounded px-1.5 py-0.5 text-xs text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Editar
                          </button>
                          <button
                            type="button"
                            disabled={!canEdit || !saldoPositivo || editingId === r.id}
                            onClick={() => openRegisterPayment(r)}
                            className="rounded px-1.5 py-0.5 text-xs text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Registrar pagamento
                          </button>
                          <button
                            type="button"
                            disabled={!canEdit || !temPago || editingId === r.id}
                            onClick={() => openReversePayment(r)}
                            className="rounded px-1.5 py-0.5 text-xs text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Estornar
                          </button>
                          <button
                            type="button"
                            disabled={!canEdit || r.type !== "MANUAL" || editingId === r.id}
                            onClick={() => openDeleteManual(r)}
                            className="rounded px-1.5 py-0.5 text-xs text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Excluir
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {actionModal.open && actionModal.mode !== "delete" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="pay-modal-title"
            className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-lg"
          >
            <h3 id="pay-modal-title" className="text-lg font-semibold text-slate-900">
              {modalPaymentTitle}
            </h3>
            <p className="mt-1 text-sm text-slate-600">{actionModal.row.name}</p>
            <p className="mt-2 text-xs text-slate-500">
              Valor final: <span className="font-medium text-slate-700">{formatBRL(actionModal.row.amount_final)}</span>
              {" · "}
              Pago: <span className="font-medium text-slate-700">{formatBRL(actionModal.row.amount_paid)}</span>
              {" · "}
              Saldo: <span className="font-medium text-slate-700">{formatBRL(actionModal.row.amount_remaining)}</span>
            </p>
            <div className="mt-4 space-y-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">
                  {actionModal.mode === "register" ? "Valor do pagamento *" : "Valor a estornar *"}
                </span>
                <input
                  value={modalAmount}
                  onChange={(e) => setModalAmount(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="0,00"
                  inputMode="decimal"
                  autoComplete="off"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Observação (opcional)</span>
                <textarea
                  value={modalObs}
                  onChange={(e) => setModalObs(e.target.value)}
                  rows={2}
                  className="resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                disabled={modalBusy}
                onClick={closeActionModal}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={modalBusy}
                onClick={() => void submitPaymentModal()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {modalBusy ? "Processando…" : "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      )}

      {actionModal.open && actionModal.mode === "delete" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="del-modal-title"
            className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-lg"
          >
            <h3 id="del-modal-title" className="text-lg font-semibold text-slate-900">
              Excluir despesa avulsa
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              Confirma a exclusão de <span className="font-medium text-slate-900">{actionModal.row.name}</span>? Esta
              ação não pode ser desfeita.
            </p>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                disabled={modalBusy}
                onClick={closeActionModal}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={modalBusy}
                onClick={() => void confirmDeleteManual()}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {modalBusy ? "Excluindo…" : "Excluir"}
              </button>
            </div>
          </div>
        </div>
      )}
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
