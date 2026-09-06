/**
 * Abrir e salvar anexos — regra ÚNICA para todo arquivo do sistema (PDFs de NF, anexos de
 * ativo, documentos de projeto, comprovantes de pagamento variável).
 *
 * Todo download passa por requisição autenticada (o arquivo não é uma URL pública), então
 * "ver no navegador" é: baixar o blob e abri-lo numa aba. O detalhe que decide se funciona
 * é a ORDEM — a aba é aberta no clique, enquanto o gesto do usuário ainda vale, e só
 * depois recebe o endereço do blob. Abrir depois do await é o que faz o navegador tratar a
 * aba como pop-up e bloquear.
 */

/** Extensões que o navegador exibe na própria aba. Fora daqui, "Ver" não é oferecido. */
const PREVIEWABLE_SUFFIXES = [
  ".pdf",
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".gif",
  ".svg",
  ".bmp",
  ".txt",
  ".xml",
  ".csv",
];

/** O arquivo abre no navegador (PDF, imagem, texto) ou só faz sentido baixar (xlsx, docx…)? */
export function canPreviewInBrowser(mimeType: string | null | undefined, fileName?: string): boolean {
  const mime = (mimeType || "").toLowerCase();
  if (mime.startsWith("image/") || mime.startsWith("text/")) return true;
  if (mime === "application/pdf" || mime === "application/xml") return true;
  // Sem mime confiável (ou octet-stream genérico), decide pela extensão do nome.
  if (!mime || mime === "application/octet-stream") {
    const name = (fileName || "").toLowerCase();
    return PREVIEWABLE_SUFFIXES.some((ext) => name.endsWith(ext));
  }
  return false;
}

/** Libera o object URL depois de dar tempo de a aba/o download consumirem o blob. */
function revokeLater(url: string): void {
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/**
 * Abre o arquivo numa nova aba. `fetchBlob` é chamado DEPOIS de a aba existir, para o
 * navegador não tratar a abertura como pop-up.
 */
export async function viewFileInNewTab(fetchBlob: () => Promise<Blob>): Promise<void> {
  // Sem "noopener" aqui de propósito: com ele o navegador devolve null e não haveria como
  // apontar a aba para o blob. O vínculo é cortado logo abaixo, assim que o endereço é
  // definido.
  const tab = window.open("", "_blank");
  try {
    const blob = await fetchBlob();
    const url = URL.createObjectURL(blob);
    if (tab) {
      tab.opener = null;
      tab.location.replace(url);
    } else {
      // Pop-up bloqueado: tenta a abertura direta, que o usuário pode liberar no aviso.
      window.open(url, "_blank", "noopener,noreferrer");
    }
    revokeLater(url);
  } catch (e) {
    tab?.close();
    throw e;
  }
}

/** Salva o blob como arquivo, com o nome informado. */
export function saveBlobAsFile(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  revokeLater(url);
}
