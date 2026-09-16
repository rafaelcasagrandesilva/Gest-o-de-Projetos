import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  createManualPayableSnapshot,
  bulkDeleteManualPayables,
  deletePayableSnapshot,
  formatMonthToYYYYMM,
  listPayableSnapshots,
  reconcilePayableSnapshot,
  registerPayablePayment,
  reversePayablePayment,
  updatePayableSnapshot,
  PAYABLE_RESULT_CLASSIFICATIONS,
  PAYABLE_RESULT_CLASSIFICATION_LABELS,
  type PayableResultClassification,
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
import { formatCurrencyField, formatCurrencyOrDash, normalizeCurrencyForApi, parseCurrencyInput } from "@/utils/currency";
import { PayablesImportModal } from "@/components/PayablesImportModal";
import { SortableTh } from "@/components/table";
import { useTableSort, type TableSortHeaderProps } from "@/hooks/useTableSort";
import { PAYABLE_SORT_COLUMNS, defaultPayableOperationalSort, defaultPayableSort } from "@/tableSort/payables";
import {
  payableCashFlowLabelFromDate,
  payableCompetenceLabel,
  todayIsoLocal,
} from "@/utils/payableCompetence";
import { Money } from "@/components/Money";

/** Centros fixos permitidos no manual — alinhado a `MANUAL_PAYABLE_FIXED_COST_CENTERS` no backend. */
const PAYABLES_MANUAL_FIXED_COST_CENTERS = ["Administrativo", "Financeiro"] as const;
const PAYABLES_MANUAL_CC_ADMIN = "Administrativo";
const PAYABLES_FIXED_CC_SET = new Set<string>(PAYABLES_MANUAL_FIXED_COST_CENTERS);

type ActionModal =
  | { open: false }
  | { open: true; mode: "register" | "reverse"; row: PayableSnapshotRow }
  | { open: true; mode: "delete"; row: PayableSnapshotRow };

/** Valor monetário ou "—" quando redigido pelo backend — fonte única (utils/currency). */
const formatBRL = formatCurrencyOrDash;
const money = formatCurrencyOrDash;

/** Valor numérico para input (pt-BR, sem R$) — fonte única (utils/currency). */
const formatMoneyFieldBr = formatCurrencyField;

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function statusBadgeClass(s: PayableSnapshotStatus, isOverpaid = false): string {
  if (s === "PAGO" && isOverpaid) return "bg-amber-100 text-amber-900 ring-amber-300";
  if (s === "PAGO") return "bg-emerald-100 text-emerald-900 ring-emerald-200";
  if (s === "PARCIAL") return "bg-blue-100 text-blue-900 ring-blue-200";
  return "bg-amber-100 text-amber-900 ring-amber-200";
}

function saldoClassName(remaining: number | null, isOverpaid: boolean): string {
  if (remaining == null) return "text-slate-600";
  if (isOverpaid || remaining < -0.005) return "text-amber-800";
  if (remaining > 0.005) return "text-slate-900";
  return "text-slate-600";
}

function typeLabel(t: PayableSnapshotType): string {
  if (t === "COLLABORATOR") return "Colaborador";
  if (t === "VEHICLE") return "Veículos";
  if (t === "FIXED_COST") return "Custo diverso";
  if (t === "ENDIVIDAMENTO" || t === "FINANCIAL") return "Endividamento";
  if (t === "ANTECIPACAO" || t === "ANTECIPACAO_OPERACAO") return "Antecipação";
  return "Manual";
}

/**
 * Rótulo do "Tipo" exibido na linha. Para os lançamentos automáticos de Custos Indiretos
 * gerados a partir do cadastro, mostra a categoria ("Custo Indireto" / "Colaborador");
 * os demais (projetos, legado, manuais) mantêm o rótulo por tipo — sem regressão.
 * A categoria gravada continua "Custo Fixo"; só o texto exibido mudou (espelha
 * `payable_display_group` no backend).
 */
function payableTipoLabel(r: PayableSnapshotRow): string {
  if (r.type === "FIXED_COST" && r.category === "Custo Fixo") return "Custo Indireto";
  if (r.type === "FIXED_COST" && r.category === "Colaborador") return r.category;
  return typeLabel(r.type);
}

/** Linha manual ainda sem classificação no Resultado da Empresa. */
function isUnclassifiedManual(r: PayableSnapshotRow): boolean {
  return r.type === "MANUAL" && !r.result_classification;
}

/** Chave de comparação do centro de custo com o nome do projeto (mesma regra do backend: sem caixa/espaços extras). */
function costCenterKey(value: string | null | undefined): string {
  return (value ?? "").trim().split(/\s+/).join(" ").toLocaleLowerCase("pt-BR");
}

/** Opções de classificação: «Custo direto do projeto» só quando o centro de custo é um projeto ATIVO. */
function resultClassificationOptions(
  costCenter: string,
  activeProjectCostCenters: Set<string>,
  current?: PayableResultClassification | "" | null,
): PayableResultClassification[] {
  const direct = activeProjectCostCenters.has(costCenterKey(costCenter)) || current === "DIRETO";
  return PAYABLE_RESULT_CLASSIFICATIONS.filter((c) => c !== "DIRETO" || direct);
}

/** Badge discreto da classificação no resultado (só linhas MANUAL). */
function ResultClassificationBadge({ row }: { row: PayableSnapshotRow }) {
  if (row.type !== "MANUAL") return null;
  const base = "inline-flex whitespace-nowrap rounded-full px-1.5 py-0 text-[10px] font-medium ring-1";
  const c = row.result_classification;
  if (!c) {
    return (
      <span
        className={`${base} bg-amber-50 text-amber-800 ring-amber-200`}
        title="Defina como esta despesa entra no Resultado da Empresa (editar)."
      >
        Sem classificação
      </span>
    );
  }
  if (c === "DIRETO") {
    return (
      <span
        className={`${base} bg-sky-50 text-sky-800 ring-sky-200`}
        title={`Entra no resultado como custo direto do projeto ${row.cost_center}`}
      >
        Custo direto
      </span>
    );
  }
  if (c === "INDIRETO") {
    return (
      <span className={`${base} bg-orange-50 text-orange-800 ring-orange-200`} title="Entra no resultado como custo indireto">
        Custo indireto
      </span>
    );
  }
  if (c === "ENDIVIDAMENTO") {
    return (
      <span className={`${base} bg-violet-50 text-violet-800 ring-violet-200`} title="Entra no resultado como endividamento">
        Endividamento
      </span>
    );
  }
  return (
    <span className={`${base} bg-slate-100 text-slate-600 ring-slate-200`} title="Não entra no Resultado da Empresa">
      Fora do resultado
    </span>
  );
}

export function Payables() {
  const { user } = useAuth();
  const canView = usePermission("payables.list");
  // CAP tem permissão de edição PRÓPRIA (antes usava costs.edit, acoplado ao módulo de Custos).
  const canEdit = usePermission("payables.update");
  // Incluir e excluir despesa têm verbo próprio (o backend exige payables.create / payables.delete).
  const canCreate = usePermission("payables.create");
  const canDelete = usePermission("payables.delete");
  const canRegenerateSnapshot = Boolean(user?.is_superuser);
  const canReconcileSnapshot = usePermission("payable_snapshot.reconcile");

  const [periodMode, setPeriodMode] = useState<"MONTH" | "ALL">("MONTH");
  const [period, setPeriod] = useState(() => formatMonthToYYYYMM(new Date()));
  const [statusFilter, setStatusFilter] = useState<PayableSnapshotStatus | "">("");
  const [search, setSearch] = useState("");
  const [onlyUnclassifiedManual, setOnlyUnclassifiedManual] = useState(false);

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
    include_in_dashboard: true,
    result_classification: "" as PayableResultClassification | "",
  });

  const [projectOptions, setProjectOptions] = useState<Project[]>([]);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState(0);
  const [editDate, setEditDate] = useState("");
  const [editIncludeInDashboard, setEditIncludeInDashboard] = useState(true);
  const [editResultClassification, setEditResultClassification] = useState<PayableResultClassification | "">("");

  const [actionModal, setActionModal] = useState<ActionModal>({ open: false });
  const [modalAmount, setModalAmount] = useState("");
  const [modalPaymentDate, setModalPaymentDate] = useState(() => todayIsoLocal());
  const [modalReversalReason, setModalReversalReason] = useState("");
  const [modalObs, setModalObs] = useState("");
  const [modalBusy, setModalBusy] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  // Exclusão em massa de lançamentos manuais.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);

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

  const activeProjectCostCenters = useMemo(
    () => new Set(projectOptions.filter((p) => p.is_active).map((p) => costCenterKey(p.name))),
    [projectOptions],
  );

  const load = useCallback(async () => {
    if (!canView) return;
    // Evita dados stale: sempre limpa antes do fetch.
    setError(null);
    setEmptyMessage(null);
    setLoading(true);
    setRows([]);
    setSelectedIds(new Set());
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

  async function reconcileMonthSnapshot() {
    if (!canReconcileSnapshot || periodMode !== "MONTH") return;
    const ok = window.confirm(
      "Reconciliar o snapshot deste mês?\n\n" +
        "Verifica os lançamentos automáticos cuja origem (colaborador, custo indireto, " +
        "alocação, antecipação) foi removida e os marca como obsoletos.\n\n" +
        "Não altera valores, pagamentos ou estornos; apenas sinaliza resíduos para limpeza.",
    );
    if (!ok) return;
    setReconciling(true);
    setError(null);
    try {
      const result = await reconcilePayableSnapshot(period);
      const list = await listPayableSnapshots({ month: period });
      setRows(list);
      setEmptyMessage(list.length === 0 ? "Nenhuma conta a pagar neste período." : null);
      window.alert(
        `Reconciliação concluída.\n\n` +
          `Avaliados: ${result.checked}\n` +
          `Marcados como obsoletos: ${result.marked_obsolete}\n` +
          `Reativados (origem voltou): ${result.cleared}\n` +
          `Obsoletos no mês: ${result.obsolete_total}`,
      );
    } catch (e) {
      if (isAxiosError(e)) {
        setError(formatApiError(e));
      } else {
        setError("Não foi possível reconciliar o snapshot.");
      }
    } finally {
      setReconciling(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (statusFilter && r.status !== statusFilter) return false;
      if (onlyUnclassifiedManual && !isUnclassifiedManual(r)) return false;
      if (!q) return true;
      const hay = `${r.name} ${r.cost_center} ${r.category}`.toLowerCase();
      return hay.includes(q);
    });
  }, [rows, statusFilter, search, onlyUnclassifiedManual]);

  const unclassifiedManualCount = useMemo(() => rows.filter(isUnclassifiedManual).length, [rows]);

  const { sortedRows, headerSort } = useTableSort(filteredRows, PAYABLE_SORT_COLUMNS, {
    defaultCompare: periodMode === "MONTH" ? defaultPayableOperationalSort : defaultPayableSort,
  });

  // Exclusão em massa: só lançamentos MANUAIS visíveis nos filtros atuais podem ser selecionados.
  const selectableManualIds = useMemo(
    () => sortedRows.filter((r) => r.type === "MANUAL").map((r) => r.id),
    [sortedRows],
  );
  const selectedRows = useMemo(
    () => sortedRows.filter((r) => r.type === "MANUAL" && selectedIds.has(r.id)),
    [sortedRows, selectedIds],
  );
  const selectedSummary = useMemo(() => {
    const redacted = selectedRows.some((r) => r.amount_final == null);
    const withPayment = selectedRows.filter((r) => (r.amount_paid ?? 0) > 0.005);
    return {
      total: redacted ? null : selectedRows.reduce((acc, r) => acc + (r.amount_final ?? 0), 0),
      paidCount: withPayment.length,
      paid: redacted ? null : withPayment.reduce((acc, r) => acc + (r.amount_paid ?? 0), 0),
    };
  }, [selectedRows]);

  const totals = useMemo(() => {
    // Sem "Dados sensíveis" o backend redige os valores (null) → totais ficam ocultos ("—"),
    // não zerados (evita número enganoso). Redação é tudo-ou-nada por usuário.
    const redacted = filteredRows.some((r) => r.amount_final == null);
    if (redacted) {
      return { total: null as number | null, pago: null as number | null, emAberto: null as number | null };
    }
    let total = 0;
    let pago = 0;
    for (const r of filteredRows) {
      total += Number(r.amount_final ?? 0);
      if (periodMode === "MONTH") {
        pago += Number(r.paid_in_period ?? 0);
      } else {
        pago += Number(r.amount_paid ?? 0);
      }
    }
    total = Math.round(total * 100) / 100;
    pago = Math.round(pago * 100) / 100;
    const saldoLiquido = Math.round(
      filteredRows.reduce((s, r) => s + Number(r.amount_remaining ?? 0), 0) * 100,
    ) / 100;
    return { total, pago, emAberto: saldoLiquido };
  }, [filteredRows, periodMode]);

  function closeActionModal() {
    setActionModal({ open: false });
    setModalAmount("");
    setModalPaymentDate(todayIsoLocal());
    setModalReversalReason("");
    setModalObs("");
    setModalBusy(false);
  }

  function openRegisterPayment(row: PayableSnapshotRow) {
    if (!canEdit) return;
    setError(null);
    setModalObs("");
    setModalPaymentDate(todayIsoLocal());
    const saldo = Number(row.amount_remaining ?? 0);
    setModalAmount(saldo > 0.005 ? formatMoneyFieldBr(saldo) : "");
    setActionModal({ open: true, mode: "register", row });
  }

  const modalOverpaymentPreview = useMemo(() => {
    if (!actionModal.open || actionModal.mode !== "register") return null;
    const row = actionModal.row;
    const amt = parseCurrencyInput(modalAmount.trim());
    if (!Number.isFinite(amt) || amt <= 0) return null;
    const newPaid = Math.round(((row.amount_paid ?? 0) + amt) * 100) / 100;
    const newRemaining = Math.round(((row.amount_final ?? 0) - newPaid) * 100) / 100;
    if (newPaid > (row.amount_final ?? 0) + 0.02) {
      return {
        newPaid,
        newRemaining,
        overpaidAmount: Math.round((newPaid - (row.amount_final ?? 0)) * 100) / 100,
      };
    }
    return { newPaid, newRemaining, overpaidAmount: 0 };
  }, [actionModal, modalAmount]);

  function openReversePayment(row: PayableSnapshotRow) {
    if (!canEdit) return;
    setError(null);
    setModalObs("");
    setModalReversalReason("");
    setModalAmount((row.amount_paid ?? 0) > 0 ? formatMoneyFieldBr(row.amount_paid ?? 0) : "");
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
    const amt = parseCurrencyInput(modalAmount.trim());
    if (!Number.isFinite(amt) || amt <= 0) {
      setError("Informe um valor maior que zero.");
      return;
    }
    if (actionModal.mode === "register") {
      if (!modalPaymentDate) {
        setError("Informe a data do pagamento.");
        return;
      }
      if (modalPaymentDate > todayIsoLocal()) {
        setError("A data do pagamento não pode ser futura.");
        return;
      }
    }
    setModalBusy(true);
    setError(null);
    try {
      const obs = modalObs.trim() ? modalObs.trim() : null;
      const allowOver =
        actionModal.mode === "register" &&
        modalOverpaymentPreview != null &&
        modalOverpaymentPreview.overpaidAmount > 0.02;
      const updated =
        actionModal.mode === "register"
          ? await registerPayablePayment(row.id, {
              amount: amt,
              payment_date: modalPaymentDate,
              observation: obs,
              allow_overpayment: allowOver,
            })
          : await reversePayablePayment(row.id, {
              amount: amt,
              reversal_reason: modalReversalReason.trim() || null,
              observation: obs,
            });
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

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAllManual() {
    setSelectedIds((prev) => {
      const allSelected = selectableManualIds.length > 0 && selectableManualIds.every((id) => prev.has(id));
      return allSelected ? new Set() : new Set(selectableManualIds);
    });
  }

  async function confirmBulkDelete() {
    if (!canDelete || selectedRows.length === 0) return;
    setBulkBusy(true);
    setError(null);
    try {
      await bulkDeleteManualPayables(selectedRows.map((r) => r.id));
      if (editingId && selectedIds.has(editingId)) setEditingId(null);
      setBulkDeleteOpen(false);
      await load();
    } catch (e) {
      setBulkDeleteOpen(false);
      if (isAxiosError(e)) setError(formatApiError(e));
      else setError("Não foi possível excluir os lançamentos selecionados.");
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!canCreate) return;
    const amount = normalizeCurrencyForApi(form.amount);
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
    if (!form.result_classification) {
      setError("Informe como a despesa entra no resultado.");
      return;
    }
    if (form.result_classification === "DIRETO" && !activeProjectCostCenters.has(costCenterKey(form.cost_center))) {
      setError("“Custo direto do projeto” exige um projeto ativo como centro de custo.");
      return;
    }
    const resultClassification = form.result_classification;

    setSaving(true);
    setError(null);
    try {
      const competenceMonth = form.due_date.trim().slice(0, 7) || period;
      await createManualPayableSnapshot({
        month: competenceMonth,
        name: form.name.trim(),
        amount,
        due_date: form.due_date,
        category: form.category.trim(),
        cost_center: form.cost_center.trim(),
        include_in_dashboard: form.include_in_dashboard,
        result_classification: resultClassification,
      });
      setShowForm(false);
      setForm({
        name: "",
        amount: "",
        due_date: "",
        category: "",
        cost_center: PAYABLES_MANUAL_CC_ADMIN,
        include_in_dashboard: true,
        result_classification: "",
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
    setEditValue(row.amount_final ?? 0);
    setEditDate(row.due_date.slice(0, 10));
    setEditIncludeInDashboard(row.include_in_dashboard !== false);
    setEditResultClassification(row.type === "MANUAL" ? (row.result_classification ?? "") : "");
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
      // Classificação no resultado só existe para manuais (backend devolve 400 nas demais).
      const editingRow = rows.find((x) => x.id === editingId);
      const isManual = editingRow?.type === "MANUAL";
      const updated = await updatePayableSnapshot(editingId, {
        amount_final: editValue,
        due_date: editDate,
        include_in_dashboard: editIncludeInDashboard,
        ...(isManual && editResultClassification ? { result_classification: editResultClassification } : {}),
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

  const tableProps = {
    canEdit,
    canDelete,
    canReconcile: canReconcileSnapshot,
    editingId,
    editSaving,
    editValue,
    editDate,
    editIncludeInDashboard,
    setEditIncludeInDashboard,
    editResultClassification,
    setEditResultClassification,
    activeProjectCostCenters,
    setEditValue,
    setEditDate,
    onSaveEdit: () => void saveEdit(),
    onCancelEdit: cancelEdit,
    onStartEdit: startEdit,
    onRegisterPayment: openRegisterPayment,
    onReversePayment: openReversePayment,
    onDeleteManual: openDeleteManual,
    selectedIds,
    selectableManualIds,
    onToggleSelect: toggleSelect,
    onToggleSelectAll: toggleSelectAllManual,
  };

  return (
    <div className="mx-auto max-w-full overflow-x-hidden space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Contas a pagar</h1>
          <p className="mt-1 text-sm text-slate-600">
            Snapshot mensal: depois de gerado, descrições e centros de custo só mudam ao{" "}
            <strong>regerar o mês</strong> (ação restrita a super usuário). Pagamentos parciais e estornos atualizam o
            valor pago acumulado nas linhas atuais.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!canEdit || periodMode === "ALL"}
            onClick={() => setImportOpen(true)}
            className="rounded-lg border border-indigo-200 bg-white px-4 py-2 text-sm font-medium text-indigo-800 shadow-sm hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Importar planilha
          </button>
          <button
            type="button"
            disabled={!canCreate || periodMode === "ALL"}
            onClick={() => setShowForm((s) => !s)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {showForm ? "Fechar" : "Adicionar despesa"}
          </button>
        </div>
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
        <Kpi label="Total (valor final)" value={money(totals.total)} />
        <Kpi
          label={periodMode === "MONTH" ? "Pago no período" : "Pago (acumulado)"}
          value={money(totals.pago)}
          accent="text-emerald-800"
        />
        <Kpi label="Em aberto" value={money(totals.emAberto)} accent="text-amber-800" />
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <PeriodFilter
            label="Mês (fluxo de caixa)"
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

          <label
            className="flex items-center gap-2 self-end pb-2 text-sm text-slate-700"
            title="Mostra só as despesas manuais que ainda não dizem como entram no Resultado da Empresa."
          >
            <input
              type="checkbox"
              checked={onlyUnclassifiedManual}
              onChange={(e) => setOnlyUnclassifiedManual(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            <span>
              Manuais sem classificação
              {unclassifiedManualCount > 0 ? (
                <span className="ml-1 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                  {unclassifiedManualCount}
                </span>
              ) : null}
            </span>
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
          {periodMode === "MONTH" && canReconcileSnapshot && (
            <button
              type="button"
              disabled={reconciling}
              onClick={() => void reconcileMonthSnapshot()}
              className="w-fit rounded-lg border border-sky-300 bg-sky-50 px-4 py-2 text-sm font-medium text-sky-900 hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
              title="Marca lançamentos automáticos sem origem atual como obsoletos (sem apagar histórico)."
            >
              {reconciling ? "Reconciliando…" : "Reconciliar snapshot"}
            </button>
          )}
        </div>
      </section>

      {showForm && canCreate && (
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
              onChange={(e) => {
                const costCenter = e.target.value;
                setForm((f) => ({
                  ...f,
                  cost_center: costCenter,
                  // «Custo direto do projeto» deixa de valer se o centro de custo não é mais um projeto ativo.
                  result_classification:
                    f.result_classification === "DIRETO" && !activeProjectCostCenters.has(costCenterKey(costCenter))
                      ? ""
                      : f.result_classification,
                }));
              }}
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
          <Field label="Entra no resultado como *">
            <select
              required
              value={form.result_classification}
              onChange={(e) =>
                setForm((f) => ({ ...f, result_classification: e.target.value as PayableResultClassification | "" }))
              }
              className="w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
            >
              <option value="">Selecione…</option>
              {resultClassificationOptions(form.cost_center, activeProjectCostCenters).map((c) => (
                <option key={c} value={c}>
                  {PAYABLE_RESULT_CLASSIFICATION_LABELS[c]}
                </option>
              ))}
            </select>
            <span className="text-xs font-normal text-slate-500">
              Usado no Resultado da Empresa (Indicadores). “Custo direto do projeto” aparece quando o centro de custo
              é um projeto ativo. Repasses, retenções e bloqueios não são custo: use “Não entra no resultado”.
            </span>
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
              disabled={saving}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Salvando…" : "Salvar despesa"}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500 shadow-sm">
          <div className="flex items-center justify-center gap-2">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
            <span>Carregando…</span>
          </div>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500 shadow-sm">
          Não foi possível carregar os dados.
        </div>
      ) : (
        <>
        {canDelete && selectedRows.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm">
            <span className="text-slate-800">
              <strong>{selectedRows.length}</strong>{" "}
              {selectedRows.length === 1 ? "lançamento manual selecionado" : "lançamentos manuais selecionados"} ·{" "}
              {formatBRL(selectedSummary.total)}
              {selectedSummary.paidCount > 0 ? (
                <span className="text-red-800">
                  {" "}
                  · {selectedSummary.paidCount} com pagamento registrado ({formatBRL(selectedSummary.paid)})
                </span>
              ) : null}
            </span>
            <span className="flex gap-2">
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Limpar seleção
              </button>
              <button
                type="button"
                onClick={() => setBulkDeleteOpen(true)}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
              >
                Excluir selecionados
              </button>
            </span>
          </div>
        ) : null}
        <PayablesSnapshotTable
          rows={sortedRows}
          headerSort={headerSort}
          emptyLabel={
            rows.length === 0
              ? (emptyMessage ?? "Nenhuma conta a pagar neste período.")
              : "Nenhum item para os filtros atuais."
          }
          {...tableProps}
        />
        </>
      )}

      <PayablesImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => void load()}
      />

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
              Valor final: <span className="font-medium tabular-nums text-slate-700">{money(actionModal.row.amount_final)}</span>
              {" · "}
              Pago: <span className="font-medium tabular-nums text-slate-700">{money(actionModal.row.amount_paid)}</span>
              {" · "}
              Saldo:{" "}
              <span
                className={`font-medium tabular-nums ${saldoClassName(
                  actionModal.row.amount_remaining,
                  actionModal.row.is_overpaid,
                )}`}
              >
                {money(actionModal.row.amount_remaining)}
              </span>
            </p>
            {modalOverpaymentPreview && modalOverpaymentPreview.overpaidAmount > 0.02 ? (
              <div
                className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
                role="status"
              >
                Pagamento acima do valor esperado. Adiantamento de{" "}
                <span className="font-semibold tabular-nums">{formatBRL(modalOverpaymentPreview.overpaidAmount)}</span>
                {modalOverpaymentPreview.newRemaining < -0.005 ? (
                  <>
                    {" "}
                    (saldo após pagamento:{" "}
                    <span className="font-semibold tabular-nums">{formatBRL(modalOverpaymentPreview.newRemaining)}</span>)
                  </>
                ) : null}
              </div>
            ) : null}
            {actionModal.mode === "register" ? (
              <div className="mt-3 rounded-lg border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-sm text-indigo-950">
                <p>
                  <span className="font-medium">Competência:</span>{" "}
                  {payableCompetenceLabel(actionModal.row.month)}
                </p>
                <p className="mt-1">
                  <span className="font-medium">Fluxo de caixa:</span>{" "}
                  {payableCashFlowLabelFromDate(modalPaymentDate)}
                </p>
                <p className="mt-2 text-xs text-indigo-800/90">
                  Este pagamento quitará uma obrigação de{" "}
                  <span className="font-semibold">{payableCompetenceLabel(actionModal.row.month)}</span>, mas será
                  registrado no fluxo de caixa de{" "}
                  <span className="font-semibold">{payableCashFlowLabelFromDate(modalPaymentDate)}</span>.
                </p>
              </div>
            ) : null}
            <div className="mt-4 space-y-3">
              {actionModal.mode === "register" ? (
                <label className="flex flex-col gap-1 text-sm">
                  <span className="font-medium text-slate-700">Data do pagamento *</span>
                  <input
                    type="date"
                    required
                    max={todayIsoLocal()}
                    value={modalPaymentDate}
                    onChange={(e) => setModalPaymentDate(e.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </label>
              ) : (
                <label className="flex flex-col gap-1 text-sm">
                  <span className="font-medium text-slate-700">Motivo do estorno (opcional)</span>
                  <input
                    value={modalReversalReason}
                    onChange={(e) => setModalReversalReason(e.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder="Ex.: lançamento duplicado"
                  />
                </label>
              )}
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

      {bulkDeleteOpen && selectedRows.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="bulk-del-modal-title"
            className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-lg"
          >
            <h3 id="bulk-del-modal-title" className="text-lg font-semibold text-slate-900">
              Excluir lançamentos manuais
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              Confirma a exclusão de <span className="font-medium text-slate-900">{selectedRows.length}</span>{" "}
              {selectedRows.length === 1 ? "lançamento manual" : "lançamentos manuais"}, somando{" "}
              <span className="font-medium tabular-nums text-slate-900">{formatBRL(selectedSummary.total)}</span>? Esta ação não
              pode ser desfeita.
            </p>
            {selectedSummary.paidCount > 0 ? (
              <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {selectedSummary.paidCount} {selectedSummary.paidCount === 1 ? "tem" : "têm"} pagamento registrado (
                {formatBRL(selectedSummary.paid)}). Os pagamentos serão excluídos junto.
              </p>
            ) : null}
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() => setBulkDeleteOpen(false)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() => void confirmBulkDelete()}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {bulkBusy ? "Excluindo…" : `Excluir ${selectedRows.length}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

type PayablesSnapshotTableProps = {
  rows: PayableSnapshotRow[];
  headerSort: TableSortHeaderProps;
  emptyLabel: string;
  canEdit: boolean;
  canDelete: boolean;
  canReconcile: boolean;
  editingId: string | null;
  editSaving: boolean;
  editValue: number;
  editDate: string;
  editIncludeInDashboard: boolean;
  setEditIncludeInDashboard: (v: boolean) => void;
  editResultClassification: PayableResultClassification | "";
  setEditResultClassification: (v: PayableResultClassification | "") => void;
  /** Nomes normalizados dos projetos ATIVOS — habilita «Custo direto do projeto». */
  activeProjectCostCenters: Set<string>;
  setEditValue: (n: number) => void;
  setEditDate: (d: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onStartEdit: (r: PayableSnapshotRow) => void;
  onRegisterPayment: (r: PayableSnapshotRow) => void;
  onReversePayment: (r: PayableSnapshotRow) => void;
  onDeleteManual: (r: PayableSnapshotRow) => void;
  /** Seleção para exclusão em massa (só lançamentos MANUAIS). */
  selectedIds: Set<string>;
  selectableManualIds: string[];
  onToggleSelect: (id: string) => void;
  onToggleSelectAll: () => void;
};

function PayablesSnapshotTable({
  rows,
  headerSort,
  emptyLabel,
  canEdit,
  canDelete,
  canReconcile,
  editingId,
  editSaving,
  editValue,
  editDate,
  editIncludeInDashboard,
  setEditIncludeInDashboard,
  editResultClassification,
  setEditResultClassification,
  activeProjectCostCenters,
  setEditValue,
  setEditDate,
  onSaveEdit,
  onCancelEdit,
  onStartEdit,
  onRegisterPayment,
  onReversePayment,
  onDeleteManual,
  selectedIds,
  selectableManualIds,
  onToggleSelect,
  onToggleSelectAll,
}: PayablesSnapshotTableProps) {
  const allManualSelected = selectableManualIds.length > 0 && selectableManualIds.every((id) => selectedIds.has(id));
  const someManualSelected = selectableManualIds.some((id) => selectedIds.has(id));
  return (
    <div className="overflow-x-auto w-full rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="min-w-[1320px] w-full table-fixed divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th className="w-[36px] px-2 py-2">
              {canDelete && selectableManualIds.length > 0 ? (
                <input
                  type="checkbox"
                  checked={allManualSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someManualSelected && !allManualSelected;
                  }}
                  onChange={onToggleSelectAll}
                  title="Selecionar todos os lançamentos manuais visíveis"
                  aria-label="Selecionar todos os lançamentos manuais visíveis"
                  className="h-4 w-4 rounded border-slate-300"
                />
              ) : null}
            </th>
            <SortableTh label="Tipo" column="type" className="w-[90px] px-2 py-2" {...headerSort} />
            <SortableTh label="Nome" column="name" className="w-[280px] px-2 py-2" {...headerSort} />
            <SortableTh label="Competência" column="month" className="w-[110px] px-2 py-2" {...headerSort} />
            <SortableTh label="Centro de custo" column="cost_center" className="w-[160px] px-2 py-2" {...headerSort} />
            <SortableTh
              label="Valor original"
              column="amount_original"
              className="w-[100px] px-2 py-2"
              align="right"
              {...headerSort}
            />
            <SortableTh
              label="Valor final"
              column="amount_final"
              className="w-[100px] px-2 py-2"
              align="right"
              {...headerSort}
            />
            <SortableTh label="Pago" column="amount_paid" className="w-[90px] px-2 py-2" align="right" {...headerSort} />
            <SortableTh label="Saldo" column="amount_remaining" className="w-[90px] px-2 py-2" align="right" {...headerSort} />
            <SortableTh label="Vencimento" column="due_date" className="w-[100px] px-2 py-2" align="right" {...headerSort} />
            <SortableTh label="Status" column="status" className="w-[90px] px-2 py-2" {...headerSort} />
            <SortableTh
              label="Último pagamento"
              column="last_payment"
              className="w-[120px] px-2 py-2"
              {...headerSort}
            />
            <th className="w-[220px] whitespace-nowrap px-2 py-2 text-right">Ações</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={13} className="px-3 py-8 text-center text-slate-500">
                {emptyLabel}
              </td>
            </tr>
          ) : (
            rows.map((r) => {
              const isEditing = editingId === r.id;
              const temPago = (r.amount_paid ?? 0) > 0.005;
              return (
                <tr key={r.id} className={selectedIds.has(r.id) ? "bg-red-50/60" : "hover:bg-slate-50/80"}>
                  <td className="px-2 py-1.5">
                    {canDelete && r.type === "MANUAL" ? (
                      <input
                        type="checkbox"
                        checked={selectedIds.has(r.id)}
                        onChange={() => onToggleSelect(r.id)}
                        aria-label={`Selecionar ${r.name}`}
                        className="h-4 w-4 rounded border-slate-300"
                      />
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-slate-700">{payableTipoLabel(r)}</td>
                  <td className="min-w-0 px-2 py-1.5 align-middle text-slate-900">
                    {/* Tooltip com o nome completo (obrigações de operação de antecipação
                        guardam o nome longo em observation; demais lançamentos usam o nome).
                        Endividamento: `name` é o Credor e `item_description` a Descrição. */}
                    <div
                      className="truncate max-w-[280px]"
                      title={
                        r.type === "ANTECIPACAO_OPERACAO"
                          ? r.observation ?? r.name
                          : r.item_description
                            ? `${r.name} — ${r.item_description}`
                            : r.name
                      }
                    >
                      {r.name}
                    </div>
                    {r.item_description ? (
                      <div className="truncate max-w-[280px] text-xs text-slate-500">
                        {r.item_description}
                      </div>
                    ) : null}
                    {r.type === "MANUAL" ? (
                      <div className="mt-0.5 leading-none">
                        <ResultClassificationBadge row={r} />
                      </div>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-slate-700">
                    {payableCompetenceLabel(r.month)}
                  </td>
                  <td className="min-w-0 px-2 py-1.5 align-middle text-slate-700">
                    <TruncatedCell value={r.cost_center} maxWidthClass="max-w-[160px]" />
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-slate-700">
                    <Money value={r.amount_original} />
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-right align-middle tabular-nums text-slate-900">
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
                        className="w-full min-w-[5.5rem] rounded border border-slate-300 px-1.5 py-0.5 text-right text-sm"
                      />
                    ) : (
                      money(r.amount_final)
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-slate-800">
                    <Money value={r.amount_paid} />
                  </td>
                  <td
                    className={`whitespace-nowrap px-2 py-1.5 text-right tabular-nums font-medium ${saldoClassName(
                      r.amount_remaining,
                      r.is_overpaid,
                    )}`}
                  >
                    {money(r.amount_remaining)}
                    {r.is_overpaid ? (
                      <span className="ml-1 text-[10px] font-normal text-amber-700">(adiant.)</span>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 align-middle text-slate-700">
                    {isEditing ? (
                      <input
                        type="date"
                        required
                        value={editDate}
                        onChange={(e) => setEditDate(e.target.value)}
                        className="w-full rounded border border-slate-300 px-1.5 py-0.5 text-sm"
                      />
                    ) : (
                      formatDateBr(r.due_date)
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${statusBadgeClass(
                        r.status,
                        r.is_overpaid,
                      )}`}
                    >
                      {r.status}
                      {r.is_overpaid ? "+" : ""}
                    </span>
                    {r.is_obsolete ? (
                      <span
                        className="ml-1 inline-flex rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-medium text-rose-700 ring-1 ring-rose-200"
                        title={r.obsolete_reason ?? "Origem removida"}
                      >
                        Origem removida
                      </span>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-slate-600">
                    {r.last_payment_date ? formatDateBr(r.last_payment_date) : "—"}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-right">
                    {isEditing ? (
                      <span className="inline-flex flex-col items-end gap-1 whitespace-nowrap">
                        <label className="flex items-center gap-1.5 text-[10px] text-slate-600">
                          <input
                            type="checkbox"
                            checked={editIncludeInDashboard}
                            onChange={(e) => setEditIncludeInDashboard(e.target.checked)}
                            className="h-3.5 w-3.5 rounded border-slate-300"
                          />
                          Dashboard
                        </label>
                        {r.type === "MANUAL" ? (
                          <select
                            value={editResultClassification}
                            onChange={(e) =>
                              setEditResultClassification(e.target.value as PayableResultClassification | "")
                            }
                            title="Entra no resultado como"
                            aria-label="Entra no resultado como"
                            className="max-w-[200px] rounded border border-slate-300 bg-white px-1 py-0.5 text-xs"
                          >
                            {!r.result_classification ? <option value="">Sem classificação</option> : null}
                            {resultClassificationOptions(
                              r.cost_center,
                              activeProjectCostCenters,
                              r.result_classification,
                            ).map((c) => (
                              <option key={c} value={c}>
                                {PAYABLE_RESULT_CLASSIFICATION_LABELS[c]}
                              </option>
                            ))}
                          </select>
                        ) : null}
                        <span className="inline-flex items-center gap-1">
                        <button
                          type="button"
                          disabled={!canEdit || editSaving}
                          onClick={onSaveEdit}
                          className="rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-800 hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {editSaving ? "Salvando…" : "Salvar"}
                        </button>
                        <button
                          type="button"
                          disabled={editSaving}
                          onClick={onCancelEdit}
                          className="rounded border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Cancelar
                        </button>
                        </span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center justify-end gap-x-1 whitespace-nowrap">
                        {!r.include_in_dashboard ? (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600" title="Excluído do Dashboard Financeiro">
                            Fora do dash.
                          </span>
                        ) : null}
                        <button
                          type="button"
                          disabled={!canEdit}
                          onClick={() => onStartEdit(r)}
                          className="rounded px-1.5 py-0.5 text-xs text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          disabled={!canEdit || editingId === r.id}
                          onClick={() => onRegisterPayment(r)}
                          className="rounded px-1.5 py-0.5 text-xs text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Registrar pagamento
                        </button>
                        <button
                          type="button"
                          disabled={!canEdit || !temPago || editingId === r.id}
                          onClick={() => onReversePayment(r)}
                          className="rounded px-1.5 py-0.5 text-xs text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Estornar
                        </button>
                        <button
                          type="button"
                          disabled={
                            editingId === r.id ||
                            (r.is_obsolete
                              ? !canReconcile
                              : !canDelete || (r.type !== "MANUAL" && r.type !== "VEHICLE"))
                          }
                          onClick={() => onDeleteManual(r)}
                          className="rounded px-1.5 py-0.5 text-xs text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                          title={
                            r.is_obsolete
                              ? "Excluir resíduo obsoleto (apenas sem pagamentos registrados)."
                              : r.type === "VEHICLE"
                                ? "Veículos no Contas a Pagar foi descontinuado: pode excluir quando não há pagamento ativo."
                                : undefined
                          }
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
