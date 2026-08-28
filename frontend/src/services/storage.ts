import { api } from "./api";

export interface MissingFile {
  tipo: string;
  onde: string;
  titulo: string;
  arquivo: string;
  enviado_em: string;
  caminho: string;
  existe: boolean;
}

export interface MissingFilesReport {
  /** Diretório em uso por tipo de anexo (chave = variável de ambiente). */
  diretorios: Record<string, string>;
  raiz: string;
  resumo: { tipo: string; total: number; ausentes: number }[];
  total_ausentes: number;
  total_registros: number;
  ausentes: MissingFile[];
}

/** Anexos registrados no banco cujo arquivo não está no disco do servidor. */
export async function fetchMissingFilesReport(): Promise<MissingFilesReport> {
  const { data } = await api.get<MissingFilesReport>("/admin/storage/missing-files");
  return data;
}
