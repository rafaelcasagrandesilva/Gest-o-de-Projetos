import { useCallback, useEffect, useRef, useState } from "react";
import { formatApiError } from "@/utils/apiError";
import { canPreviewInBrowser } from "@/utils/fileView";
import { ATTACHMENT_ACCEPT, formatFileSize } from "@/services/paymentComponentAttachments";
import {
  downloadAdvanceBatchAttachment,
  listAdvanceBatchAttachments,
  viewAdvanceBatchAttachment,
  type AdvanceBatchAttachment,
} from "@/services/receivableAdvanceBatches";

/** Mudanças nos documentos que só valem ao clicar em Salvar (criação ou edição da operação). */
export interface PendingDocChanges {
  adds: File[];
  removals: string[]; // ids de documentos já gravados
}

export const EMPTY_DOC_CHANGES: PendingDocChanges = { adds: [], removals: [] };

/**
 * Documentos da operação (borderô/termo da instituição).
 *
 * - Sem `changes`: CONSULTA — Ver / Baixar (detalhe da operação, caixa da lista).
 * - Com `changes` + `onChangesChange`: EDIÇÃO — adicionar e remover ficam PENDENTES e só são
 *   gravados quando o usuário clica em Salvar (quem aplica é o formulário da operação).
 *   `batchId` nulo = operação ainda não criada (só há documentos a adicionar).
 */
export function AdvanceBatchDocuments({
  batchId,
  changes,
  onChangesChange,
}: {
  batchId: string | null;
  changes?: PendingDocChanges;
  onChangesChange?: (next: PendingDocChanges) => void;
}) {
  const editable = Boolean(changes && onChangesChange);
  const [items, setItems] = useState<AdvanceBatchAttachment[] | null>(batchId ? null : []);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!batchId) return;
    try {
      setItems(await listAdvanceBatchAttachments(batchId));
    } catch (e) {
      setError(formatApiError(e));
      setItems([]);
    }
  }, [batchId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function open(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(formatApiError(e));
    }
  }

  const removals = new Set(changes?.removals ?? []);
  const adds = changes?.adds ?? [];
  const btn = "rounded border px-2 py-0.5 text-xs font-medium";

  return (
    <section className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Documentos da operação</p>
        {editable ? (
          <>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ATTACHMENT_ACCEPT}
              className="hidden"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                e.target.value = "";
                if (files.length && changes && onChangesChange) {
                  onChangesChange({ ...changes, adds: [...changes.adds, ...files] });
                }
              }}
            />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className={`${btn} border-indigo-200 bg-indigo-50 text-indigo-800 hover:bg-indigo-100`}
            >
              📎 Adicionar documento
            </button>
          </>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="mt-2 rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-800">
          {error}
        </p>
      ) : null}

      {items === null ? (
        <p className="mt-2 text-slate-500">Carregando…</p>
      ) : items.length === 0 && adds.length === 0 ? (
        <p className="mt-2 text-slate-500">
          {editable ? "Nenhum documento. Borderô/termo da instituição (PDF)." : "Nenhum documento anexado."}
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100">
          {items.map((att) => {
            const removing = removals.has(att.id);
            return (
              <li key={att.id} className="flex items-center justify-between gap-3 py-1.5">
                <span className="min-w-0">
                  <span
                    className={`block truncate font-medium ${removing ? "text-slate-400 line-through" : "text-slate-800"}`}
                    title={att.file_name}
                  >
                    {att.file_name}
                  </span>
                  <span className="text-xs text-slate-500">
                    {removing ? <span className="text-red-700">será removido ao salvar</span> : formatFileSize(att.size_bytes)}
                  </span>
                </span>
                <span className="flex shrink-0 gap-2">
                  {canPreviewInBrowser(att.mime_type, att.file_name) ? (
                    <button
                      type="button"
                      onClick={() => void open(() => viewAdvanceBatchAttachment(att))}
                      className={`${btn} border-indigo-200 bg-indigo-50 text-indigo-800 hover:bg-indigo-100`}
                    >
                      Ver
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void open(() => downloadAdvanceBatchAttachment(att))}
                    className={`${btn} border-slate-200 bg-white text-slate-700 hover:bg-slate-50`}
                  >
                    Baixar
                  </button>
                  {editable && changes && onChangesChange ? (
                    <button
                      type="button"
                      onClick={() =>
                        onChangesChange({
                          ...changes,
                          removals: removing
                            ? changes.removals.filter((id) => id !== att.id)
                            : [...changes.removals, att.id],
                        })
                      }
                      className={`${btn} border-transparent ${removing ? "text-slate-700 hover:bg-slate-50" : "text-red-700 hover:bg-red-50"}`}
                    >
                      {removing ? "Desfazer" : "Remover"}
                    </button>
                  ) : null}
                </span>
              </li>
            );
          })}
          {adds.map((f, i) => (
            <li key={`novo-${i}-${f.name}`} className="flex items-center justify-between gap-3 py-1.5">
              <span className="min-w-0">
                <span className="block truncate font-medium text-slate-800" title={f.name}>
                  {f.name}
                </span>
                <span className="text-xs text-emerald-700">será anexado ao salvar · {formatFileSize(f.size)}</span>
              </span>
              {changes && onChangesChange ? (
                <button
                  type="button"
                  onClick={() => onChangesChange({ ...changes, adds: changes.adds.filter((_, j) => j !== i) })}
                  className={`${btn} border-transparent text-slate-700 hover:bg-slate-50`}
                >
                  Desfazer
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Caixa só com os documentos (aberta pelo "📎 Anexo (n)" da lista de operações). */
export function AdvanceBatchDocumentsDialog({
  batchId,
  title,
  onClose,
}: {
  batchId: string;
  title: string;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Documentos da operação"
      onClick={onClose}
    >
      <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Fechar">
            ✕
          </button>
        </div>
        <AdvanceBatchDocuments batchId={batchId} />
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}
