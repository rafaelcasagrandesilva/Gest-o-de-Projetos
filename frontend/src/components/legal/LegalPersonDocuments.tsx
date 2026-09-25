import { useCallback, useEffect, useRef, useState } from "react";
import { usePermission } from "@/hooks/usePermission";
import { formatApiError } from "@/utils/apiError";
import { canPreviewInBrowser } from "@/utils/fileView";
import {
  LEGAL_PERSON_DOCUMENT_CATEGORIES,
  deactivateLegalPersonDocument,
  downloadLegalPersonDocument,
  listLegalPersonDocuments,
  uploadLegalPersonDocument,
  viewLegalPersonDocument,
  type LegalPersonDocument,
  type LegalPersonDocumentCategory,
} from "@/services/legal";

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Documentos do desligado (rescisão, multa 477, FGTS, contrato, ponto, comprovantes…).
 *
 * Usado na ficha (consulta) e no formulário de edição da Administração. O envio é imediato —
 * não depende do "Salvar" do formulário — e o arquivo vai para o volume persistente, como os
 * documentos de projeto. Abrir o arquivo exige Dados sensíveis (o backend também barra).
 */
export function LegalPersonDocuments({ personId, allowUpload = false }: { personId: string; allowUpload?: boolean }) {
  const hasUpdate = usePermission("legal_persons.update");
  const hasDelete = usePermission("legal_persons.delete");
  const canUpload = allowUpload && hasUpdate;
  const canRemove = allowUpload && (hasUpdate || hasDelete);
  const canOpen = usePermission("legal_persons.sensitive");

  const [docs, setDocs] = useState<LegalPersonDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [category, setCategory] = useState<LegalPersonDocumentCategory>("RESCISAO");
  const [title, setTitle] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDocs(await listLegalPersonDocuments(personId));
      setError(null);
    } catch (e) {
      setError(`Não foi possível carregar os documentos: ${formatApiError(e)}`);
    } finally {
      setLoading(false);
    }
  }, [personId]);
  useEffect(() => {
    void load();
  }, [load]);

  async function upload() {
    if (files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      // Vários arquivos de uma vez entram na mesma categoria; o título só vale para envio único.
      for (const file of files) {
        await uploadLegalPersonDocument(personId, {
          category,
          title: files.length === 1 ? title : undefined,
          file,
        });
      }
      setFiles([]);
      setTitle("");
      if (fileInput.current) fileInput.current.value = "";
      await load();
    } catch (e) {
      setError(`Não foi possível enviar o documento: ${formatApiError(e)}`);
      await load();
    } finally {
      setUploading(false);
    }
  }

  async function run(doc: LegalPersonDocument, action: () => Promise<void>, verb: string) {
    setBusyId(doc.id);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(`Não foi possível ${verb} o documento: ${formatApiError(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function remove(doc: LegalPersonDocument) {
    if (!window.confirm(`Remover o documento "${doc.title}"? Ele sai da lista, mas fica guardado no histórico.`)) return;
    await run(
      doc,
      async () => {
        await deactivateLegalPersonDocument(doc);
        setDocs((prev) => prev.filter((d) => d.id !== doc.id));
      },
      "remover",
    );
  }

  const inputCls =
    "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none";

  return (
    <div className="space-y-3">
      {canUpload ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] text-slate-500">Tipo</span>
              <select
                className={inputCls}
                value={category}
                onChange={(e) => setCategory(e.target.value as LegalPersonDocumentCategory)}
              >
                {LEGAL_PERSON_DOCUMENT_CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] text-slate-500">Descrição (opcional)</span>
              <input
                className={inputCls}
                value={title}
                disabled={files.length > 1}
                onChange={(e) => setTitle(e.target.value)}
                // Dentro do formulário de edição, Enter salvaria a pessoa inteira.
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.preventDefault();
                }}
                placeholder={files.length > 1 ? "Usa o nome de cada arquivo" : "ex.: TRCT assinado"}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] text-slate-500">Arquivo(s)</span>
              <input
                ref={fileInput}
                type="file"
                multiple
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
                className="text-xs text-slate-600 file:mr-2 file:rounded file:border-0 file:bg-slate-200 file:px-2 file:py-1 file:text-xs"
              />
            </label>
          </div>
          <div className="mt-2 flex justify-end">
            <button
              type="button"
              disabled={uploading || files.length === 0}
              onClick={() => void upload()}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {uploading ? "Enviando…" : files.length > 1 ? `Anexar ${files.length} arquivos` : "Anexar"}
            </button>
          </div>
        </div>
      ) : null}

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <p className="py-3 text-center text-sm text-slate-400">Carregando…</p>
      ) : docs.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-200 py-4 text-center text-sm text-slate-400">
          Nenhum documento anexado.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2 font-semibold">Tipo</th>
                <th className="px-3 py-2 font-semibold">Documento</th>
                <th className="px-3 py-2 font-semibold">Enviado</th>
                <th className="px-3 py-2 text-right font-semibold">Ações</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} className="border-b border-slate-100 last:border-0">
                  <td className="whitespace-nowrap px-3 py-2">
                    <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                      {d.category_label}
                    </span>
                  </td>
                  <td className="max-w-[240px] px-3 py-2">
                    <p className="truncate font-medium text-slate-800" title={d.title}>
                      {d.title}
                    </p>
                    {d.title !== d.original_filename ? (
                      <p className="truncate text-xs text-slate-400" title={d.original_filename}>
                        {d.original_filename}
                      </p>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-500">
                    {new Date(d.uploaded_at).toLocaleDateString("pt-BR")} · {formatSize(d.size_bytes)}
                    {d.uploaded_by_email ? <span className="block text-slate-400">{d.uploaded_by_email}</span> : null}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    {canOpen && canPreviewInBrowser(d.content_type, d.original_filename) ? (
                      <button
                        type="button"
                        disabled={busyId === d.id}
                        onClick={() => void run(d, () => viewLegalPersonDocument(d), "abrir")}
                        className="rounded px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                      >
                        Ver
                      </button>
                    ) : null}
                    {canOpen ? (
                      <button
                        type="button"
                        disabled={busyId === d.id}
                        onClick={() => void run(d, () => downloadLegalPersonDocument(d), "baixar")}
                        className="rounded px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                      >
                        Baixar
                      </button>
                    ) : (
                      <span className="text-xs text-slate-400" title="Abrir documentos exige Dados sensíveis">
                        restrito
                      </span>
                    )}
                    {canRemove ? (
                      <button
                        type="button"
                        disabled={busyId === d.id}
                        onClick={() => void remove(d)}
                        className="ml-1 rounded px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                      >
                        Remover
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
