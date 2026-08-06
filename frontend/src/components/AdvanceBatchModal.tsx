import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isAxiosError } from "axios";
import {
  createAdvanceBatch,
  editAdvanceBatch,
  fetchAdvanceBatch,
  fetchEligibleInvoicesForBatch,
  cancelAdvanceBatch,
  deleteAdvanceBatchHard,
  updateAdvanceBatchDashboardInclusion,
  setAdvanceBatchActualReceived,
  type AdvanceBatch,
  type AdvanceBatchEligibleInvoice,
  type AdvanceBatchItem,
} from "@/services/receivableAdvanceBatches";
import { OperationInvoicesTable } from "@/components/OperationInvoicesTable";
import { fetchAdvanceInstitutions, type AdvanceInstitution } from "@/services/advanceInstitutions";
import { formatApiError } from "@/utils/apiError";
import { formatCurrencyField, formatCurrencyOrDash, normalizeCurrencyForApi } from "@/utils/currency";
import type { AdvanceBasis } from "@/services/receivableAdvanceBatches";

// Bases de antecipação (Bruto / Líquido / Líquido −10%). Compartilhadas por LEPTA e Daycoval:
// definem o valor antecipado sugerido por NF (mesma regra do backend LeptaOperationHandler).
const ADVANCE_BASIS_OPTIONS: { value: AdvanceBasis; label: string }[] = [
  { value: "BRUTO", label: "Bruto" },
  { value: "LIQUIDO", label: "Líquido" },
  { value: "LIQUIDO_MENOS_10", label: "Líquido −10%" },
];

/**
 * Valor antecipado de uma NF conforme a base — fonte única no front, com a mesma
 * regra base→valor do backend `LeptaOperationHandler.compute_item_advanced_amount`:
 * BRUTO → bruto; LIQUIDO → líquido; LIQUIDO_MENOS_10 → líquido − 10% do BRUTO
 * (a retenção de 10% incide sobre o bruto, não sobre o líquido).
 * Retorna o valor bruto (sem arredondar por item) — o arredondamento a centavos
 * fica com quem usa: o total previsto do LEPTA (arredonda a soma, como já fazia) e
 * o pré-preenchimento do Daycoval (formata o campo em 2 casas). Assim o LEPTA
 * permanece idêntico ao comportamento anterior.
 */
function advancedAmountForBasis(inv: AdvanceBatchEligibleInvoice, basis: AdvanceBasis): number {
  if (basis === "LIQUIDO") return inv.net_amount;
  if (basis === "LIQUIDO_MENOS_10") return inv.net_amount - inv.gross_amount * 0.1;
  return inv.gross_amount; // BRUTO (default seguro)
}

const STATUS_BR: Record<string, string> = {
  DRAFT: "Rascunho",
  OPEN: "Em aberto",
  SETTLED: "Liquidada",
  CANCELLED: "Cancelada",
};

/** Null-safe: delega ao util compartilhado (valor redigido → "—"). */
const formatBRL = formatCurrencyOrDash;

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function parseMoney(raw: string): number {
  return normalizeCurrencyForApi(raw);
}

function todayIso(): string {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
}

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  /** Visualizar borderô existente */
  viewBatchId?: string | null;
  /** Composição do repasse: filtra a tabela de NFs pelo mês de vencimento (YYYY-MM). */
  repasseCompetence?: string;
  /** Navegação operação → NF. */
  onOpenInvoice?: (item: AdvanceBatchItem) => void;
  /** Navegação operação → outra operação (regra 6): abre outro borderô. */
  onOpenOperation?: (batchId: string) => void;
};

export function AdvanceBatchModal({
  open,
  onClose,
  onCreated,
  viewBatchId,
  repasseCompetence,
  onOpenInvoice,
  onOpenOperation,
}: Props) {
  const isView = Boolean(viewBatchId);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invoices, setInvoices] = useState<AdvanceBatchEligibleInvoice[]>([]);
  // Busca tradicional: searchInput = texto digitado (não filtra); searchQuery = texto
  // efetivamente aplicado (só muda ao pressionar ENTER ou clicar em "Buscar").
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // Espelho de `selected` para o merge da busca preservar NFs já escolhidas (ex.: na edição).
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [detail, setDetail] = useState<AdvanceBatch | null>(null);
  // Edição de uma operação ATIVA: reusa o form de criação pré-preenchido a partir do detalhe.
  const [editing, setEditing] = useState(false);
  const [includeInDashboard, setIncludeInDashboard] = useState(true);
  const [dashboardSaving, setDashboardSaving] = useState(false);
  const [actualReceivedInput, setActualReceivedInput] = useState("");
  const [actualSaving, setActualSaving] = useState(false);

  const [institutions, setInstitutions] = useState<AdvanceInstitution[]>([]);
  const [institutionId, setInstitutionId] = useState("");
  const [bases, setBases] = useState<Record<string, AdvanceBasis>>({});
  const [manualAmounts, setManualAmounts] = useState<Record<string, string>>({});
  const [repasseEnabled, setRepasseEnabled] = useState(false);
  const [operationCode, setOperationCode] = useState("");
  const [operationType, setOperationType] = useState<"BORDERO" | "FACTORING" | "FIDC" | "OUTROS">("BORDERO");
  const [receiveDate, setReceiveDate] = useState(todayIso());
  const [receivedAmount, setReceivedAmount] = useState("");
  const [discountAmount, setDiscountAmount] = useState("");
  const [feeAmount, setFeeAmount] = useState("");
  const [observation, setObservation] = useState("");

  const loadEligible = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchEligibleInvoicesForBatch({
        search: searchQuery.trim() || undefined,
      });
      // Preserva NFs já selecionadas que não vieram na busca (ex.: NFs da operação em edição).
      setInvoices((prev) => {
        const byId = new Map(rows.map((r) => [r.id, r]));
        for (const p of prev) if (selectedRef.current.has(p.id) && !byId.has(p.id)) byId.set(p.id, p);
        return [...byId.values()];
      });
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível carregar NFs elegíveis.");
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  const loadDetail = useCallback(async () => {
    if (!viewBatchId) return;
    setLoading(true);
    setError(null);
    try {
      const b = await fetchAdvanceBatch(viewBatchId);
      setDetail(b);
      setIncludeInDashboard(b.include_in_dashboard !== false);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível carregar o borderô.");
    } finally {
      setLoading(false);
    }
  }, [viewBatchId]);

  // Reset ao FECHAR: o modal é reutilizado (mesma instância), então sem limpar o estado a
  // próxima abertura (nova antecipação / outra operação / edição) vazaria os dados da operação
  // anterior. Limpar no fechamento garante que a próxima abertura comece do zero.
  useEffect(() => {
    if (open) return;
    setEditing(false);
    setDetail(null);
    setError(null);
    setSelected(new Set());
    setBases({});
    setManualAmounts({});
    setSearchInput("");
    setSearchQuery("");
    setInstitutionId("");
    setOperationCode("");
    setOperationType("BORDERO");
    setReceiveDate(todayIso());
    setReceivedAmount("");
    setDiscountAmount("");
    setFeeAmount("");
    setObservation("");
    setRepasseEnabled(false);
    setActualReceivedInput("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (isView && !editing) void loadDetail();
    if (!isView || editing) void loadEligible();
    // Instituições são necessárias tanto para criar quanto para EDITAR (resolvem o perfil
    // LEPTA/Daycoval que define o payload) — sempre carregadas.
    void fetchAdvanceInstitutions({ only_active: true })
      .then(setInstitutions)
      .catch(() => setInstitutions([]));
  }, [open, isView, editing, loadDetail, loadEligible]);

  const selectedInstitution = useMemo(
    () => institutions.find((i) => i.id === institutionId) ?? null,
    [institutions, institutionId],
  );
  const profile = selectedInstitution?.operation_profile ?? null;
  const isLepta = profile === "LEPTA";
  const isDaycoval = profile === "DAYCOVAL";

  const grossTotal = useMemo(() => {
    let sum = 0;
    for (const id of selected) {
      const inv = invoices.find((r) => r.id === id);
      if (inv) sum += inv.gross_amount;
    }
    return Math.round(sum * 100) / 100;
  }, [selected, invoices]);

  // Objetivo 3: NFs selecionadas sobem para o topo; dentro de cada grupo mantém a ordem atual.
  const ordered = useMemo(() => {
    const sel: AdvanceBatchEligibleInvoice[] = [];
    const rest: AdvanceBatchEligibleInvoice[] = [];
    for (const inv of invoices) (selected.has(inv.id) ? sel : rest).push(inv);
    return { sel, rest };
  }, [invoices, selected]);

  // Objetivo 4 (Daycoval): refs dos campos "Valor antecipado" para auto-foco e ENTER→próxima.
  const amountInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const [pendingFocusId, setPendingFocusId] = useState<string | null>(null);

  useEffect(() => {
    if (!pendingFocusId) return;
    const el = amountInputRefs.current[pendingFocusId];
    if (el) {
      el.focus();
      el.select();
      setPendingFocusId(null);
    }
  }, [pendingFocusId, ordered]);

  function focusNextAmount(currentId: string) {
    const ids = ordered.sel.map((i) => i.id);
    const idx = ids.indexOf(currentId);
    for (let k = idx + 1; k < ids.length; k++) {
      const el = amountInputRefs.current[ids[k]];
      if (el) {
        el.focus();
        el.select();
        return;
      }
    }
    amountInputRefs.current[currentId]?.blur();
  }

  const daycovalPrevisto = useMemo(
    () => [...selected].reduce((acc, id) => acc + (parseMoney(manualAmounts[id] ?? "") || 0), 0),
    [selected, manualAmounts],
  );

  // LEPTA: soma dos valores antecipados por NF conforme a base escolhida (mesma regra
  // do backend). O líquido previsto = antecipados − deságio − tarifas (calculado, só leitura).
  const leptaAdvancedTotal = useMemo(() => {
    let sum = 0;
    for (const id of selected) {
      const inv = invoices.find((r) => r.id === id);
      if (!inv) continue;
      sum += advancedAmountForBasis(inv, bases[id] ?? "BRUTO");
    }
    return Math.round(sum * 100) / 100;
  }, [selected, invoices, bases]);

  const renderInvoiceRow = (inv: AdvanceBatchEligibleInvoice) => {
    const isSel = selected.has(inv.id);
    return (
      <tr key={inv.id} className={isSel ? "bg-indigo-50/40" : "hover:bg-slate-50/80"}>
        <td className="px-2 py-1.5">
          <input type="checkbox" checked={isSel} onChange={() => toggle(inv.id)} />
        </td>
        <td className="px-2 py-1.5">{inv.project_name ?? "—"}</td>
        <td className="px-2 py-1.5">{inv.client_name ?? "—"}</td>
        <td className="px-2 py-1.5 font-medium">
          {inv.number}
          {(inv.operations_count ?? 0) > 0 ? (
            <span
              className="mt-0.5 block text-[10px] font-normal text-amber-700"
              title={`Já utilizada em ${inv.operations_count} ${
                (inv.operations_count ?? 0) === 1 ? "operação" : "operações"
              }`}
            >
              {`Já usada em ${inv.operations_count} ${
                (inv.operations_count ?? 0) === 1 ? "operação" : "operações"
              }`}
              {(inv.operations?.length ?? 0) > 0
                ? ` • ${[...new Set((inv.operations ?? []).map((o) => o.institution))].join(" • ")}`
                : ""}
            </span>
          ) : null}
        </td>
        <td className="px-2 py-1.5 whitespace-nowrap">{formatDateBr(inv.issue_date)}</td>
        <td className="px-2 py-1.5 whitespace-nowrap">{formatDateBr(inv.due_date)}</td>
        <td className="px-2 py-1.5 text-right tabular-nums">{formatBRL(inv.gross_amount)}</td>
        <td className="px-2 py-1.5 text-xs">{inv.status}</td>
        {isLepta || isDaycoval ? (
          <td className="px-2 py-1.5">
            <select
              value={bases[inv.id] ?? "BRUTO"}
              disabled={!isSel}
              onChange={(e) => handleBasisChange(inv.id, e.target.value as AdvanceBasis)}
              className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            >
              {ADVANCE_BASIS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </td>
        ) : null}
        {isDaycoval ? (
          <td className="px-2 py-1.5 text-right">
            <input
              ref={(el) => {
                amountInputRefs.current[inv.id] = el;
              }}
              value={manualAmounts[inv.id] ?? ""}
              disabled={!isSel}
              onChange={(e) => setManualAmounts((prev) => ({ ...prev, [inv.id]: e.target.value }))}
              onKeyDown={(e) => {
                // Objetivo 4: ENTER confirma o valor e pula para a próxima NF selecionada.
                if (e.key === "Enter") {
                  e.preventDefault();
                  focusNextAmount(inv.id);
                }
              }}
              placeholder="0,00"
              inputMode="decimal"
              className="w-28 rounded border border-slate-300 px-2 py-1 text-right text-xs disabled:opacity-50"
            />
          </td>
        ) : null}
      </tr>
    );
  };

  const receivedNum = parseMoney(receivedAmount);
  const discountNum = parseMoney(discountAmount);
  const feeNum = parseMoney(feeAmount);
  const discountPct = grossTotal > 0.005 ? ((discountNum / grossTotal) * 100).toFixed(2) : "—";
  // LEPTA: líquido previsto creditado = antecipados − deságio − tarifas.
  const leptaLiquido = Math.round((leptaAdvancedTotal - discountNum - feeNum) * 100) / 100;

  /** Pré-preenche o "Valor antecipado" (Daycoval) a partir da base — valor inicial sugerido,
   *  reutilizando a mesma regra do LEPTA. O campo permanece editável. */
  function suggestDaycovalAmount(id: string, basis: AdvanceBasis) {
    const inv = invoices.find((r) => r.id === id);
    if (!inv) return;
    setManualAmounts((prev) => ({ ...prev, [id]: formatCurrencyField(advancedAmountForBasis(inv, basis)) }));
  }

  /** Troca da base por NF (LEPTA e Daycoval). No Daycoval, re-sugere o valor antecipado. */
  function handleBasisChange(id: string, basis: AdvanceBasis) {
    setBases((prev) => ({ ...prev, [id]: basis }));
    if (isDaycoval) suggestDaycovalAmount(id, basis);
  }

  function toggle(id: string) {
    const isAdding = !selected.has(id);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    // Objetivo 4 + pré-preenchimento: ao selecionar (Daycoval), a NF sobe, o valor
    // antecipado já vem sugerido pela base e o cursor entra no campo (pronto para editar).
    if (isAdding && isDaycoval) {
      suggestDaycovalAmount(id, bases[id] ?? "BRUTO");
      setPendingFocusId(id);
    }
  }

  function startEdit() {
    if (!detail) return;
    setInstitutionId(detail.institution_id ?? "");
    setOperationType((detail.operation_type ?? "BORDERO") as "BORDERO" | "FACTORING" | "FIDC" | "OUTROS");
    setOperationCode(detail.operation_code ?? "");
    setReceiveDate(detail.receive_date);
    setDiscountAmount(detail.discount_amount ? formatCurrencyField(detail.discount_amount) : "");
    setFeeAmount(detail.fee_amount ? formatCurrencyField(detail.fee_amount) : "");
    setReceivedAmount(detail.received_amount ? formatCurrencyField(detail.received_amount) : "");
    setRepasseEnabled(Boolean(detail.repasse_enabled));
    setObservation(detail.observation ?? "");
    const sel = new Set<string>();
    const nextBases: Record<string, AdvanceBasis> = {};
    const nextManual: Record<string, string> = {};
    const seeded: AdvanceBatchEligibleInvoice[] = [];
    for (const it of detail.items) {
      sel.add(it.invoice_id);
      if (it.advance_basis) nextBases[it.invoice_id] = it.advance_basis as AdvanceBasis;
      if (it.advanced_amount != null) nextManual[it.invoice_id] = formatCurrencyField(it.advanced_amount);
      seeded.push({
        id: it.invoice_id,
        project_id: "",
        project_name: it.project_name,
        number: it.invoice_number ?? "",
        client_name: it.client_name,
        issue_date: it.issue_date ?? "",
        due_date: it.due_date ?? "",
        gross_amount: it.gross_amount ?? it.invoice_amount ?? 0,
        net_amount: it.net_amount ?? 0,
        status: it.invoice_status ?? "ANTECIPADA",
      });
    }
    setSelected(sel);
    setBases(nextBases);
    setManualAmounts(nextManual);
    // Garante que as NFs da operação apareçam na lista (mesmo que já antecipadas).
    setInvoices((prev) => {
      const byId = new Map(prev.map((r) => [r.id, r]));
      for (const s of seeded) if (!byId.has(s.id)) byId.set(s.id, s);
      return [...byId.values()];
    });
    setError(null);
    setEditing(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (selected.size < 1) {
      setError("Selecione ao menos 1 nota fiscal.");
      return;
    }
    if (!institutionId) {
      setError("Selecione a instituição.");
      return;
    }
    if (!receiveDate) {
      setError("Informe a data de recebimento.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      // Editar reusa o MESMO payload da criação; o backend reverte → aplica → reaplica.
      const submitBatch =
        editing && detail
          ? (p: Parameters<typeof createAdvanceBatch>[0]) => editAdvanceBatch(detail.id, p)
          : createAdvanceBatch;
      const common = {
        operation_type: operationType,
        operation_code: operationCode.trim() || null,
        institution_id: institutionId,
        receive_date: receiveDate,
        // Devolução no nível da operação foi removida: o vencimento perante a instituição é
        // o de cada NF (invoice.due_date), controlado na aba Liquidação. O backend usa a data
        // de recebimento internamente para a coluna repayment_date (compat).
        repayment_date: null,
        observation: observation.trim() || null,
      };
      if (isLepta) {
        // Fluxo Lepta: base por NF + deságio + tarifas + repasse. O líquido recebido é
        // calculado no backend (antecipados − deságio − tarifas) — o front apenas coleta.
        await submitBatch({
          ...common,
          discount_amount: discountNum,
          fee_amount: feeNum,
          repasse_enabled: repasseEnabled,
          items: [...selected].map((id) => ({ invoice_id: id, advance_basis: bases[id] ?? "BRUTO" })),
        });
      } else if (isDaycoval) {
        // Fluxo Daycoval: valor antecipado informado manualmente por NF.
        const items = [...selected].map((id) => ({
          invoice_id: id,
          advance_basis: "MANUAL" as AdvanceBasis,
          advanced_amount: parseMoney(manualAmounts[id] ?? ""),
        }));
        if (items.some((it) => !(it.advanced_amount > 0))) {
          setError("Informe o valor antecipado (> 0) de cada NF selecionada.");
          setSaving(false);
          return;
        }
        await submitBatch({ ...common, items });
      } else {
        await submitBatch({
          ...common,
          received_amount: receivedNum,
          discount_amount: discountNum,
          fee_amount: feeNum,
          invoice_ids: [...selected],
        });
      }
      onCreated();
      onClose();
    } catch (err) {
      setError(
        isAxiosError(err)
          ? formatApiError(err)
          : editing
            ? "Não foi possível salvar a edição."
            : "Não foi possível criar o borderô.",
      );
    } finally {
      setSaving(false);
    }
  }

  function operationLabel(): string {
    if (!detail) return "";
    // Identificador operacional oficial = número interno do SGC.
    if (detail.sgc_number != null) return String(detail.sgc_number);
    if ((detail.batch_number ?? "").trim()) return detail.batch_number;
    return `ANTECIPACAO-${detail.id.slice(0, 8)}`;
  }

  async function handleSaveDashboardInclusion() {
    if (!detail) return;
    setDashboardSaving(true);
    setError(null);
    try {
      const updated = await updateAdvanceBatchDashboardInclusion(detail.id, includeInDashboard);
      setDetail(updated);
      onCreated();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar.");
    } finally {
      setDashboardSaving(false);
    }
  }

  async function handleSaveActualReceived() {
    if (!detail) return;
    const val = parseMoney(actualReceivedInput);
    if (!(val >= 0)) {
      setError("Informe um valor recebido válido.");
      return;
    }
    setActualSaving(true);
    setError(null);
    try {
      const updated = await setAdvanceBatchActualReceived(detail.id, val);
      setDetail(updated);
      onCreated();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar o valor recebido.");
    } finally {
      setActualSaving(false);
    }
  }

  async function handleCancelBatch() {
    if (!detail) return;
    if (detail.status !== "OPEN") return;
    const ok = window.confirm(
      `Cancelar a operação ${operationLabel()}?\n\n` +
        `Isso remove o vínculo das NFs e exclui as despesas automáticas (se não houver pagamento nelas).`,
    );
    if (!ok) return;
    setSaving(true);
    setError(null);
    try {
      await cancelAdvanceBatch(detail.id);
      onCreated();
      onClose();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível cancelar o borderô.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteHard() {
    if (!detail) return;
    if (detail.status !== "CANCELLED") {
      setError("Para excluir definitivamente, primeiro cancele o borderô.");
      return;
    }
    const ok = window.confirm(
      `EXCLUIR definitivamente a operação ${operationLabel()}?\n\n` +
        `Esta ação é irreversível e indicada apenas para correção de erro.\n` +
        `O sistema bloqueará se houver pagamentos nas despesas do borderô.`,
    );
    if (!ok) return;
    setSaving(true);
    setError(null);
    try {
      await deleteAdvanceBatchHard(detail.id);
      onCreated();
      onClose();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível excluir o borderô.");
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        className="my-4 w-full max-w-5xl rounded-xl border border-slate-200 bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">
            {editing
              ? `Editar operação SGC ${detail?.sgc_number ?? ""}`
              : isView
                ? `Operação SGC ${detail?.sgc_number ?? ""}`
                : "Nova antecipação"}
          </h2>
          <button type="button" onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900">
            Fechar
          </button>
        </div>

        {error ? (
          <div className="mx-5 mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {isView && detail && !editing ? (
          <div className="space-y-4 p-5 text-sm">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                disabled={saving || detail.status !== "OPEN"}
                onClick={startEdit}
                className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
                title="Reabre a operação para edição (reverte, aplica as mudanças e reaplica). Bloqueado se houver pagamento nas despesas."
              >
                Editar
              </button>
              <button
                type="button"
                disabled={saving || detail.status !== "OPEN"}
                onClick={() => void handleCancelBatch()}
                className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? "Cancelando…" : "Cancelar borderô"}
              </button>
              <button
                type="button"
                disabled={saving || detail.status !== "CANCELLED"}
                onClick={() => void handleDeleteHard()}
                className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-900 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? "Excluindo…" : "Excluir definitivamente"}
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <p>
                <span className="text-slate-500">Operação SGC:</span>{" "}
                <span className="font-semibold">{detail.sgc_number ?? "—"}</span>
              </p>
              <p>
                <span className="text-slate-500">Número da instituição:</span>{" "}
                {detail.operation_code?.trim() ? detail.operation_code : "—"}
              </p>
              <p>
                <span className="text-slate-500">Instituição:</span> {detail.institution}
              </p>
              <p>
                <span className="text-slate-500">Perfil:</span> {detail.institution_profile ?? "—"}
              </p>
              <p>
                <span className="text-slate-500">Status:</span> {STATUS_BR[detail.status] ?? detail.status}
              </p>
              <p>
                <span className="text-slate-500">NFs:</span> {detail.items.length}
              </p>
              <p>
                <span className="text-slate-500">Criação:</span> {formatDateBr(detail.created_at)}
              </p>
              <p>
                <span className="text-slate-500">Confirmação:</span>{" "}
                {detail.confirmed_at ? formatDateBr(detail.confirmed_at) : "—"}
              </p>
              <p>
                <span className="text-slate-500">Recebimento:</span> {formatDateBr(detail.receive_date)}
              </p>
              <p>
                <span className="text-slate-500">Bruto:</span> {formatBRL(detail.gross_amount)}
              </p>
              <p>
                <span className="text-slate-500">Líquido:</span> {formatBRL(detail.received_amount)}
              </p>
              {detail.expected_amount != null ? (
                <>
                  <p>
                    <span className="text-slate-500">Previsto:</span> {formatBRL(detail.expected_amount)}
                  </p>
                  <p>
                    <span className="text-slate-500">Realizado:</span>{" "}
                    {detail.actual_received_amount != null ? formatBRL(detail.actual_received_amount) : "—"}
                  </p>
                  <p>
                    <span className="text-slate-500">Diferença:</span>{" "}
                    {detail.actual_received_amount != null
                      ? formatBRL(detail.actual_received_amount - detail.expected_amount)
                      : "—"}
                  </p>
                </>
              ) : null}
              {detail.repasse_amount != null ? (
                <p>
                  <span className="text-slate-500">Repasse:</span> {formatBRL(detail.repasse_amount)}
                </p>
              ) : null}
              {detail.expected_amount == null ? (
                <>
                  <p>
                    <span className="text-slate-500">Deságio:</span> {formatBRL(detail.discount_amount)}
                    {detail.discount_percent != null ? ` (${detail.discount_percent}%)` : null}
                  </p>
                  <p>
                    <span className="text-slate-500">Tarifas:</span> {formatBRL(detail.fee_amount)}
                  </p>
                </>
              ) : null}
            </div>
            {/* Indicador informativo: custo efetivo de antecipar as NFs (Daycoval). */}
            {detail.institution_profile === "DAYCOVAL" && detail.finance_cost_percent != null ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
                  Custo efetivo da antecipação (informativo)
                </p>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-4">
                  <div>
                    <dt className="text-[11px] text-amber-700/80">Total líquido das NFs</dt>
                    <dd className="font-semibold tabular-nums text-slate-800">
                      {formatBRL(detail.invoices_net_total ?? 0)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] text-amber-700/80">Valor efetivamente recebido</dt>
                    <dd className="font-semibold tabular-nums text-slate-800">
                      {formatBRL(detail.received_amount)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] text-amber-700/80">Custo financeiro</dt>
                    <dd className="font-semibold tabular-nums text-amber-900">
                      {formatBRL(detail.finance_cost_amount ?? 0)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] text-amber-700/80">Taxa efetiva da antecipação</dt>
                    <dd className="font-semibold tabular-nums text-amber-900">
                      {detail.finance_cost_percent.toLocaleString("pt-BR", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                      %
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}
            {detail.observation ? (
              <p className="text-slate-600">
                <span className="font-medium">Obs.:</span> {detail.observation}
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={includeInDashboard}
                  onChange={(e) => setIncludeInDashboard(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300"
                />
                <span className="text-slate-700">Considerar no Dashboard Financeiro</span>
              </label>
              {includeInDashboard !== (detail.include_in_dashboard !== false) ? (
                <button
                  type="button"
                  disabled={dashboardSaving}
                  onClick={() => void handleSaveDashboardInclusion()}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {dashboardSaving ? "Salvando…" : "Salvar participação no dashboard"}
                </button>
              ) : null}
            </div>
            {detail.expected_amount != null && detail.status === "OPEN" ? (
              <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <label className="flex flex-col gap-1 text-sm">
                  <span className="font-medium text-slate-700">Valor efetivamente recebido (realizado)</span>
                  <input
                    value={actualReceivedInput}
                    onChange={(e) => setActualReceivedInput(e.target.value)}
                    placeholder={formatBRL(detail.received_amount)}
                    inputMode="decimal"
                    className="w-40 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </label>
                <button
                  type="button"
                  disabled={actualSaving || !actualReceivedInput.trim()}
                  onClick={() => void handleSaveActualReceived()}
                  className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {actualSaving ? "Salvando…" : "Salvar realizado"}
                </button>
                <span className="text-[11px] text-slate-500">
                  O previsto é preservado para auditoria; o Dashboard passa a refletir o realizado.
                </span>
              </div>
            ) : null}
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                {repasseCompetence
                  ? `NFs do repasse (vencimento ${repasseCompetence})`
                  : `Notas fiscais da operação (${detail.items.length})`}
              </p>
              <OperationInvoicesTable
                items={detail.items}
                dueCompetenceFilter={repasseCompetence}
                onOpenInvoice={onOpenInvoice}
                currentBatchId={detail.id}
                onOpenOperation={onOpenOperation}
              />
            </div>
          </div>
        ) : loading ? (
          <p className="p-8 text-center text-sm text-slate-500">Carregando…</p>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 p-5">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Tipo</span>
                <select
                  value={operationType}
                  onChange={(e) => setOperationType(e.target.value as typeof operationType)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                >
                  <option value="BORDERO">Borderô</option>
                  <option value="FACTORING">Factoring</option>
                  <option value="FIDC">FIDC</option>
                  <option value="OUTROS">Outros</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Número / Identificação da instituição</span>
                <input
                  value={operationCode}
                  onChange={(e) => setOperationCode(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="Ex.: BT-2026-015, Borderô 5932 (opcional)"
                />
                <span className="text-[11px] text-slate-500">
                  Código fornecido pela instituição. O número interno da operação (SGC) é gerado
                  automaticamente.
                </span>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Instituição *</span>
                <select
                  required
                  value={institutionId}
                  onChange={(e) => setInstitutionId(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                >
                  <option value="">Selecione…</option>
                  {institutions.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name}
                    </option>
                  ))}
                </select>
                {selectedInstitution ? (
                  <span className="text-[11px] text-slate-500">
                    Fluxo: {selectedInstitution.operation_profile}
                  </span>
                ) : null}
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Data recebimento *</span>
                <input
                  type="date"
                  required
                  value={receiveDate}
                  onChange={(e) => setReceiveDate(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              {/* Devolução no nível da operação REMOVIDA: o vencimento perante a instituição é
                  o de cada NF (controlado na aba Liquidação de NFs). */}
              {isDaycoval ? (
                <p className="text-[11px] text-slate-500 sm:col-span-2 lg:col-span-3">
                  Informe o valor antecipado de cada NF na tabela abaixo. Ao confirmar, as NFs são
                  marcadas como recebidas; o previsto é a soma dos valores informados e o realizado
                  pode ser editado depois.
                </p>
              ) : (
                <>
                  {isLepta ? (
                    // LEPTA: líquido recebido é calculado (antecipados − deságio − tarifas),
                    // exibido apenas como leitura. O usuário não digita o líquido.
                    <label className="flex flex-col gap-1 text-sm">
                      <span className="font-medium text-slate-700">Valor líquido recebido (calculado)</span>
                      <input
                        value={formatBRL(leptaLiquido)}
                        readOnly
                        tabIndex={-1}
                        className="cursor-default rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700"
                      />
                      <span className="text-[11px] text-slate-500">= antecipados − deságio − tarifas</span>
                    </label>
                  ) : (
                    <label className="flex flex-col gap-1 text-sm">
                      <span className="font-medium text-slate-700">Valor líquido recebido *</span>
                      <input
                        value={receivedAmount}
                        onChange={(e) => setReceivedAmount(e.target.value)}
                        className="rounded-lg border border-slate-300 px-3 py-2"
                        placeholder="0,00"
                        inputMode="decimal"
                      />
                    </label>
                  )}
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="font-medium text-slate-700">Deságio</span>
                    <input
                      value={discountAmount}
                      onChange={(e) => setDiscountAmount(e.target.value)}
                      className="rounded-lg border border-slate-300 px-3 py-2"
                      placeholder="0,00"
                      inputMode="decimal"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="font-medium text-slate-700">Tarifas bancárias</span>
                    <input
                      value={feeAmount}
                      onChange={(e) => setFeeAmount(e.target.value)}
                      className="rounded-lg border border-slate-300 px-3 py-2"
                      placeholder="0,00"
                      inputMode="decimal"
                    />
                  </label>
                  {isLepta ? (
                    <label className="flex items-start gap-2 text-sm sm:col-span-2 lg:col-span-3">
                      <input
                        type="checkbox"
                        checked={repasseEnabled}
                        onChange={(e) => setRepasseEnabled(e.target.checked)}
                        className="mt-0.5 h-4 w-4 rounded border-slate-300"
                      />
                      <span className="text-slate-700">
                        Reter 7% (Repasse não apropriado)
                        <span className="block text-[11px] text-slate-500">
                          Gera lançamento(s) em Contas a Pagar por mês de vencimento das NFs.
                        </span>
                      </span>
                    </label>
                  ) : null}
                </>
              )}
              <label className="sm:col-span-2 lg:col-span-3 flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Observações</span>
                <textarea
                  value={observation}
                  onChange={(e) => setObservation(e.target.value)}
                  rows={2}
                  className="resize-y rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
            </div>

            {/* Objetivo 5: resumo operacional em tempo real conforme a seleção das NFs. */}
            <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 px-4 py-3 text-sm text-indigo-950">
              <p className="mb-2 text-base font-semibold">
                {selected.size} NF{selected.size === 1 ? "" : "(s)"}
              </p>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3 lg:grid-cols-4">
                {isDaycoval ? (
                  <>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Bruto</dt>
                      <dd className="font-semibold tabular-nums">{formatBRL(grossTotal)}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Previsto</dt>
                      <dd className="font-semibold tabular-nums">{formatBRL(daycovalPrevisto)}</dd>
                    </div>
                  </>
                ) : isLepta ? (
                  <>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Bruto (antecipado)</dt>
                      <dd className="font-semibold tabular-nums">{formatBRL(leptaAdvancedTotal)}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">(−) Deságio</dt>
                      <dd className="font-semibold tabular-nums">{formatBRL(discountNum)}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">(−) Tarifas</dt>
                      <dd className="font-semibold tabular-nums">{formatBRL(feeNum)}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">(=) Líquido previsto</dt>
                      <dd className="font-semibold tabular-nums text-indigo-900">{formatBRL(leptaLiquido)}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Repasse 7%</dt>
                      <dd className="text-indigo-700">{repasseEnabled ? "na confirmação" : "—"}</dd>
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Bruto</dt>
                      <dd className="font-semibold tabular-nums">{formatBRL(grossTotal)}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Líquido</dt>
                      <dd className="font-semibold tabular-nums">{formatBRL(receivedNum)}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Deságio</dt>
                      <dd className="font-semibold tabular-nums">{discountPct !== "—" ? `${discountPct}%` : "—"}</dd>
                    </div>
                  </>
                )}
                <div>
                  <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Instituição</dt>
                  <dd className="truncate font-medium" title={selectedInstitution?.name ?? undefined}>
                    {selectedInstitution?.name ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Operação SGC</dt>
                  <dd className="font-medium text-indigo-700">Automático (ao salvar)</dd>
                </div>
                <div>
                  <dt className="text-[11px] uppercase tracking-wide text-indigo-700/70">Número da instituição</dt>
                  <dd className="truncate font-medium" title={operationCode.trim() || undefined}>
                    {operationCode.trim() || "—"}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="flex flex-wrap gap-2">
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => {
                  // A busca só é aplicada ao confirmar (ENTER); digitar não filtra a lista.
                  if (e.key === "Enter") {
                    e.preventDefault();
                    setSearchQuery(searchInput);
                  }
                }}
                placeholder="Buscar NF, cliente ou projeto… (ENTER para buscar)"
                className="min-w-[240px] flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={() => setSearchQuery(searchInput)}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
              >
                Buscar
              </button>
            </div>

            <div className="max-h-[320px] overflow-x-auto overflow-y-auto rounded-lg border border-slate-200">
              <table className="min-w-[720px] w-full divide-y divide-slate-200 text-sm">
                <thead className="sticky top-0 bg-slate-50 text-left text-xs font-semibold uppercase text-slate-600">
                  <tr>
                    <th className="w-10 px-2 py-2" />
                    <th className="px-2 py-2">Projeto</th>
                    <th className="px-2 py-2">Cliente</th>
                    <th className="px-2 py-2">Nº NF</th>
                    <th className="px-2 py-2">Emissão</th>
                    <th className="px-2 py-2">Vencimento</th>
                    <th className="px-2 py-2 text-right">Bruto</th>
                    <th className="px-2 py-2">Status</th>
                    {isLepta || isDaycoval ? <th className="px-2 py-2">Base antecipação</th> : null}
                    {isDaycoval ? <th className="px-2 py-2 text-right">Valor antecipado</th> : null}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {invoices.length === 0 ? (
                    <tr>
                      <td colSpan={isDaycoval ? 10 : isLepta ? 9 : 8} className="px-3 py-8 text-center text-slate-500">
                        Nenhuma NF elegível encontrada.
                      </td>
                    </tr>
                  ) : (
                    <>
                      {ordered.sel.map(renderInvoiceRow)}
                      {ordered.sel.length > 0 && ordered.rest.length > 0 ? (
                        <tr className="bg-slate-100/80">
                          <td
                            colSpan={isLepta || isDaycoval ? 9 : 8}
                            className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500"
                          >
                            Não selecionadas
                          </td>
                        </tr>
                      ) : null}
                      {ordered.rest.map(renderInvoiceRow)}
                    </>
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end gap-2 border-t border-slate-200 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={saving || selected.size < 1}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Salvando…" : editing ? "Salvar edição" : "Criar borderô"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
