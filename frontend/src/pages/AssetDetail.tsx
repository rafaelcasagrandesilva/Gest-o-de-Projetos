import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AssetSizeBadge } from "@/components/assets/AssetSizeBadge";
import { AssetSizeField } from "@/components/assets/AssetSizeField";
import {
  ASSET_MACRO_CATEGORIES,
  isEpiMacroCategory,
  isTechMacroCategory,
} from "@/components/assets/assetCategories";
import { assetSupportsSize } from "@/components/assets/assetSize";
import { formatTagsInput, parseTagsInput } from "@/components/assets/assetTags";
import { AssetExpirationBadge } from "@/components/assets/AssetExpirationBadge";
import { AssetPhysicalConditionBadge } from "@/components/assets/AssetPhysicalConditionBadge";
import { AssetStatusBadge } from "@/components/assets/AssetStatusBadge";
import { AssetMoneyInput } from "@/components/assets/AssetMoneyInput";
import { moneyFieldFromNumber } from "@/components/assets/assetMoney";
import {
  ASSET_STATUS_LABELS,
  formatAssignmentDeliveryLine,
  formatBRL,
  parseBRLInput,
  PHYSICAL_CONDITION_LABELS,
} from "@/components/assets/assetLabels";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { CostCenterSelect } from "@/components/company-finance/CostCenterSelect";
import { CollaboratorSelect } from "@/components/CollaboratorSelect";
import { useAuth } from "@/context/AuthContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { hasPermission } from "@/permissions";
import { api } from "@/services/api";
import {
  createAssignment,
  createInspection,
  deleteAsset,
  deleteAssetAttachment,
  deleteAssignment,
  deleteInspection,
  deleteReturnAssignment,
  fetchAssetCategories,
  getAssetDetail,
  returnAssignment,
  updateAsset,
  updateReturnAssignment,
  type AssetAssignment,
  uploadAssetAttachment,
  type AssetAttachmentType,
  type AssetDetail,
  type AssetPhysicalCondition,
  type AssetStatus,
} from "@/services/assets";
import { listProjects, type Project } from "@/services/projects";

type TabId = "general" | "assignments" | "inspections" | "files" | "timeline";

const TABS: { id: TabId; label: string }[] = [
  { id: "general", label: "Geral" },
  { id: "assignments", label: "Responsabilidade" },
  { id: "inspections", label: "Ensaios e validade" },
  { id: "files", label: "Arquivos" },
  { id: "timeline", label: "Histórico" },
];

const ATTACHMENT_TYPES: { value: AssetAttachmentType; label: string }[] = [
  { value: "TERM", label: "Termo de responsabilidade" },
  { value: "REPORT", label: "Laudo" },
  { value: "CERTIFICATE", label: "Certificado" },
  { value: "INVOICE", label: "Nota fiscal" },
  { value: "MANUAL", label: "Manual" },
  { value: "PHOTO", label: "Foto" },
  { value: "MAINTENANCE_ORDER", label: "OS manutenção" },
  { value: "OTHER", label: "Outro" },
];

type ConfirmTarget =
  | { type: "asset" }
  | { type: "assignment"; id: string }
  | { type: "return"; id: string }
  | { type: "inspection"; id: string }
  | { type: "attachment"; id: string };

const PHYSICAL_OPTIONS: AssetPhysicalCondition[] = ["NEW", "GOOD", "FAIR", "DAMAGED"];

export function AssetDetailPage() {
  const { assetId } = useParams<{ assetId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { setWorkspace } = useWorkspace();

  useEffect(() => {
    setWorkspace("assets");
  }, [setWorkspace]);
  const canEdit = hasPermission(user?.permission_names, "assets.edit");

  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [tab, setTab] = useState<TabId>("general");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [assignDeliveredById, setAssignDeliveredById] = useState("");
  const [assignDeliveredByName, setAssignDeliveredByName] = useState<string | null>(null);
  const [assignEmployeeId, setAssignEmployeeId] = useState("");
  const [assignEmployeeName, setAssignEmployeeName] = useState<string | null>(null);
  const [assignDate, setAssignDate] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [returnToId, setReturnToId] = useState("");
  const [returnToName, setReturnToName] = useState<string | null>(null);
  const [returnPhysicalCondition, setReturnPhysicalCondition] = useState<AssetPhysicalCondition>("GOOD");
  const [returnNotes, setReturnNotes] = useState("");
  const [editReturnId, setEditReturnId] = useState<string | null>(null);
  const [purchaseValueInput, setPurchaseValueInput] = useState("");
  const [tagsInput, setTagsInput] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [confirm, setConfirm] = useState<ConfirmTarget | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const openAssignment = useMemo(
    () => detail?.assignments.find((a) => !a.return_date) ?? null,
    [detail],
  );

  const load = useCallback(async () => {
    if (!assetId) return;
    setError(null);
    try {
      const row = await getAssetDetail(assetId);
      setDetail(row);
      setPurchaseValueInput(moneyFieldFromNumber(row.purchase_value));
      setTagsInput(formatTagsInput(row.tags));
    } catch {
      setError("Ativo não encontrado.");
      setDetail(null);
    }
  }, [assetId]);

  useEffect(() => {
    void load();
    void listProjects().then(setProjects).catch(() => undefined);
    void fetchAssetCategories()
      .then(setCategories)
      .catch(() => setCategories([...ASSET_MACRO_CATEGORIES]));
  }, [load]);

  async function saveGeneral() {
    if (!detail || !canEdit) return;
    setSaving(true);
    try {
      await updateAsset(detail.id, {
        name: detail.name,
        category: detail.category,
        subcategory: detail.subcategory,
        tags: parseTagsInput(tagsInput),
        size: detail.size?.trim() ? detail.size.trim() : null,
        description: detail.description,
        brand: detail.brand,
        model: detail.model,
        serial_number: detail.serial_number,
        patrimony_tag: detail.patrimony_tag,
        imei: detail.imei,
        ca_number: detail.ca_number,
        status: detail.status,
        physical_condition: detail.physical_condition,
        acquisition_date: detail.acquisition_date,
        purchase_value: purchaseValueInput.trim() ? parseBRLInput(purchaseValueInput) : null,
        notes: detail.notes,
        cost_center_ref: detail.cost_center_ref ?? undefined,
      });
      await load();
    } catch {
      setError("Erro ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  function patch<K extends keyof AssetDetail>(key: K, value: AssetDetail[K]) {
    setDetail((d) => (d ? { ...d, [key]: value } : d));
  }

  async function handleNewAssignment() {
    if (!detail || !assetId) return;
    if (!assignDeliveredById || !assignEmployeeId || !assignDate) {
      setError("Informe quem entregou, quem recebeu e a data de entrega.");
      return;
    }
    try {
      await createAssignment(assetId, {
        employee_id: assignEmployeeId,
        delivered_by_employee_id: assignDeliveredById,
        delivery_date: assignDate,
      });
      setAssignDeliveredById("");
      setAssignDeliveredByName(null);
      setAssignEmployeeId("");
      setAssignEmployeeName(null);
      setAssignDate("");
      setError(null);
      await load();
    } catch {
      setError("Não foi possível registrar a entrega.");
    }
  }

  async function handleReturn(assignmentId: string) {
    if (!assetId || !returnDate || !returnToId) {
      setError("Informe quem recebeu a devolução e a data.");
      return;
    }
    try {
      await returnAssignment(assetId, assignmentId, {
        return_date: returnDate,
        returned_to_employee_id: returnToId,
        returned_condition: returnPhysicalCondition,
        return_notes: returnNotes.trim() || null,
      });
      setReturnDate("");
      setReturnToId("");
      setReturnToName(null);
      setReturnNotes("");
      setError(null);
      await load();
    } catch {
      setError("Não foi possível registrar a devolução.");
    }
  }

  function startEditReturn(a: AssetAssignment) {
    setEditReturnId(a.id);
    setReturnDate(a.return_date ?? "");
    setReturnToId(a.returned_to_employee_id ?? "");
    setReturnToName(a.returned_to_name);
    setReturnPhysicalCondition(a.returned_condition ?? "GOOD");
    setReturnNotes(a.return_notes ?? "");
  }

  async function handleSaveReturnEdit(assignmentId: string) {
    if (!assetId || !returnDate || !returnToId) {
      setError("Informe quem recebeu a devolução e a data.");
      return;
    }
    try {
      await updateReturnAssignment(assetId, assignmentId, {
        return_date: returnDate,
        returned_to_employee_id: returnToId,
        returned_condition: returnPhysicalCondition,
        return_notes: returnNotes.trim() || null,
      });
      setEditReturnId(null);
      setError(null);
      await load();
    } catch {
      setError("Não foi possível atualizar a devolução.");
    }
  }

  async function runConfirmDelete() {
    if (!confirm || !assetId) return;
    setConfirmLoading(true);
    try {
      if (confirm.type === "asset") {
        await deleteAsset(assetId);
        navigate("/assets");
        return;
      }
      if (confirm.type === "assignment") await deleteAssignment(assetId, confirm.id);
      if (confirm.type === "return") await deleteReturnAssignment(assetId, confirm.id);
      if (confirm.type === "inspection") await deleteInspection(assetId, confirm.id);
      if (confirm.type === "attachment") await deleteAssetAttachment(assetId, confirm.id);
      setConfirm(null);
      await load();
    } catch {
      setError("Não foi possível excluir.");
    } finally {
      setConfirmLoading(false);
    }
  }

  async function handleNewInspection() {
    if (!assetId) return;
    const type = (document.getElementById("insp-type") as HTMLInputElement | null)?.value?.trim();
    const date = (document.getElementById("insp-date") as HTMLInputElement | null)?.value;
    const months = (document.getElementById("insp-months") as HTMLInputElement | null)?.value;
    if (!type || !date) return;
    try {
      await createInspection(assetId, {
        inspection_type: type,
        inspection_date: date,
        expiration_months: months ? Number(months) : null,
      });
      await load();
    } catch {
      setError("Não foi possível registrar o ensaio.");
    }
  }

  async function handleUpload(file: File, fileType: AssetAttachmentType) {
    if (!assetId) return;
    try {
      await uploadAssetAttachment(assetId, file, fileType);
      await load();
    } catch {
      setError("Falha no upload.");
    }
  }

  async function handleDownload(path: string, fileName: string) {
    try {
      const { data } = await api.get<Blob>(path, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Não foi possível baixar o arquivo.");
    }
  }

  if (!detail) {
    return (
      <div className="space-y-4">
        <Link to="/assets" className="text-sm text-indigo-600 hover:underline">
          ← Voltar
        </Link>
        <p className="text-slate-500">{error ?? "Carregando…"}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/assets" className="text-sm text-indigo-600 hover:underline">
            ← Patrimônio
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">
            {detail.name}{" "}
            <span className="font-mono text-base font-normal text-slate-500">{detail.asset_code}</span>
          </h1>
          <div className="mt-2 flex flex-wrap gap-2">
            <AssetStatusBadge status={detail.status} />
            <AssetSizeBadge size={detail.size} />
            <AssetPhysicalConditionBadge condition={detail.physical_condition} />
            <AssetExpirationBadge
              show={detail.has_inspection_control}
              level={detail.expiration_alert}
              compact
            />
          </div>
        </div>
        {canEdit ? (
          <button
            type="button"
            onClick={() => setConfirm({ type: "asset" })}
            className="rounded-lg border border-red-200 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50"
          >
            Excluir ativo
          </button>
        ) : null}
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium ${
              tab === t.id ? "border border-b-0 border-slate-200 bg-white text-indigo-700" : "text-slate-600"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6">
        {tab === "general" ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm sm:col-span-2">
              <span className="text-slate-600">Nome do item</span>
              <input
                disabled={!canEdit}
                value={detail.name}
                onChange={(e) => patch("name", e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            <label className="text-sm">
              <span className="text-slate-600">Categoria</span>
              <select
                disabled={!canEdit}
                value={detail.category}
                onChange={(e) => patch("category", e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              >
                {(categories.length ? categories : [...ASSET_MACRO_CATEGORIES]).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="text-slate-600">Tags</span>
              <input
                disabled={!canEdit}
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
                placeholder="isolado, medição, ATPV…"
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
              <p className="mt-1 text-xs text-slate-500">Separadas por vírgula — uso em buscas futuras.</p>
            </label>
            {detail.subcategory ? (
              <div className="text-sm sm:col-span-2">
                <span className="text-slate-600">Subcategoria (legado)</span>
                <p className="mt-1 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-slate-700">
                  {detail.subcategory}
                </p>
              </div>
            ) : null}
            <label className="text-sm">
              <span className="text-slate-600">Status</span>
              <select
                disabled={!canEdit}
                value={detail.status}
                onChange={(e) => patch("status", e.target.value as AssetStatus)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              >
                {(Object.keys(ASSET_STATUS_LABELS) as AssetStatus[]).map((s) => (
                  <option key={s} value={s}>
                    {ASSET_STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="text-slate-600">Estado físico</span>
              <select
                disabled={!canEdit}
                value={detail.physical_condition ?? ""}
                onChange={(e) =>
                  patch("physical_condition", (e.target.value || null) as AssetPhysicalCondition | null)
                }
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              >
                <option value="">—</option>
                {PHYSICAL_OPTIONS.map((c) => (
                  <option key={c} value={c}>
                    {PHYSICAL_CONDITION_LABELS[c]}
                  </option>
                ))}
              </select>
              <div className="mt-1">
                <AssetPhysicalConditionBadge condition={detail.physical_condition} />
              </div>
            </label>
            <label className="text-sm">
              <span className="text-slate-600">Valor do item (R$)</span>
              <AssetMoneyInput
                disabled={!canEdit}
                value={purchaseValueInput}
                onChange={setPurchaseValueInput}
              />
              {detail.purchase_value != null && detail.purchase_value > 0 ? (
                <p className="mt-1 text-xs text-slate-500">{formatBRL(detail.purchase_value)}</p>
              ) : null}
            </label>
            <label className="text-sm">
              <span className="text-slate-600">Centro de custo</span>
              <CostCenterSelect
                value={detail.cost_center_ref ?? ""}
                onChange={(ref) => patch("cost_center_ref", ref)}
                projects={projects}
                disabled={!canEdit}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            {assetSupportsSize(detail.category) ? (
              <AssetSizeField
                disabled={!canEdit}
                value={detail.size ?? ""}
                onChange={(v) => patch("size", v.trim() ? v : null)}
                className="text-sm"
              />
            ) : null}
            <label className="text-sm sm:col-span-2">
              <span className="text-slate-600">Descrição</span>
              <textarea
                disabled={!canEdit}
                value={detail.description ?? ""}
                onChange={(e) => patch("description", e.target.value || null)}
                rows={2}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            {isTechMacroCategory(detail.category) ? (
              <>
                <label className="text-sm">
                  <span className="text-slate-600">Marca</span>
                  <input
                    disabled={!canEdit}
                    value={detail.brand ?? ""}
                    onChange={(e) => patch("brand", e.target.value || null)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="text-sm">
                  <span className="text-slate-600">Modelo</span>
                  <input
                    disabled={!canEdit}
                    value={detail.model ?? ""}
                    onChange={(e) => patch("model", e.target.value || null)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="text-sm">
                  <span className="text-slate-600">Nº série</span>
                  <input
                    disabled={!canEdit}
                    value={detail.serial_number ?? ""}
                    onChange={(e) => patch("serial_number", e.target.value || null)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="text-sm">
                  <span className="text-slate-600">IMEI</span>
                  <input
                    disabled={!canEdit}
                    value={detail.imei ?? ""}
                    onChange={(e) => patch("imei", e.target.value || null)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="text-sm">
                  <span className="text-slate-600">Etiqueta patrimonial</span>
                  <input
                    disabled={!canEdit}
                    value={detail.patrimony_tag ?? ""}
                    onChange={(e) => patch("patrimony_tag", e.target.value || null)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
              </>
            ) : null}
            {isEpiMacroCategory(detail.category) ? (
              <label className="text-sm">
                <span className="text-slate-600">CA</span>
                <input
                  disabled={!canEdit}
                  value={detail.ca_number ?? ""}
                  onChange={(e) => patch("ca_number", e.target.value || null)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
            ) : null}
            {!isTechMacroCategory(detail.category) ? (
              <>
                <label className="text-sm">
                  <span className="text-slate-600">Marca</span>
                  <input
                    disabled={!canEdit}
                    value={detail.brand ?? ""}
                    onChange={(e) => patch("brand", e.target.value || null)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="text-sm">
                  <span className="text-slate-600">Modelo</span>
                  <input
                    disabled={!canEdit}
                    value={detail.model ?? ""}
                    onChange={(e) => patch("model", e.target.value || null)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="text-sm">
                  <span className="text-slate-600">Nº série / patrimônio</span>
                  <input
                    disabled={!canEdit}
                    value={detail.serial_number ?? detail.patrimony_tag ?? ""}
                    onChange={(e) => patch("serial_number", e.target.value || null)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
              </>
            ) : null}
            <label className="text-sm sm:col-span-2">
              <span className="text-slate-600">Observações</span>
              <textarea
                disabled={!canEdit}
                value={detail.notes ?? ""}
                onChange={(e) => patch("notes", e.target.value || null)}
                rows={3}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            {canEdit ? (
              <div className="sm:col-span-2">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void saveGeneral()}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-50"
                >
                  {saving ? "Salvando…" : "Salvar"}
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        {tab === "assignments" ? (
          <div className="space-y-6">
            {openAssignment ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm">
                <p>
                  <strong>Responsável atual:</strong> {openAssignment.employee_name} (desde{" "}
                  {openAssignment.delivery_date})
                </p>
                {canEdit ? (
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <p className="text-xs text-slate-600 sm:col-span-2">
                      Devolvendo: <strong>{openAssignment.employee_name}</strong>
                    </p>
                    <CollaboratorSelect
                      label="Responsável que recebeu a devolução"
                      value={returnToId}
                      selectedName={returnToName}
                      onChange={(id) => {
                        setReturnToId(id);
                        if (!id) setReturnToName(null);
                      }}
                      onPick={(it) => {
                        setReturnToId(it.id);
                        setReturnToName(it.name);
                      }}
                    />
                    <label className="text-sm">
                      Data devolução
                      <input
                        type="date"
                        value={returnDate}
                        onChange={(e) => setReturnDate(e.target.value)}
                        className="mt-1 w-full rounded border px-3 py-2"
                      />
                    </label>
                    <label className="text-sm sm:col-span-2">
                      Estado do item na devolução *
                      <select
                        value={returnPhysicalCondition}
                        onChange={(e) => setReturnPhysicalCondition(e.target.value as AssetPhysicalCondition)}
                        className="mt-1 w-full rounded border px-3 py-2"
                      >
                        {PHYSICAL_OPTIONS.map((c) => (
                          <option key={c} value={c}>
                            {PHYSICAL_CONDITION_LABELS[c]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-sm sm:col-span-2">
                      Observações da devolução
                      <textarea
                        value={returnNotes}
                        onChange={(e) => setReturnNotes(e.target.value)}
                        rows={2}
                        className="mt-1 w-full rounded border px-3 py-2"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => void handleReturn(openAssignment.id)}
                      className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white sm:col-span-2"
                    >
                      Registrar devolução
                    </button>
                  </div>
                ) : null}
              </div>
            ) : canEdit ? (
              <div className="space-y-3 rounded-lg border border-slate-200 p-4">
                <p className="text-sm font-medium">Nova entrega</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <CollaboratorSelect
                    label="Responsável que entregou"
                    value={assignDeliveredById}
                    selectedName={assignDeliveredByName}
                    onChange={(id) => {
                      setAssignDeliveredById(id);
                      if (!id) setAssignDeliveredByName(null);
                    }}
                    onPick={(it) => {
                      setAssignDeliveredById(it.id);
                      setAssignDeliveredByName(it.name);
                    }}
                  />
                  <CollaboratorSelect
                    label="Responsável que recebeu"
                    value={assignEmployeeId}
                    selectedName={assignEmployeeName}
                    onChange={(id) => {
                      setAssignEmployeeId(id);
                      if (!id) setAssignEmployeeName(null);
                    }}
                    onPick={(it) => {
                      setAssignEmployeeId(it.id);
                      setAssignEmployeeName(it.name);
                    }}
                  />
                  <label className="text-sm sm:col-span-2">
                    Data entrega
                    <input
                      type="date"
                      value={assignDate}
                      onChange={(e) => setAssignDate(e.target.value)}
                      className="mt-1 w-full rounded border px-3 py-2"
                    />
                  </label>
                </div>
                <button
                  type="button"
                  onClick={() => void handleNewAssignment()}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white"
                >
                  Registrar entrega
                </button>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Sem responsável ativo.</p>
            )}
            <ul className="divide-y divide-slate-100 text-sm">
              {detail.assignments.map((a) => (
                <li key={a.id} className="py-3">
                  {editReturnId === a.id ? (
                    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <p className="font-medium text-slate-800">Editar devolução</p>
                      <CollaboratorSelect
                        label="Responsável que recebeu a devolução"
                        value={returnToId}
                        selectedName={returnToName}
                        onChange={(id) => {
                          setReturnToId(id);
                          if (!id) setReturnToName(null);
                        }}
                        onPick={(it) => {
                          setReturnToId(it.id);
                          setReturnToName(it.name);
                        }}
                      />
                      <label className="block text-sm">
                        Data devolução
                        <input
                          type="date"
                          value={returnDate}
                          onChange={(e) => setReturnDate(e.target.value)}
                          className="mt-1 w-full rounded border px-3 py-2"
                        />
                      </label>
                      <label className="block text-sm">
                        Estado do item
                        <select
                          value={returnPhysicalCondition}
                          onChange={(e) =>
                            setReturnPhysicalCondition(e.target.value as AssetPhysicalCondition)
                          }
                          className="mt-1 w-full rounded border px-3 py-2"
                        >
                          {PHYSICAL_OPTIONS.map((c) => (
                            <option key={c} value={c}>
                              {PHYSICAL_CONDITION_LABELS[c]}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="block text-sm">
                        Observações
                        <textarea
                          value={returnNotes}
                          onChange={(e) => setReturnNotes(e.target.value)}
                          rows={2}
                          className="mt-1 w-full rounded border px-3 py-2"
                        />
                      </label>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => void handleSaveReturnEdit(a.id)}
                          className="rounded bg-indigo-600 px-3 py-1 text-xs text-white"
                        >
                          Salvar devolução
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditReturnId(null)}
                          className="rounded border px-3 py-1 text-xs"
                        >
                          Cancelar
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-0.5 text-slate-700">
                        <p>{formatAssignmentDeliveryLine(a)}</p>
                        {a.return_date ? (
                          <>
                            <p>
                              Devolução recebida por {a.returned_to_name ?? "—"} — devolução{" "}
                              {a.return_date}
                            </p>
                            {a.returned_condition ? (
                              <p className="text-slate-600">
                                Estado: {PHYSICAL_CONDITION_LABELS[a.returned_condition]}
                              </p>
                            ) : null}
                            {a.return_notes ? (
                              <p className="text-xs text-slate-500">{a.return_notes}</p>
                            ) : null}
                          </>
                        ) : (
                          <p className="text-xs text-amber-700">Em aberto</p>
                        )}
                      </div>
                      {canEdit ? (
                        <div className="flex shrink-0 flex-col items-end gap-1">
                          {a.return_date ? (
                            <>
                              <button
                                type="button"
                                onClick={() => startEditReturn(a)}
                                className="text-xs text-indigo-600 hover:underline"
                              >
                                Editar devolução
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirm({ type: "return", id: a.id })}
                                className="text-xs text-red-600 hover:underline"
                              >
                                Excluir devolução
                              </button>
                            </>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => setConfirm({ type: "assignment", id: a.id })}
                            className="text-xs text-red-600 hover:underline"
                          >
                            Excluir movimentação
                          </button>
                        </div>
                      ) : null}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {tab === "inspections" ? (
          <div className="space-y-6">
            {canEdit ? (
              <div className="grid gap-3 rounded-lg border border-slate-200 p-4 sm:grid-cols-3">
                <input id="insp-type" placeholder="Tipo (ensaio, CA, calibração…)" className="rounded border px-3 py-2 text-sm" />
                <input id="insp-date" type="date" className="rounded border px-3 py-2 text-sm" />
                <input id="insp-months" type="number" min={1} placeholder="Validade (meses)" className="rounded border px-3 py-2 text-sm" />
                <button
                  type="button"
                  onClick={() => void handleNewInspection()}
                  className="rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white sm:col-span-3"
                >
                  Adicionar ensaio
                </button>
              </div>
            ) : null}
            <ul className="space-y-3">
              {detail.inspections.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div>
                    <p className="font-medium">{i.inspection_type}</p>
                    <p className="text-xs text-slate-500">
                      {i.inspection_date}
                      {i.expiration_date ? ` → validade ${i.expiration_date}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {i.expiration_date && i.expiration_alert ? (
                      <AssetExpirationBadge show level={i.expiration_alert} date={i.expiration_date} />
                    ) : null}
                    {canEdit ? (
                      <button
                        type="button"
                        onClick={() => setConfirm({ type: "inspection", id: i.id })}
                        className="text-xs text-red-600 hover:underline"
                      >
                        Excluir
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {tab === "files" ? (
          <div className="space-y-4">
            {canEdit ? (
              <div className="flex flex-wrap items-end gap-2">
                <select id="upload-type" className="rounded border px-3 py-2 text-sm">
                  {ATTACHMENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <input
                  type="file"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    const t = (document.getElementById("upload-type") as HTMLSelectElement).value as AssetAttachmentType;
                    if (f) void handleUpload(f, t);
                    e.target.value = "";
                  }}
                  className="text-sm"
                />
              </div>
            ) : null}
            <ul className="divide-y divide-slate-100 text-sm">
              {detail.attachments.map((a) => (
                <li key={a.id} className="flex items-center justify-between py-2">
                  <span>
                    {a.file_name} <span className="text-xs text-slate-400">({a.file_type})</span>
                  </span>
                  <div className="flex gap-2">
                    {a.download_url ? (
                      <button
                        type="button"
                        onClick={() => void handleDownload(a.download_url!, a.file_name)}
                        className="text-indigo-600 hover:underline"
                      >
                        Baixar
                      </button>
                    ) : null}
                    {canEdit ? (
                      <button
                        type="button"
                        onClick={() => setConfirm({ type: "attachment", id: a.id })}
                        className="text-red-600 hover:underline"
                      >
                        Excluir
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {tab === "timeline" ? (
          <ul className="space-y-4 border-l-2 border-slate-200 pl-4">
            {detail.timeline.map((ev, idx) => (
              <li key={`${ev.kind}-${idx}`} className="relative text-sm">
                <span className="absolute -left-[1.35rem] top-1 h-2 w-2 rounded-full bg-indigo-500" />
                <p className="font-medium text-slate-900">{ev.title}</p>
                <p className="text-xs text-slate-500">{new Date(ev.at).toLocaleString("pt-BR")}</p>
                {ev.detail ? <p className="text-slate-600">{ev.detail}</p> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        title={
          confirm?.type === "asset"
            ? "Excluir ativo"
            : confirm?.type === "assignment"
              ? "Excluir movimentação"
              : confirm?.type === "return"
                ? "Excluir devolução"
                : confirm?.type === "inspection"
                  ? "Excluir ensaio"
                  : "Excluir anexo"
        }
        message="Esta ação será registrada no histórico. Deseja continuar?"
        onCancel={() => setConfirm(null)}
        onConfirm={() => void runConfirmDelete()}
        loading={confirmLoading}
      />
    </div>
  );
}
