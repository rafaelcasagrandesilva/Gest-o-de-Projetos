import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import {
  activateProject,
  contractValidityInfo,
  createProjectAdditive,
  deactivateProject,
  deleteProjectAdditive,
  deleteProjectDocument,
  downloadProjectDocument,
  getProjectDetail,
  listProjectDocuments,
  updateProjectAdditive,
  updateProjectContract,
  updateProjectGeneral,
  uploadProjectDocument,
  PROJECT_DOCUMENT_CATEGORIES,
  type ProjectContractAdditive,
  type ProjectDocument,
  type ProjectDocumentCategory,
} from "@/services/projects";
import { fetchCostCenters } from "@/services/employees";
import { CostCenterCombo } from "@/components/CostCenterCombo";
import { usePermission } from "@/hooks/usePermission";
import { formatApiError } from "@/utils/apiError";
import { formatCurrencyField, formatCurrencyOrDash, normalizeCurrencyForApi } from "@/utils/currency";

type DetailTab = "geral" | "contrato" | "documentos" | "historico";

const CATEGORY_LABEL: Record<ProjectDocumentCategory, string> = Object.fromEntries(
  PROJECT_DOCUMENT_CATEGORIES.map((c) => [c.value, c.label]),
) as Record<ProjectDocumentCategory, string>;

type Props = {
  open: boolean;
  projectId: string | null;
  projectName?: string;
  canEdit: boolean;
  onClose: () => void;
  /** Chamado após salvar algo (para o pai recarregar a lista, se quiser). */
  onSaved?: () => void;
};

/** Valor para input (pt-BR, sem R$) e valor de exibição — fonte única (utils/currency). */
const moneyToInput = formatCurrencyField;
const formatBRL = formatCurrencyOrDash;

/** Vigência atual (ISO yyyy-mm-dd) = início + prazo original + Σ prazos dos aditivos (meses). */
function computeValidityIso(startIso: string, baseMonths: number | null, additiveMonths: number): string {
  if (!startIso || baseMonths == null || !Number.isFinite(baseMonths)) return "";
  const [y, m, d] = startIso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return "";
  const total = m - 1 + baseMonths + additiveMonths;
  const year = y + Math.floor(total / 12);
  const month = ((total % 12) + 12) % 12;
  const lastDay = new Date(year, month + 1, 0).getDate();
  const day = Math.min(d, lastDay);
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Data final derivada = início (ISO yyyy-mm-dd) + N meses. Retorna dd/mm/aaaa ou "—". */
function computeEndDateBr(startIso: string, months: number | null): string {
  if (!startIso || months == null || !Number.isFinite(months)) return "—";
  const [y, m, d] = startIso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return "—";
  const total = m - 1 + months;
  const year = y + Math.floor(total / 12);
  const month = ((total % 12) + 12) % 12; // 0-based
  const lastDay = new Date(year, month + 1, 0).getDate();
  const day = Math.min(d, lastDay);
  return `${String(day).padStart(2, "0")}/${String(month + 1).padStart(2, "0")}/${year}`;
}

type AdditiveDraft = { additive_date: string; additive_value: string; additive_duration: string };

function draftFrom(a: ProjectContractAdditive): AdditiveDraft {
  return {
    additive_date: a.additive_date ?? "",
    additive_value: moneyToInput(a.additive_value),
    additive_duration: a.additive_duration ?? "",
  };
}

export function ProjectDetailsModal({ open, projectId, projectName, canEdit, onClose, onSaved }: Props) {
  const canViewDocs = usePermission("projects.documents.view");
  const canUploadDocs = usePermission("projects.documents.upload");
  const canDeleteDocs = usePermission("projects.documents.delete");

  const [activeTab, setActiveTab] = useState<DetailTab>("geral");
  const [loading, setLoading] = useState(false);
  const [savingContract, setSavingContract] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Aba Geral (editável).
  const [projName, setProjName] = useState("");
  const [projDescription, setProjDescription] = useState("");
  const [projCostCenter, setProjCostCenter] = useState("");
  const [costCenterOptions, setCostCenterOptions] = useState<string[]>([]);
  const [projActive, setProjActive] = useState(true);
  const [projActiveOriginal, setProjActiveOriginal] = useState(true);
  const [savingGeneral, setSavingGeneral] = useState(false);

  // Aba Documentos.
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docCategory, setDocCategory] = useState<ProjectDocumentCategory>("CONTRATO");
  const [docTitle, setDocTitle] = useState("");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [busyDocId, setBusyDocId] = useState<string | null>(null);

  const [contractNumber, setContractNumber] = useState("");
  const [contractValue, setContractValue] = useState("");
  const [contractStartDate, setContractStartDate] = useState("");
  const [contractDuration, setContractDuration] = useState("");
  const [buyerName, setBuyerName] = useState("");
  const [buyerPhone, setBuyerPhone] = useState("");
  const [buyerEmail, setBuyerEmail] = useState("");
  const [managerName, setManagerName] = useState("");
  const [managerPhone, setManagerPhone] = useState("");
  const [managerEmail, setManagerEmail] = useState("");

  const [additives, setAdditives] = useState<ProjectContractAdditive[]>([]);
  const [drafts, setDrafts] = useState<Record<string, AdditiveDraft>>({});
  const [busyAdditiveId, setBusyAdditiveId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const d = await getProjectDetail(projectId);
      setProjName(d.name ?? "");
      setProjDescription(d.description ?? "");
      setProjCostCenter(d.cost_center ?? "");
      setProjActive(d.is_active);
      setProjActiveOriginal(d.is_active);
      setContractNumber(d.contract_number ?? "");
      setContractValue(moneyToInput(d.contract_value));
      setContractStartDate(d.contract_start_date ?? "");
      setContractDuration(d.contract_duration != null ? String(d.contract_duration) : "");
      setBuyerName(d.buyer_name ?? "");
      setBuyerPhone(d.buyer_phone ?? "");
      setBuyerEmail(d.buyer_email ?? "");
      setManagerName(d.manager_name ?? "");
      setManagerPhone(d.manager_phone ?? "");
      setManagerEmail(d.manager_email ?? "");
      setAdditives(d.additives);
      setDrafts(Object.fromEntries(d.additives.map((a) => [a.id, draftFrom(a)])));
    } catch (e) {
      setError(isAxiosError(e) ? "Não foi possível carregar o projeto." : "Erro ao carregar.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (open && projectId) void load();
  }, [open, projectId, load]);

  // Reseta para a aba Geral a cada abertura.
  useEffect(() => {
    if (open) setActiveTab("geral");
  }, [open, projectId]);

  // Centros de Custo já existentes (para o select da aba Geral).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void fetchCostCenters()
      .then((cc) => {
        if (!cancelled) setCostCenterOptions(cc);
      })
      .catch(() => {
        if (!cancelled) setCostCenterOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const loadDocuments = useCallback(async () => {
    if (!projectId || !canViewDocs) return;
    setDocsLoading(true);
    try {
      setDocuments(await listProjectDocuments(projectId));
    } catch {
      setError("Não foi possível carregar os documentos.");
    } finally {
      setDocsLoading(false);
    }
  }, [projectId, canViewDocs]);

  useEffect(() => {
    if (open && activeTab === "documentos") void loadDocuments();
  }, [open, activeTab, loadDocuments]);

  async function handleUploadDocument() {
    if (!projectId || !docFile) return;
    if (!docTitle.trim()) {
      setError("Informe o título do documento.");
      return;
    }
    setUploadingDoc(true);
    setError(null);
    try {
      await uploadProjectDocument(projectId, {
        category: docCategory,
        title: docTitle.trim(),
        file: docFile,
      });
      setDocTitle("");
      setDocFile(null);
      setDocCategory("CONTRATO");
      await loadDocuments();
    } catch (e) {
      setError(isAxiosError(e) ? (e.response?.data?.detail ?? "Não foi possível enviar o documento.") : "Erro no upload.");
    } finally {
      setUploadingDoc(false);
    }
  }

  async function handleDownloadDocument(doc: ProjectDocument) {
    setBusyDocId(doc.id);
    setError(null);
    try {
      await downloadProjectDocument(doc);
    } catch (e) {
      setError(`Não foi possível baixar o documento: ${formatApiError(e)}`);
    } finally {
      setBusyDocId(null);
    }
  }

  async function handleDeleteDocument(doc: ProjectDocument) {
    if (!projectId) return;
    if (!window.confirm(`Excluir o documento "${doc.title}"?`)) return;
    setBusyDocId(doc.id);
    setError(null);
    try {
      await deleteProjectDocument(projectId, doc.id);
      setDocuments((prev) => prev.filter((x) => x.id !== doc.id));
    } catch {
      setError("Não foi possível excluir o documento.");
    } finally {
      setBusyDocId(null);
    }
  }

  async function handleSaveGeneral() {
    if (!projectId) return;
    if (!projName.trim()) {
      setError("Informe o nome do projeto.");
      return;
    }
    setSavingGeneral(true);
    setError(null);
    try {
      // Reutiliza o mesmo endpoint de atualização (nome/descrição)…
      await updateProjectGeneral(projectId, {
        name: projName.trim(),
        description: projDescription.trim() || null,
        cost_center: projCostCenter.trim() || null,
      });
      // …e o fluxo existente de encerramento/reativação para o status.
      if (projActive !== projActiveOriginal) {
        if (projActive) await activateProject(projectId);
        else await deactivateProject(projectId);
        setProjActiveOriginal(projActive);
      }
      onSaved?.();
    } catch (e) {
      setError(isAxiosError(e) ? (e.response?.data?.detail ?? "Não foi possível salvar as alterações.") : "Erro ao salvar.");
    } finally {
      setSavingGeneral(false);
    }
  }

  async function handleSaveContract() {
    if (!projectId) return;
    const months = contractDuration.trim() ? Math.trunc(Number(contractDuration)) : null;
    // A data de início é obrigatória para permitir o cálculo da data final.
    if (months != null && !contractStartDate) {
      setError("Informe a data de início do contrato para calcular a data final.");
      return;
    }
    setSavingContract(true);
    setError(null);
    try {
      await updateProjectContract(projectId, {
        contract_number: contractNumber.trim() || null,
        contract_value: contractValue.trim() ? normalizeCurrencyForApi(contractValue) : null,
        contract_start_date: contractStartDate || null,
        contract_duration: months,
        buyer_name: buyerName.trim() || null,
        buyer_phone: buyerPhone.trim() || null,
        buyer_email: buyerEmail.trim() || null,
        manager_name: managerName.trim() || null,
        manager_phone: managerPhone.trim() || null,
        manager_email: managerEmail.trim() || null,
      });
      onSaved?.();
    } catch (e) {
      setError(isAxiosError(e) ? "Não foi possível salvar as informações do contrato." : "Erro ao salvar.");
    } finally {
      setSavingContract(false);
    }
  }

  async function handleAddAdditive() {
    if (!projectId) return;
    setBusyAdditiveId("new");
    setError(null);
    try {
      const created = await createProjectAdditive(projectId, {});
      setAdditives((prev) => [...prev, created]);
      setDrafts((prev) => ({ ...prev, [created.id]: draftFrom(created) }));
      onSaved?.();
    } catch (e) {
      setError(isAxiosError(e) ? "Não foi possível adicionar o aditivo." : "Erro ao adicionar.");
    } finally {
      setBusyAdditiveId(null);
    }
  }

  async function handleSaveAdditive(id: string) {
    if (!projectId) return;
    const d = drafts[id];
    if (!d) return;
    setBusyAdditiveId(id);
    setError(null);
    try {
      const updated = await updateProjectAdditive(projectId, id, {
        additive_date: d.additive_date || null,
        additive_value: d.additive_value.trim() ? normalizeCurrencyForApi(d.additive_value) : null,
        additive_duration: d.additive_duration.trim() || null,
      });
      setAdditives((prev) => prev.map((a) => (a.id === id ? updated : a)));
      onSaved?.();
    } catch (e) {
      setError(isAxiosError(e) ? "Não foi possível salvar o aditivo." : "Erro ao salvar aditivo.");
    } finally {
      setBusyAdditiveId(null);
    }
  }

  async function handleRemoveAdditive(id: string) {
    if (!projectId) return;
    if (!window.confirm("Remover este aditivo?")) return;
    setBusyAdditiveId(id);
    setError(null);
    try {
      await deleteProjectAdditive(projectId, id);
      setAdditives((prev) => prev.filter((a) => a.id !== id));
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      onSaved?.();
    } catch (e) {
      setError(isAxiosError(e) ? "Não foi possível remover o aditivo." : "Erro ao remover.");
    } finally {
      setBusyAdditiveId(null);
    }
  }

  function setDraft(id: string, patch: Partial<AdditiveDraft>) {
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  if (!open) return null;

  const inputCls =
    "rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-500";
  const labelCls = "flex flex-col gap-1 text-sm";
  const legendCls = "text-xs font-semibold uppercase tracking-wide text-slate-500";

  // Vigência atual (ao vivo) = início + prazo original + Σ prazos dos aditivos em edição.
  const additiveMonthsSum = Object.values(drafts).reduce((acc, dr) => {
    const n = Math.trunc(Number(dr.additive_duration));
    return acc + (Number.isFinite(n) ? n : 0);
  }, 0);
  const baseMonths = contractDuration.trim() ? Math.trunc(Number(contractDuration)) : null;
  const validityIso = computeValidityIso(contractStartDate, baseMonths, additiveMonthsSum);
  const validity = contractValidityInfo(validityIso || null);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        className="my-4 w-full max-w-3xl rounded-xl border border-slate-200 bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">
            Detalhes {projectName ? `— ${projectName}` : ""}
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

        {/* Abas */}
        <div className="border-b border-slate-200 px-5">
          <nav className="-mb-px flex gap-1 overflow-x-auto text-sm">
            {([
              { key: "geral", label: "Geral" },
              { key: "contrato", label: "Contrato" },
              ...(canViewDocs ? [{ key: "documentos", label: "Documentos" } as const] : []),
              { key: "historico", label: "Histórico" },
            ] as { key: DetailTab; label: string }[]).map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setActiveTab(t.key)}
                className={`whitespace-nowrap border-b-2 px-3 py-2.5 font-medium ${
                  activeTab === t.key
                    ? "border-indigo-600 text-indigo-700"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>

        {loading ? (
          <p className="p-8 text-center text-sm text-slate-500">Carregando…</p>
        ) : (
          <div className="p-5">
            {/* Aba Geral — informações básicas (editáveis). */}
            {activeTab === "geral" ? (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className={labelCls}>
                    <span className="font-medium text-slate-700">Nome *</span>
                    <input
                      value={projName}
                      onChange={(e) => setProjName(e.target.value)}
                      disabled={!canEdit}
                      className={inputCls}
                    />
                  </label>
                  <label className={labelCls}>
                    <span className="font-medium text-slate-700">Status</span>
                    <select
                      value={projActive ? "ativo" : "encerrado"}
                      onChange={(e) => setProjActive(e.target.value === "ativo")}
                      disabled={!canEdit}
                      className={inputCls}
                    >
                      <option value="ativo">Ativo</option>
                      <option value="encerrado">Encerrado</option>
                    </select>
                  </label>
                  <label className={`${labelCls} sm:col-span-2`}>
                    <span className="font-medium text-slate-700">Centro de Custo</span>
                    <CostCenterCombo
                      value={projCostCenter}
                      onChange={setProjCostCenter}
                      options={costCenterOptions}
                      disabled={!canEdit}
                      className={inputCls}
                    />
                    <span className="text-xs font-normal text-slate-500">
                      Agrupamento reutilizável — define quais colaboradores aparecem para alocação neste projeto.
                    </span>
                  </label>
                  <label className={`${labelCls} sm:col-span-2`}>
                    <span className="font-medium text-slate-700">Descrição</span>
                    <textarea
                      value={projDescription}
                      onChange={(e) => setProjDescription(e.target.value)}
                      disabled={!canEdit}
                      rows={3}
                      className={`${inputCls} resize-y`}
                    />
                  </label>
                </div>
                {canEdit ? (
                  <div className="flex justify-end">
                    <button
                      type="button"
                      disabled={savingGeneral}
                      onClick={() => void handleSaveGeneral()}
                      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {savingGeneral ? "Salvando…" : "Salvar alterações"}
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}

            {/* Aba Contrato — toda a implementação contratual existente. */}
            {activeTab === "contrato" ? (
              <div className="space-y-6">
            {/* Informações do contrato */}
            <section className="space-y-3">
              <p className={legendCls}>Informações do contrato</p>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Número do contrato</span>
                  <input
                    value={contractNumber}
                    onChange={(e) => setContractNumber(e.target.value)}
                    disabled={!canEdit}
                    className={inputCls}
                  />
                </label>
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Valor total</span>
                  <input
                    value={contractValue}
                    onChange={(e) => setContractValue(e.target.value)}
                    disabled={!canEdit}
                    inputMode="decimal"
                    placeholder="0,00"
                    className={inputCls}
                  />
                </label>
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Data de início do contrato *</span>
                  <input
                    type="date"
                    value={contractStartDate}
                    onChange={(e) => setContractStartDate(e.target.value)}
                    disabled={!canEdit}
                    className={inputCls}
                  />
                </label>
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Prazo Total (Meses)</span>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={contractDuration}
                    onChange={(e) => setContractDuration(e.target.value)}
                    disabled={!canEdit}
                    placeholder="ex.: 36"
                    className={inputCls}
                  />
                </label>
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Data final original</span>
                  <input
                    value={computeEndDateBr(contractStartDate, baseMonths)}
                    readOnly
                    tabIndex={-1}
                    title="Calculada automaticamente: início + prazo original (meses)"
                    className={`${inputCls} cursor-default bg-slate-50 text-slate-600`}
                  />
                </label>
              </div>
              {/* Resumo da vigência — pequeno bloco organizado, sem caixas coloridas/alertas. */}
              <div className="mt-1 rounded-lg border border-slate-200 bg-slate-50/60 px-4 py-3">
                <p className={legendCls}>Resumo da vigência</p>
                <dl className="mt-2 grid grid-cols-1 gap-x-8 gap-y-1.5 text-sm sm:grid-cols-3">
                  <div className="flex justify-between gap-2 sm:block">
                    <dt className="text-slate-500">Data início</dt>
                    <dd className="font-medium text-slate-800">{computeEndDateBr(contractStartDate, 0)}</dd>
                  </div>
                  <div className="flex justify-between gap-2 sm:block">
                    <dt className="text-slate-500">Data final original</dt>
                    <dd className="font-medium text-slate-800">{computeEndDateBr(contractStartDate, baseMonths)}</dd>
                  </div>
                  <div className="flex justify-between gap-2 sm:block">
                    <dt className="text-slate-500">Vigência atual</dt>
                    <dd className="font-semibold text-slate-900">{validity.dateBr}</dd>
                  </div>
                </dl>
                {validity.days != null && validity.tone === "warning" ? (
                  <p className="mt-2 text-xs font-medium text-amber-700">🟡 Restam {validity.days} dias</p>
                ) : validity.days != null && validity.tone === "expired" ? (
                  <p className="mt-2 text-xs font-medium text-red-700">
                    🔴 Contrato vencido há {Math.abs(validity.days)} dias
                  </p>
                ) : null}
              </div>
            </section>

            {/* Comprador */}
            <section className="space-y-3">
              <p className={legendCls}>Comprador</p>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Nome</span>
                  <input value={buyerName} onChange={(e) => setBuyerName(e.target.value)} disabled={!canEdit} className={inputCls} />
                </label>
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Telefone</span>
                  <input value={buyerPhone} onChange={(e) => setBuyerPhone(e.target.value)} disabled={!canEdit} className={inputCls} />
                </label>
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">E-mail</span>
                  <input value={buyerEmail} onChange={(e) => setBuyerEmail(e.target.value)} disabled={!canEdit} type="email" className={inputCls} />
                </label>
              </div>
            </section>

            {/* Gestor do contrato */}
            <section className="space-y-3">
              <p className={legendCls}>Gestor do contrato</p>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Nome</span>
                  <input value={managerName} onChange={(e) => setManagerName(e.target.value)} disabled={!canEdit} className={inputCls} />
                </label>
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">Telefone</span>
                  <input value={managerPhone} onChange={(e) => setManagerPhone(e.target.value)} disabled={!canEdit} className={inputCls} />
                </label>
                <label className={labelCls}>
                  <span className="font-medium text-slate-700">E-mail</span>
                  <input value={managerEmail} onChange={(e) => setManagerEmail(e.target.value)} disabled={!canEdit} type="email" className={inputCls} />
                </label>
              </div>
              {canEdit ? (
                <div className="flex justify-end">
                  <button
                    type="button"
                    disabled={savingContract}
                    onClick={() => void handleSaveContract()}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {savingContract ? "Salvando…" : "Salvar informações do contrato"}
                  </button>
                </div>
              ) : null}
            </section>

            {/* Aditivos contratuais */}
            <section className="space-y-3 border-t border-slate-200 pt-4">
              <div className="flex items-center justify-between">
                <p className={legendCls}>Aditivos contratuais</p>
                {canEdit ? (
                  <button
                    type="button"
                    disabled={busyAdditiveId === "new"}
                    onClick={() => void handleAddAdditive()}
                    className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50"
                  >
                    {busyAdditiveId === "new" ? "Adicionando…" : "+ Adicionar aditivo"}
                  </button>
                ) : null}
              </div>

              {additives.length === 0 ? (
                <p className="text-sm text-slate-500">Nenhum aditivo cadastrado.</p>
              ) : (
                <div className="space-y-3">
                  {additives.map((a, idx) => {
                    const d = drafts[a.id] ?? draftFrom(a);
                    return (
                      <div key={a.id} className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-700">Aditivo {idx + 1}</span>
                          {!canEdit ? (
                            <span className="text-xs text-slate-500">{formatBRL(a.additive_value)}</span>
                          ) : null}
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                          <label className={labelCls}>
                            <span className="text-[11px] text-slate-500">Data do aditivo</span>
                            <input
                              type="date"
                              value={d.additive_date}
                              onChange={(e) => setDraft(a.id, { additive_date: e.target.value })}
                              disabled={!canEdit}
                              className={inputCls}
                            />
                          </label>
                          <label className={labelCls}>
                            <span className="text-[11px] text-slate-500">Valor do aditivo</span>
                            <input
                              value={d.additive_value}
                              onChange={(e) => setDraft(a.id, { additive_value: e.target.value })}
                              disabled={!canEdit}
                              inputMode="decimal"
                              placeholder="0,00"
                              className={inputCls}
                            />
                          </label>
                          <label className={labelCls}>
                            <span className="text-[11px] text-slate-500">Prazo adicional (Meses)</span>
                            <input
                              type="number"
                              min={0}
                              step={1}
                              value={d.additive_duration}
                              onChange={(e) => setDraft(a.id, { additive_duration: e.target.value })}
                              disabled={!canEdit}
                              placeholder="ex.: 2"
                              className={inputCls}
                            />
                          </label>
                          <label className={labelCls}>
                            <span className="text-[11px] text-slate-500">Data final do aditivo</span>
                            <input
                              value={computeEndDateBr(d.additive_date, d.additive_duration.trim() ? Math.trunc(Number(d.additive_duration)) : null)}
                              readOnly
                              tabIndex={-1}
                              title="Calculada automaticamente: data do aditivo + prazo adicional (meses)"
                              className={`${inputCls} cursor-default bg-slate-50 text-slate-600`}
                            />
                          </label>
                        </div>
                        {canEdit ? (
                          <div className="mt-2 flex justify-end gap-2">
                            <button
                              type="button"
                              disabled={busyAdditiveId === a.id}
                              onClick={() => void handleSaveAdditive(a.id)}
                              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                            >
                              {busyAdditiveId === a.id ? "Salvando…" : "Salvar"}
                            </button>
                            <button
                              type="button"
                              disabled={busyAdditiveId === a.id}
                              onClick={() => void handleRemoveAdditive(a.id)}
                              className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                            >
                              Remover
                            </button>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
              </div>
            ) : null}

            {/* Aba Documentos */}
            {activeTab === "documentos" && canViewDocs ? (
              <div className="space-y-4">
                {canUploadDocs ? (
                  <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                    <p className={`${legendCls} mb-2`}>Adicionar documento</p>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <label className={labelCls}>
                        <span className="text-[11px] text-slate-500">Categoria</span>
                        <select
                          value={docCategory}
                          onChange={(e) => setDocCategory(e.target.value as ProjectDocumentCategory)}
                          className={inputCls}
                        >
                          {PROJECT_DOCUMENT_CATEGORIES.map((c) => (
                            <option key={c.value} value={c.value}>
                              {c.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className={labelCls}>
                        <span className="text-[11px] text-slate-500">Título</span>
                        <input
                          value={docTitle}
                          onChange={(e) => setDocTitle(e.target.value)}
                          placeholder="ex.: Contrato assinado"
                          className={inputCls}
                        />
                      </label>
                      <label className={labelCls}>
                        <span className="text-[11px] text-slate-500">Arquivo</span>
                        <input
                          type="file"
                          onChange={(e) => setDocFile(e.target.files?.[0] ?? null)}
                          className="text-xs text-slate-600 file:mr-2 file:rounded file:border-0 file:bg-slate-200 file:px-2 file:py-1 file:text-xs"
                        />
                      </label>
                    </div>
                    <div className="mt-2 flex justify-end">
                      <button
                        type="button"
                        disabled={uploadingDoc || !docFile || !docTitle.trim()}
                        onClick={() => void handleUploadDocument()}
                        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        {uploadingDoc ? "Enviando…" : "Salvar"}
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full min-w-[640px] divide-y divide-slate-200 text-sm">
                    <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-600">
                      <tr>
                        <th className="px-3 py-2">Categoria</th>
                        <th className="px-3 py-2">Título</th>
                        <th className="px-3 py-2">Arquivo</th>
                        <th className="px-3 py-2">Enviado por</th>
                        <th className="px-3 py-2">Data</th>
                        <th className="px-3 py-2 text-right">Ações</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {docsLoading ? (
                        <tr>
                          <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                            Carregando…
                          </td>
                        </tr>
                      ) : documents.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                            Nenhum documento cadastrado.
                          </td>
                        </tr>
                      ) : (
                        documents.map((doc) => (
                          <tr key={doc.id} className="hover:bg-slate-50/80">
                            <td className="px-3 py-2">
                              <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                                {CATEGORY_LABEL[doc.category] ?? doc.category}
                              </span>
                            </td>
                            <td className="px-3 py-2 font-medium text-slate-900">{doc.title}</td>
                            <td className="max-w-[180px] truncate px-3 py-2 text-slate-600" title={doc.original_filename}>
                              {doc.original_filename}
                            </td>
                            <td className="px-3 py-2 text-slate-600">{doc.uploaded_by_name ?? "—"}</td>
                            <td className="whitespace-nowrap px-3 py-2 text-slate-600">
                              {new Date(doc.uploaded_at).toLocaleDateString("pt-BR")}
                            </td>
                            <td className="whitespace-nowrap px-3 py-2 text-right">
                              <button
                                type="button"
                                disabled={busyDocId === doc.id}
                                onClick={() => void handleDownloadDocument(doc)}
                                className="rounded px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                              >
                                Download
                              </button>
                              {canDeleteDocs ? (
                                <button
                                  type="button"
                                  disabled={busyDocId === doc.id}
                                  onClick={() => void handleDeleteDocument(doc)}
                                  className="ml-1 rounded px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                                >
                                  Excluir
                                </button>
                              ) : null}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            {/* Aba Histórico — placeholder (próxima etapa). */}
            {activeTab === "historico" ? (
              <p className="py-10 text-center text-sm text-slate-500">
                Histórico do projeto será implementado em uma próxima etapa.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
