import { useEffect, useState } from "react";
import { formatApiError } from "@/utils/apiError";
import { canPreviewInBrowser } from "@/utils/fileView";
import { formatFileSize, type PaymentComponentAttachment } from "@/services/paymentComponentAttachments";
import {
  downloadPayableAttachment,
  listPayableAttachments,
  viewPayableAttachment,
  type PayableSnapshotRow,
} from "@/services/payables";

/** Comprovantes de um título do Contas a Pagar — Ver (abre no navegador) e Baixar, como nas NFs. */
export function PayableAttachmentsModal({ row, onClose }: { row: PayableSnapshotRow; onClose: () => void }) {
  const [items, setItems] = useState<PaymentComponentAttachment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listPayableAttachments(row.id)
      .then((list) => alive && setItems(list))
      .catch((e) => alive && setError(formatApiError(e)));
    return () => {
      alive = false;
    };
  }, [row.id]);

  async function run(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(formatApiError(e));
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Comprovantes"
      onClick={onClose}
    >
      <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Comprovantes</h2>
            <p className="mt-0.5 text-sm text-slate-600">
              {row.name}
              {row.item_description ? ` · ${row.item_description}` : ""}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Fechar">
            ✕
          </button>
        </div>

        {error && (
          <div role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        )}

        {items === null && !error ? (
          <p className="mt-4 text-sm text-slate-500">Carregando…</p>
        ) : items && items.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">Nenhum comprovante anexado.</p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {(items ?? []).map((att) => (
              <li key={att.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium text-slate-800" title={att.file_name}>
                    {att.file_name}
                  </span>
                  <span className="text-xs text-slate-500">{formatFileSize(att.size_bytes)}</span>
                </span>
                <span className="flex shrink-0 gap-2">
                  {canPreviewInBrowser(att.mime_type, att.file_name) && (
                    <button
                      type="button"
                      onClick={() => void run(() => viewPayableAttachment(att))}
                      className="rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-800 hover:bg-indigo-100"
                    >
                      Ver
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void run(() => downloadPayableAttachment(att))}
                    className="rounded border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Baixar
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-5 flex justify-end">
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
