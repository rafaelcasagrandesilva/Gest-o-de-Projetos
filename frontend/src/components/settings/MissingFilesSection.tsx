import { useState } from "react";
import { formatApiError } from "@/utils/apiError";
import { fetchMissingFilesReport, type MissingFilesReport } from "@/services/storage";

/**
 * Anexos que existem no cadastro mas cujo arquivo não está no disco do servidor —
 * o que precisa ser reenviado depois de um redeploy que apagou uploads gravados
 * fora do volume persistente. Diagnóstico sob demanda: só consulta ao clicar.
 */
export function MissingFilesSection() {
  const [report, setReport] = useState<MissingFilesReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCheck() {
    setLoading(true);
    setError(null);
    try {
      setReport(await fetchMissingFilesReport());
    } catch (e) {
      setError(formatApiError(e));
      setReport(null);
    } finally {
      setLoading(false);
    }
  }

  function handleExportCsv() {
    if (!report) return;
    const linhas = [
      ["Tipo", "Onde", "Título", "Arquivo", "Enviado em", "Caminho esperado"],
      ...report.ausentes.map((a) => [a.tipo, a.onde, a.titulo, a.arquivo, a.enviado_em, a.caminho]),
    ];
    const csv = linhas.map((l) => l.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(";")).join("\r\n");
    const url = URL.createObjectURL(new Blob([`﻿${csv}`], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "arquivos-ausentes.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Arquivos ausentes no servidor</h3>
      <p className="mt-1 text-xs text-slate-500">
        Confere documentos de projeto, anexos de ativos e PDFs de NF contra o disco. Um anexo listado
        aqui aparece no cadastro, mas o arquivo não está no servidor — o download falha e ele precisa
        ser reenviado.
      </p>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          disabled={loading}
          onClick={() => void handleCheck()}
          className="rounded-lg bg-slate-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
        >
          {loading ? "Verificando…" : "Verificar arquivos"}
        </button>
        {report && report.ausentes.length > 0 && (
          <button
            type="button"
            onClick={handleExportCsv}
            className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Exportar CSV
          </button>
        )}
      </div>

      {report && (
        <div className="mt-5 space-y-4">
          <div className="grid gap-2 sm:grid-cols-3">
            {report.resumo.map((r) => (
              <div key={r.tipo} className="rounded-lg border border-slate-200 px-4 py-3">
                <p className="text-xs text-slate-500">{r.tipo}</p>
                <p className={`text-lg font-semibold ${r.ausentes > 0 ? "text-red-700" : "text-emerald-700"}`}>
                  {r.ausentes} ausente{r.ausentes === 1 ? "" : "s"}
                </p>
                <p className="text-xs text-slate-400">de {r.total} registro(s)</p>
              </div>
            ))}
          </div>

          {report.ausentes.length === 0 ? (
            <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              Todos os {report.total_registros} anexos registrados estão no servidor.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
                    <th className="px-3 py-2">Tipo</th>
                    <th className="px-3 py-2">Onde</th>
                    <th className="px-3 py-2">Título</th>
                    <th className="px-3 py-2">Arquivo</th>
                    <th className="px-3 py-2">Enviado em</th>
                  </tr>
                </thead>
                <tbody>
                  {report.ausentes.map((a) => (
                    <tr key={`${a.tipo}-${a.caminho}`} className="border-b border-slate-100">
                      <td className="px-3 py-2 whitespace-nowrap text-slate-500">{a.tipo}</td>
                      <td className="px-3 py-2">{a.onde}</td>
                      <td className="px-3 py-2">{a.titulo}</td>
                      <td className="px-3 py-2 text-slate-600">{a.arquivo}</td>
                      <td className="px-3 py-2 whitespace-nowrap text-slate-500">{a.enviado_em}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="text-xs text-slate-400">
            Diretórios em uso:{" "}
            {Object.entries(report.diretorios)
              .map(([k, v]) => `${k}=${v}`)
              .join(" · ")}
          </p>
        </div>
      )}
    </section>
  );
}
