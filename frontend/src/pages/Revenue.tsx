import { useEffect, useState } from "react";
import { listProjects, type Project } from "@/services/projects";
import { createRevenue, deleteRevenue, listRevenues, type Revenue } from "@/services/financial";
import { isAxiosError } from "axios";

function monthStartInput(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

export function RevenuePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [items, setItems] = useState<Revenue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [amount, setAmount] = useState("");
  const [competencia, setCompetencia] = useState(monthStartInput);
  const [status, setStatus] = useState<"previsto" | "recebido">("recebido");
  const [description, setDescription] = useState("");
  const [hasRetention, setHasRetention] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const ps = await listProjects();
        setProjects(ps);
        if (ps.length && !projectId) setProjectId(ps[0].id);
      } catch {
        setError("Não foi possível carregar projetos.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const rows = await listRevenues(projectId);
        if (!cancelled) {
          setItems(rows);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            isAxiosError(e) && e.response?.status === 403
              ? "Sem permissão (Financeiro/Admin/Diretor)."
              : "Erro ao listar faturamento."
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId) return;
    setError(null);
    try {
      await createRevenue({
        project_id: projectId,
        competencia,
        amount: Number(amount),
        description: description.trim() || null,
        status,
        has_retention: hasRetention,
      });
      setAmount("");
      setDescription("");
      setHasRetention(false);
      setItems(await listRevenues(projectId));
    } catch {
      setError("Não foi possível lançar a receita.");
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Excluir lançamento?")) return;
    try {
      await deleteRevenue(id);
      if (projectId) setItems(await listRevenues(projectId));
    } catch {
      setError("Erro ao excluir.");
    }
  }

  if (loading) {
    return <div className="text-slate-500">Carregando…</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Faturamento</h2>
        <p className="text-sm text-slate-500">Receitas por projeto (previsto / recebido)</p>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</div>
      )}

      <div className="max-w-xs">
        <label className="mb-1 block text-sm text-slate-600">Projeto</label>
        <select
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        >
          <option value="">Selecione…</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {projectId && (
        <>
          <form
            onSubmit={handleCreate}
            className="max-w-2xl space-y-3 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
          >
            <h3 className="font-medium text-slate-900">Novo faturamento</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-slate-500">Competência (mês)</label>
                <input
                  type="date"
                  required
                  value={competencia}
                  onChange={(e) => setCompetencia(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">Valor</label>
                <input
                  required
                  type="number"
                  min={0}
                  step="0.01"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">Status</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value as "previsto" | "recebido")}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                >
                  <option value="recebido">Recebido</option>
                  <option value="previsto">Previsto</option>
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs text-slate-500">Descrição</label>
                <input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
              </div>
              <div className="flex items-center gap-2 sm:col-span-2">
                <input
                  id="rev-retention"
                  type="checkbox"
                  checked={hasRetention}
                  onChange={(e) => setHasRetention(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="rev-retention" className="text-sm text-slate-700">
                  Possui retenção (10% sobre o valor — calculado automaticamente)
                </label>
              </div>
            </div>
            <button
              type="submit"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
            >
              Lançar
            </button>
          </form>

          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50/80">
                <tr>
                  <th className="px-4 py-3 font-medium text-slate-600">Competência</th>
                  <th className="px-4 py-3 font-medium text-slate-600">Valor</th>
                  <th className="px-4 py-3 font-medium text-slate-600">Retenção (R$)</th>
                  <th className="px-4 py-3 font-medium text-slate-600">Status</th>
                  <th className="px-4 py-3 font-medium text-slate-600">Descrição</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {items
                  .filter((r) => r.project_id === projectId)
                  .map((r) => (
                    <tr key={r.id} className="border-b border-slate-50">
                      <td className="px-4 py-3">{r.competencia}</td>
                      <td className="px-4 py-3 tabular-nums">
                        {r.amount.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
                      </td>
                      <td className="px-4 py-3 tabular-nums text-slate-600">
                        {r.retention_value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
                      </td>
                      <td className="px-4 py-3">{r.status}</td>
                      <td className="px-4 py-3 text-slate-600">{r.description ?? "—"}</td>
                      <td className="px-4 py-3 text-right">
                        <button type="button" onClick={() => handleDelete(r.id)} className="text-sm text-red-600">
                          Excluir
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
            {items.filter((r) => r.project_id === projectId).length === 0 && (
              <p className="p-6 text-sm text-slate-500">Nenhum lançamento para este projeto.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
