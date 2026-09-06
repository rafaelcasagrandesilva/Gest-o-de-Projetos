import { useCallback, useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_MAX_BYTES,
  ATTACHMENT_MAX_FILES,
  deleteComponentAttachment,
  downloadComponentAttachment,
  fetchComponentAttachments,
  formatFileSize,
  uploadComponentAttachments,
  viewComponentAttachment,
  type PaymentComponentAttachment,
} from "@/services/paymentComponentAttachments";
import { canPreviewInBrowser } from "@/utils/fileView";

const ACCEPTED = ATTACHMENT_ACCEPT.split(",");

/** Recusa localmente o que o backend recusaria — o usuário sabe na hora, sem round-trip. */
function rejectionReason(file: File): string | null {
  const dot = file.name.lastIndexOf(".");
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!ACCEPTED.includes(ext)) return `${file.name}: formato não aceito.`;
  if (file.size > ATTACHMENT_MAX_BYTES)
    return `${file.name}: acima de ${ATTACHMENT_MAX_BYTES / (1024 * 1024)} MB.`;
  if (file.size === 0) return `${file.name}: arquivo vazio.`;
  return null;
}

/**
 * Painel de comprovantes de UM lançamento variável — aberto pelo clipe da linha, some ao
 * fechar (a lista volta a ter a mesma altura de antes, mesmo com dezenas de reembolsos).
 *
 * Dois modos, porque a linha pode ainda não existir no banco:
 * - lançamento já salvo (`componentId`): sobe na hora e mostra o que está no servidor;
 * - linha nova: os arquivos ficam numa FILA local e sobem junto com o salvamento do
 *   conjunto (quem salva é o pai, que aí já tem o id do lançamento).
 */
export function ComponentAttachmentsPanel({
  componentId,
  pendingFiles,
  readOnly = false,
  onPendingChange,
  onCountChange,
}: {
  componentId: string | null;
  pendingFiles: File[];
  readOnly?: boolean;
  onPendingChange: (files: File[]) => void;
  onCountChange: (count: number) => void;
}) {
  const [items, setItems] = useState<PaymentComponentAttachment[]>([]);
  const [loading, setLoading] = useState(componentId !== null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (componentId === null) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const rows = await fetchComponentAttachments(componentId);
      setItems(rows);
      onCountChange(rows.length);
      setError(null);
    } catch {
      setError("Não foi possível carregar os comprovantes.");
    } finally {
      setLoading(false);
    }
    // onCountChange vem do pai e muda a cada render; incluí-lo re-buscaria em loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [componentId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function accept(files: File[]) {
    if (files.length === 0) return;
    const bad = files.map(rejectionReason).find((r) => r !== null);
    if (bad) {
      setError(bad);
      return;
    }
    // Linha nova: a fila inteira sobe numa requisição só, então o teto vale sobre ela.
    const noEnvio = componentId === null ? pendingFiles.length + files.length : files.length;
    if (noEnvio > ATTACHMENT_MAX_FILES) {
      setError(`Envie no máximo ${ATTACHMENT_MAX_FILES} arquivos por vez.`);
      return;
    }
    setError(null);
    if (componentId === null) {
      onPendingChange([...pendingFiles, ...files]);
      return;
    }
    setBusy(true);
    try {
      const saved = await uploadComponentAttachments(componentId, files);
      const next = [...items, ...saved];
      setItems(next);
      onCountChange(next.length);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível enviar o arquivo.");
    } finally {
      setBusy(false);
    }
  }

  async function removeSaved(att: PaymentComponentAttachment) {
    if (componentId === null) return;
    setBusy(true);
    try {
      await deleteComponentAttachment(componentId, att.id);
      const next = items.filter((x) => x.id !== att.id);
      setItems(next);
      onCountChange(next.length);
      setError(null);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível excluir o comprovante.");
    } finally {
      setBusy(false);
    }
  }

  async function view(att: PaymentComponentAttachment) {
    try {
      await viewComponentAttachment(att);
      setError(null);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível abrir o comprovante.");
    }
  }

  async function download(att: PaymentComponentAttachment) {
    try {
      await downloadComponentAttachment(att);
      setError(null);
    } catch (e) {
      setError(isAxiosError(e) ? formatApiError(e) : "Não foi possível baixar o comprovante.");
    }
  }

  return (
    <div className="mt-1 w-full rounded-lg border border-slate-200 bg-white p-2.5">
      {!readOnly && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void accept(Array.from(e.dataTransfer.files));
          }}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded border border-dashed px-3 py-2 text-center text-[11px] ${
            dragging
              ? "border-emerald-400 bg-emerald-50 text-emerald-800"
              : "border-slate-300 text-slate-500 hover:border-emerald-300 hover:text-emerald-700"
          }`}
        >
          {busy ? "Enviando…" : "Arraste os comprovantes aqui ou clique para selecionar"}
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ATTACHMENT_ACCEPT}
            className="hidden"
            onChange={(e) => {
              void accept(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
        </div>
      )}

      {error && <p className="mt-2 text-[11px] text-red-700">{error}</p>}

      {loading ? (
        <p className="mt-2 text-[11px] text-slate-500">Carregando comprovantes…</p>
      ) : (
        <ul className="mt-2 space-y-1">
          {items.map((att) => (
            <li key={att.id} className="flex items-center gap-2 text-[11px] text-slate-700">
              <span className="min-w-0 flex-1 truncate" title={att.file_name}>
                {att.file_name}
              </span>
              <span className="shrink-0 text-slate-400">{formatFileSize(att.size_bytes)}</span>
              {canPreviewInBrowser(att.mime_type, att.file_name) && (
                <button
                  type="button"
                  onClick={() => void view(att)}
                  className="shrink-0 rounded px-1.5 py-0.5 text-indigo-700 hover:bg-indigo-50"
                >
                  Ver
                </button>
              )}
              <button
                type="button"
                onClick={() => void download(att)}
                className="shrink-0 rounded px-1.5 py-0.5 text-emerald-800 hover:bg-emerald-50"
              >
                Baixar
              </button>
              {!readOnly && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void removeSaved(att)}
                  className="shrink-0 rounded px-1.5 py-0.5 text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  Excluir
                </button>
              )}
            </li>
          ))}

          {pendingFiles.map((file, idx) => (
            <li
              key={`${file.name}-${idx}`}
              className="flex items-center gap-2 text-[11px] text-amber-800"
            >
              <span className="min-w-0 flex-1 truncate" title={file.name}>
                {file.name}
              </span>
              <span className="shrink-0 text-amber-600">{formatFileSize(file.size)}</span>
              <span className="shrink-0 italic text-amber-600">envia ao salvar</span>
              {!readOnly && (
                <button
                  type="button"
                  onClick={() => onPendingChange(pendingFiles.filter((_, i) => i !== idx))}
                  className="shrink-0 rounded px-1.5 py-0.5 text-red-700 hover:bg-red-50"
                >
                  Remover
                </button>
              )}
            </li>
          ))}

          {items.length === 0 && pendingFiles.length === 0 && (
            <li className="text-[11px] text-slate-500">Nenhum comprovante anexado.</li>
          )}
        </ul>
      )}
    </div>
  );
}
