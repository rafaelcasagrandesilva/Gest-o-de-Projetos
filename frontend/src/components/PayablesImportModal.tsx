import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isAxiosError } from "axios";
import {
  analyzePayablesImport,
  confirmPayablesImportLegacy,
  confirmPayablesImportMapped,
  createCostCenterAlias,
  createPayablesImportTemplate,
  deletePayablesImportTemplate,
  listPayablesImportTemplates,
  previewPayablesImportLegacy,
  previewPayablesImportMapped,
  scanPayablesImportCostCenters,
  type PayableImportAnalyzeResult,
  type PayableImportColumnMapping,
  type PayableImportConfirmResult,
  type PayableImportCostCenterScanResult,
  type PayableImportPreviewResult,
  type PayableImportRowStatus,
  type PayableImportTemplate,
} from "@/services/payables";
import { formatApiError } from "@/utils/apiError";

type Props = {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
};

type Step = "upload" | "mapping" | "resolve" | "preview" | "done";

const EMPTY_MAPPING: PayableImportColumnMapping = {
  name: null,
  cost_center: null,
  due_date: null,
  amount: null,
  category: null,
  observation: null,
};

const MAPPING_FIELDS: {
  key: keyof PayableImportColumnMapping;
  label: string;
  required: boolean;
}[] = [
  { key: "name", label: "Nome / descrição", required: true },
  { key: "cost_center", label: "Centro de custo", required: true },
  { key: "due_date", label: "Vencimento", required: true },
  { key: "amount", label: "Valor", required: true },
  { key: "category", label: "Categoria", required: false },
  { key: "observation", label: "Observação", required: false },
];

function formatBRL(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDateBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function statusLabel(status: PayableImportRowStatus): string {
  if (status === "valid") return "OK";
  if (status === "duplicate") return "Duplicado";
  if (status === "error") return "Erro";
  return "Vazio";
}

function statusClass(status: PayableImportRowStatus): string {
  if (status === "valid") return "bg-emerald-100 text-emerald-900";
  if (status === "duplicate") return "bg-amber-100 text-amber-900";
  if (status === "error") return "bg-red-100 text-red-900";
  return "bg-slate-50 text-slate-500";
}

function mappingComplete(m: PayableImportColumnMapping): boolean {
  return Boolean(m.name && m.cost_center && m.due_date && m.amount);
}

export function PayablesImportModal({ open, onClose, onImported }: Props) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [headerRow, setHeaderRow] = useState(1);
  const [analyze, setAnalyze] = useState<PayableImportAnalyzeResult | null>(null);
  const [mapping, setMapping] = useState<PayableImportColumnMapping>(EMPTY_MAPPING);
  const [preview, setPreview] = useState<PayableImportPreviewResult | null>(null);
  const [result, setResult] = useState<PayableImportConfirmResult | null>(null);
  const [templates, setTemplates] = useState<PayableImportTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [saveTemplateName, setSaveTemplateName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useLegacyQuick, setUseLegacyQuick] = useState(false);
  const [costCenterScan, setCostCenterScan] = useState<PayableImportCostCenterScanResult | null>(null);
  const [costCenterResolutions, setCostCenterResolutions] = useState<Record<string, string>>({});
  const [saveAliasFlags, setSaveAliasFlags] = useState<Record<string, boolean>>({});

  const loadTemplates = useCallback(async () => {
    try {
      const list = await listPayablesImportTemplates();
      setTemplates(list);
    } catch {
      setTemplates([]);
    }
  }, []);

  useEffect(() => {
    if (open) void loadTemplates();
  }, [open, loadTemplates]);

  function reset() {
    setStep("upload");
    setFile(null);
    setHeaderRow(1);
    setAnalyze(null);
    setMapping(EMPTY_MAPPING);
    setPreview(null);
    setResult(null);
    setSelectedTemplateId("");
    setSaveTemplateName("");
    setError(null);
    setUseLegacyQuick(false);
    setCostCenterScan(null);
    setCostCenterResolutions({});
    setSaveAliasFlags({});
    if (fileRef.current) fileRef.current.value = "";
  }

  function handleClose() {
    reset();
    onClose();
  }

  function onFileChange(f: File | null) {
    setFile(f);
    setAnalyze(null);
    setPreview(null);
    setResult(null);
    setError(null);
    setStep("upload");
  }

  const columnOptions = useMemo(() => {
    const cols = analyze?.columns ?? [];
    return ["", ...cols];
  }, [analyze]);

  async function runAnalyze() {
    if (!file) {
      setError("Selecione um arquivo .xlsx ou .csv.");
      return;
    }
    setBusy(true);
    setError(null);
    setPreview(null);
    setResult(null);
    try {
      if (useLegacyQuick) {
        const data = await previewPayablesImportLegacy(file);
        setPreview(data);
        setStep("preview");
        return;
      }
      const data = await analyzePayablesImport(file, headerRow);
      setAnalyze(data);
      setMapping({
        ...EMPTY_MAPPING,
        ...data.suggested_mapping,
      });
      setHeaderRow(data.header_row);
      setStep("mapping");
    } catch (e) {
      setAnalyze(null);
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível ler a planilha.");
    } finally {
      setBusy(false);
    }
  }

  function applyTemplate(templateId: string) {
    const tpl = templates.find((t) => t.id === templateId);
    if (!tpl) return;
    setSelectedTemplateId(templateId);
    setHeaderRow(tpl.header_row);
    setMapping({ ...EMPTY_MAPPING, ...tpl.column_mapping });
  }

  async function runMappedPreviewWithResolutions(resolutions: Record<string, string>) {
    if (!file) return;
    const data = await previewPayablesImportMapped(file, headerRow, mapping, resolutions);
    setCostCenterResolutions(resolutions);
    setPreview(data);
    setStep("preview");
  }

  async function proceedAfterMapping() {
    if (!file) {
      setError("Selecione um arquivo.");
      return;
    }
    if (!mappingComplete(mapping)) {
      setError("Mapeie todos os campos obrigatórios antes de continuar.");
      return;
    }
    setBusy(true);
    setError(null);
    setPreview(null);
    try {
      const scan = await scanPayablesImportCostCenters(file, headerRow, mapping);
      setCostCenterScan(scan);
      if (scan.unknown_centers.length > 0) {
        const initialRes: Record<string, string> = {};
        const initialAlias: Record<string, boolean> = {};
        for (const src of scan.unknown_centers) {
          initialRes[src] = costCenterResolutions[src] ?? "";
          initialAlias[src] = saveAliasFlags[src] ?? true;
        }
        setCostCenterResolutions(initialRes);
        setSaveAliasFlags(initialAlias);
        setStep("resolve");
        return;
      }
      await runMappedPreviewWithResolutions({});
    } catch (e) {
      setPreview(null);
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível analisar centros de custo.");
    } finally {
      setBusy(false);
    }
  }

  async function runContinueFromResolve() {
    if (!file || !costCenterScan) return;
    for (const src of costCenterScan.unknown_centers) {
      if (!costCenterResolutions[src]?.trim()) {
        setError(`Selecione o centro de custo SGP para «${src}».`);
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      for (const src of costCenterScan.unknown_centers) {
        if (saveAliasFlags[src]) {
          await createCostCenterAlias({
            alias_name: src,
            target_cost_center: costCenterResolutions[src],
          });
        }
      }
      await runMappedPreviewWithResolutions(costCenterResolutions);
    } catch (e) {
      setPreview(null);
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível aplicar as resoluções.");
    } finally {
      setBusy(false);
    }
  }

  async function runConfirm() {
    if (!file) return;
    if (!preview || preview.valid_count === 0) {
      setError("Não há linhas válidas para importar.");
      return;
    }
    const ok = window.confirm(
      `Importar ${preview.valid_count} lançamento(s) manual(is)?\n\nDuplicatas e erros serão ignorados.`,
    );
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      const data = useLegacyQuick
        ? await confirmPayablesImportLegacy(file)
        : await confirmPayablesImportMapped(file, headerRow, mapping, costCenterResolutions);
      setResult(data);
      setStep("done");
      onImported();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Falha na importação.");
    } finally {
      setBusy(false);
    }
  }

  async function saveTemplate() {
    const name = saveTemplateName.trim();
    if (!name) {
      setError("Informe um nome para o modelo.");
      return;
    }
    if (!mappingComplete(mapping)) {
      setError("Mapeie os campos obrigatórios antes de salvar o modelo.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createPayablesImportTemplate({
        name,
        header_row: headerRow,
        column_mapping: mapping,
      });
      setSaveTemplateName("");
      await loadTemplates();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar o modelo.");
    } finally {
      setBusy(false);
    }
  }

  async function removeTemplate(id: string) {
    if (!window.confirm("Excluir este modelo de importação?")) return;
    setBusy(true);
    try {
      await deletePayablesImportTemplate(id);
      if (selectedTemplateId === id) setSelectedTemplateId("");
      await loadTemplates();
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível excluir o modelo.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  const stepLabels: Record<Step, string> = {
    upload: "1. Upload",
    mapping: "2. Mapeamento",
    resolve: "3. Resolver centros",
    preview: "4. Preview",
    done: "5. Concluído",
  };

  const stepOrder: Step[] = useLegacyQuick
    ? ["upload", "preview", "done"]
    : ["upload", "mapping", "resolve", "preview", "done"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="pay-import-title"
        className="flex max-h-[92vh] w-full max-w-5xl flex-col rounded-xl border border-slate-200 bg-white shadow-lg"
      >
        <div className="border-b border-slate-100 px-6 py-4">
          <h3 id="pay-import-title" className="text-lg font-semibold text-slate-900">
            Importar planilha — Contas a pagar
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            Todos os lançamentos importados serão do tipo <strong>MANUAL</strong>.
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            {stepOrder.map((s) => (
              <span
                key={s}
                className={`rounded-full px-2.5 py-0.5 font-medium ${
                  step === s ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                {stepLabels[s]}
              </span>
            ))}
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
          {error ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
          ) : null}

          {step === "done" && result ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950">
              <p className="font-medium">Importação concluída</p>
              <ul className="mt-2 list-inside list-disc space-y-1">
                <li>{result.imported} importado(s)</li>
                <li>{result.skipped_duplicate} duplicado(s) ignorado(s)</li>
                <li>{result.skipped_empty} linha(s) vazia(s) ignorada(s)</li>
                <li>{result.errors} erro(s)</li>
              </ul>
              {result.error_details.length > 0 ? (
                <ul className="mt-2 max-h-32 overflow-y-auto text-xs">
                  {result.error_details.map((msg) => (
                    <li key={msg}>{msg}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {(step === "upload" || step === "mapping") && (
            <label className="flex flex-col gap-2 text-sm">
              <span className="font-medium text-slate-700">Arquivo (.xlsx ou .csv)</span>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                disabled={busy}
                onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
              />
              {file ? <span className="text-xs text-slate-500">{file.name}</span> : null}
            </label>
          )}

          {step === "upload" && (
            <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/80 p-4 text-sm">
              <label className="flex max-w-xs flex-col gap-1">
                <span className="font-medium text-slate-700">Linha do cabeçalho</span>
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={headerRow}
                  disabled={useLegacyQuick || busy}
                  onChange={(e) => setHeaderRow(Math.max(1, Number(e.target.value) || 1))}
                  className="rounded border border-slate-300 px-2 py-1.5"
                />
              </label>
              <label className="flex items-center gap-2 text-slate-700">
                <input
                  type="checkbox"
                  checked={useLegacyQuick}
                  onChange={(e) => setUseLegacyQuick(e.target.checked)}
                  disabled={busy}
                />
                Importação rápida (modelo fixo colunas A–F — compatível com planilha antiga)
              </label>
            </div>
          )}

          {step === "mapping" && analyze ? (
            <div className="space-y-4">
              <p className="text-sm text-slate-600">
                {analyze.total_data_rows} linha(s) de dados detectada(s).
                {analyze.detected_legacy_template
                  ? " Esta planilha parece o modelo antigo (A–F); você pode usar a importação rápida no passo anterior."
                  : null}
              </p>

              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1 text-sm">
                  <span className="font-medium text-slate-700">Linha do cabeçalho</span>
                  <input
                    type="number"
                    min={1}
                    max={500}
                    value={headerRow}
                    disabled={busy}
                    onChange={(e) => setHeaderRow(Math.max(1, Number(e.target.value) || 1))}
                    className="w-24 rounded border border-slate-300 px-2 py-1.5"
                  />
                </label>
                <button
                  type="button"
                  disabled={busy || !file}
                  onClick={() => void runAnalyze()}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                >
                  Reanalisar
                </button>
              </div>

              {templates.length > 0 ? (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-sm">
                    <span className="font-medium text-slate-700">Modelo salvo</span>
                    <select
                      value={selectedTemplateId}
                      onChange={(e) => {
                        const id = e.target.value;
                        setSelectedTemplateId(id);
                        if (id) applyTemplate(id);
                      }}
                      className="rounded border border-slate-300 px-2 py-1.5"
                    >
                      <option value="">— Selecionar —</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {selectedTemplateId ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void removeTemplate(selectedTemplateId)}
                      className="rounded border border-red-200 px-3 py-1.5 text-sm text-red-800 hover:bg-red-50"
                    >
                      Excluir modelo
                    </button>
                  ) : null}
                </div>
              ) : null}

              <div className="grid gap-3 sm:grid-cols-2">
                {MAPPING_FIELDS.map(({ key, label, required }) => (
                  <label key={key} className="flex flex-col gap-1 text-sm">
                    <span className="font-medium text-slate-700">
                      {label}
                      {required ? " *" : ""}
                    </span>
                    <select
                      value={mapping[key] ?? ""}
                      onChange={(e) =>
                        setMapping((m) => ({
                          ...m,
                          [key]: e.target.value || null,
                        }))
                      }
                      className="rounded border border-slate-300 px-2 py-1.5"
                    >
                      {columnOptions.map((col) => (
                        <option key={`${key}-${col || "none"}`} value={col}>
                          {col || "— Não mapear —"}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>

              <div className="rounded-lg border border-slate-200 p-3">
                <p className="text-xs font-medium uppercase text-slate-500">Amostra da planilha</p>
                <div className="mt-2 overflow-x-auto">
                  <table className="min-w-full text-left text-xs">
                    <thead>
                      <tr>
                        {analyze.columns.map((c) => (
                          <th key={c} className="whitespace-nowrap px-2 py-1 text-slate-600">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {analyze.sample_rows.map((row, i) => (
                        <tr key={i} className="border-t border-slate-100">
                          {analyze.columns.map((c) => (
                            <td key={c} className="max-w-[140px] truncate px-2 py-1" title={String(row[c] ?? "")}>
                              {String(row[c] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3">
                <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-sm">
                  <span className="font-medium text-slate-700">Salvar modelo de importação</span>
                  <input
                    value={saveTemplateName}
                    onChange={(e) => setSaveTemplateName(e.target.value)}
                    placeholder="Ex.: Banco Grafeno"
                    className="rounded border border-slate-300 px-2 py-1.5"
                  />
                </label>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void saveTemplate()}
                  className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm text-indigo-900 hover:bg-indigo-100 disabled:opacity-50"
                >
                  Salvar modelo
                </button>
              </div>
            </div>
          ) : null}

          {step === "resolve" && costCenterScan ? (
            <div className="space-y-4">
              <p className="text-sm text-slate-600">
                {costCenterScan.unknown_centers.length} centro(s) de custo da planilha não foram reconhecidos.
                Associe cada um a um centro de custo do SGP. Opcionalmente salve como alias (DE-PARA) para
                importações futuras.
              </p>
              <ul className="space-y-4">
                {costCenterScan.unknown_centers.map((src) => (
                  <li
                    key={src}
                    className="rounded-lg border border-slate-200 bg-slate-50/60 p-4 text-sm"
                  >
                    <p className="font-medium text-slate-800">Centro encontrado na planilha</p>
                    <p className="mt-1 text-slate-700">«{src}»</p>
                    <label className="mt-3 flex flex-col gap-1">
                      <span className="font-medium text-slate-700">Centro de custo no SGP</span>
                      <select
                        value={costCenterResolutions[src] ?? ""}
                        onChange={(e) =>
                          setCostCenterResolutions((prev) => ({
                            ...prev,
                            [src]: e.target.value,
                          }))
                        }
                        className="rounded border border-slate-300 bg-white px-2 py-1.5"
                      >
                        <option value="">— Selecionar —</option>
                        {costCenterScan.available_targets.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="mt-3 flex items-center gap-2 text-slate-700">
                      <input
                        type="checkbox"
                        checked={saveAliasFlags[src] ?? false}
                        onChange={(e) =>
                          setSaveAliasFlags((prev) => ({
                            ...prev,
                            [src]: e.target.checked,
                          }))
                        }
                      />
                      Salvar como alias para próximas importações
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {step === "preview" && preview ? (
            <>
              <div className="flex flex-wrap gap-3 text-sm">
                <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-emerald-900">
                  Válidos: {preview.valid_count}
                </span>
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-slate-700">
                  Duplicados: {preview.duplicate_count}
                </span>
                <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-red-900">
                  Erros: {preview.error_count}
                </span>
                <span className="rounded-full bg-slate-50 px-2.5 py-0.5 text-slate-600">
                  Vazios: {preview.empty_count}
                </span>
              </div>
              <div className="max-h-[360px] overflow-auto rounded-lg border border-slate-200">
                <table className="min-w-full text-left text-xs">
                  <thead className="sticky top-0 bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-2 py-2">#</th>
                      <th className="px-2 py-2">Status</th>
                      <th className="px-2 py-2">Centro de custo</th>
                      <th className="px-2 py-2">Nome</th>
                      <th className="px-2 py-2">Vencimento</th>
                      <th className="px-2 py-2">Valor</th>
                      <th className="px-2 py-2">Categoria</th>
                      <th className="px-2 py-2">Mensagem</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {preview.rows.map((row) => {
                      const summaryBg =
                        row.status === "error"
                          ? "bg-red-50/70"
                          : row.status === "duplicate"
                            ? "bg-amber-50/70"
                            : "";
                      return (
                        <>
                          <tr key={`${row.line_number}-summary`} className={summaryBg}>
                            <td className="px-2 py-1.5 tabular-nums">{row.line_number}</td>
                            <td className="px-2 py-1.5">
                              <span
                                className={`rounded px-1.5 py-0.5 font-medium ${statusClass(row.status)}`}
                              >
                                {statusLabel(row.status)}
                              </span>
                            </td>
                            <td className="max-w-[100px] truncate px-2 py-1.5" title={row.cost_center ?? ""}>
                              {row.cost_center ?? "—"}
                            </td>
                            <td className="max-w-[140px] truncate px-2 py-1.5" title={row.name ?? ""}>
                              {row.name ?? "—"}
                            </td>
                            <td className="whitespace-nowrap px-2 py-1.5">{formatDateBr(row.due_date)}</td>
                            <td className="whitespace-nowrap px-2 py-1.5 tabular-nums">{formatBRL(row.amount)}</td>
                            <td className="max-w-[90px] truncate px-2 py-1.5">{row.category ?? "—"}</td>
                            <td
                              className="max-w-[160px] truncate px-2 py-1.5 text-slate-500"
                              title={row.message ?? ""}
                            >
                              {row.message ?? ""}
                            </td>
                          </tr>
                          <tr key={`${row.line_number}-detail`}>
                            <td colSpan={8} className="px-2 py-2 text-[11px] text-slate-700">
                              <div className="space-y-1">
                                <div>
                                  <span className="font-medium">Linha original:</span>{" "}
                                  <span>
                                    Fornecedor: {row.original_name ?? "—"}
                                    {" · "}
                                    Valor original: {row.original_amount ? `"${row.original_amount}"` : "—"}
                                    {" · "}
                                    Data original: {row.original_due_date ?? "—"}
                                    {" · "}
                                    Centro de custo (texto): {row.original_cost_center ?? "—"}
                                  </span>
                                </div>
                                <div>
                                  <span className="font-medium">Resultado convertido:</span>{" "}
                                  <span>
                                    Nome: {row.name ?? "—"}
                                    {" · "}
                                    Valor: {formatBRL(row.amount)}
                                    {" · "}
                                    Vencimento: {formatDateBr(row.due_date)}
                                    {" · "}
                                    Centro de custo final: {row.cost_center ?? "—"}
                                  </span>
                                </div>
                                {row.original_cost_center &&
                                row.cost_center &&
                                row.original_cost_center !== row.cost_center ? (
                                  <div className="text-slate-600">
                                    <span className="font-medium">Centro original:</span>{" "}
                                    {row.original_cost_center}
                                    {" · "}
                                    <span className="font-medium">Centro convertido:</span>{" "}
                                    {row.cost_center}
                                    {" · "}
                                    <span className="font-medium">Alias aplicado:</span>{" "}
                                    {row.alias_applied ? "Sim" : "Não"}
                                  </div>
                                ) : row.alias_applied ? (
                                  <div className="text-slate-600">
                                    <span className="font-medium">Alias aplicado:</span> Sim
                                  </div>
                                ) : null}
                                {row.message ? (
                                  <div className="text-slate-600">
                                    <span className="font-medium">Mensagem:</span> {row.message}
                                  </div>
                                ) : null}
                              </div>
                            </td>
                          </tr>
                        </>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>

        <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-6 py-4">
          <button
            type="button"
            disabled={busy}
            onClick={handleClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {step === "done" ? "Fechar" : "Cancelar"}
          </button>

          {step === "upload" ? (
            <button
              type="button"
              disabled={busy || !file}
              onClick={() => void runAnalyze()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? "Lendo arquivo…" : useLegacyQuick ? "Preview (modelo fixo)" : "Continuar"}
            </button>
          ) : null}

          {step === "mapping" ? (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => setStep("upload")}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm hover:bg-slate-50"
              >
                Voltar
              </button>
              <button
                type="button"
                disabled={busy || !mappingComplete(mapping)}
                onClick={() => void proceedAfterMapping()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {busy ? "Analisando…" : "Continuar"}
              </button>
            </>
          ) : null}

          {step === "resolve" ? (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => setStep("mapping")}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm hover:bg-slate-50"
              >
                Voltar
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void runContinueFromResolve()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {busy ? "Aplicando…" : "Ver preview"}
              </button>
            </>
          ) : null}

          {step === "preview" && !result ? (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  setStep(
                    useLegacyQuick
                      ? "upload"
                      : costCenterScan?.unknown_centers.length
                        ? "resolve"
                        : "mapping",
                  )
                }
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm hover:bg-slate-50"
              >
                Voltar
              </button>
              <button
                type="button"
                disabled={busy || !preview || preview.valid_count === 0}
                onClick={() => void runConfirm()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {busy ? "Importando…" : "Confirmar importação"}
              </button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
