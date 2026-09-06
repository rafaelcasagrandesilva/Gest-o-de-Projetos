import { hydrateBlobError } from "@/utils/apiError";
import { saveBlobAsFile, viewFileInNewTab } from "@/utils/fileView";

import { api } from "./api";

/** Comprovante anexado a um lançamento variável (reembolso, ajuda de custo, …). */
export interface PaymentComponentAttachment {
  id: string;
  component_id: string;
  file_name: string;
  mime_type: string | null;
  size_bytes: number;
  created_at: string;
  download_url: string;
}

/** Espelha a allowlist do backend (`PaymentComponentAttachmentService.ALLOWED_SUFFIXES`). */
export const ATTACHMENT_ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif,.gif,.xml";
/** Espelha `PAYMENT_COMPONENT_ATTACHMENT_MAX_BYTES` — barra o arquivo antes de subir. */
export const ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;
/** Espelha `MAX_FILES_PER_UPLOAD` do backend — teto de arquivos por envio. */
export const ATTACHMENT_MAX_FILES = 20;

export function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

export async function fetchComponentAttachments(
  componentId: string,
): Promise<PaymentComponentAttachment[]> {
  const { data } = await api.get<PaymentComponentAttachment[]>(
    `/payment-variable-components/${componentId}/attachments`,
  );
  return data;
}

/** Envia o LOTE de arquivos numa requisição (o backend recusa tudo se um for inválido). */
export async function uploadComponentAttachments(
  componentId: string,
  files: File[],
): Promise<PaymentComponentAttachment[]> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const { data } = await api.post<PaymentComponentAttachment[]>(
    `/payment-variable-components/${componentId}/attachments`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

/** Busca o arquivo (blob autenticado) — base do "Ver" e do "Baixar". */
export async function fetchComponentAttachmentBlob(
  att: PaymentComponentAttachment,
): Promise<Blob> {
  try {
    const resp = await api.get<Blob>(
      `/payment-variable-components/${att.component_id}/attachments/${att.id}/download`,
      { responseType: "blob" },
    );
    return resp.data;
  } catch (e) {
    throw await hydrateBlobError(e);
  }
}

/** Abre o comprovante numa nova aba (sem baixar). */
export async function viewComponentAttachment(
  att: PaymentComponentAttachment,
): Promise<void> {
  await viewFileInNewTab(() => fetchComponentAttachmentBlob(att));
}

/** Baixa o comprovante e salva com o nome original. */
export async function downloadComponentAttachment(
  att: PaymentComponentAttachment,
): Promise<void> {
  saveBlobAsFile(await fetchComponentAttachmentBlob(att), att.file_name);
}

export async function deleteComponentAttachment(
  componentId: string,
  attachmentId: string,
): Promise<void> {
  await api.delete(`/payment-variable-components/${componentId}/attachments/${attachmentId}`);
}
