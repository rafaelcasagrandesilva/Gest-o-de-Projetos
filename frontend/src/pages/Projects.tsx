import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useConsultaReadOnly } from "@/hooks/useConsultaReadOnly";
import { usePermission } from "@/hooks/usePermission";
import {
  activateProject,
  createProject,
  deactivateProject,
  listProjects,
  softDeleteProject,
  type Project,
  type ProjectStatusFilter,
} from "@/services/projects";
import { isAxiosError } from "axios";
import { TruncatedCell } from "@/components/TruncatedText";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import { PROJECT_SORT_COLUMNS, defaultProjectSort } from "@/tableSort/projects";

function statusLabel(p: Project): { label: string; cls: string } {
  if (p.is_active) return { label: "Ativo", cls: "bg-emerald-100 text-emerald-900 ring-emerald-200" };
  return { label: "Encerrado", cls: "bg-slate-100 text-slate-800 ring-slate-200" };
}

export function Projects() {
  const readOnly = useConsultaReadOnly();
  const canCreateProject = usePermission("projects.create");
  const canEditProject = usePermission("projects.edit");
  const canDeleteProject = usePermission("projects.delete");
  const [items, setItems] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ProjectStatusFilter>("ACTIVE");
  const [busyProjectId, setBusyProjectId] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const data = await listProjects({ status: statusFilter });
      setItems(data);
    } catch (e) {
      setError(isAxiosError(e) ? "Erro ao listar projetos." : "Erro inesperado.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [statusFilter]);

  const canManageAny = useMemo(() => !readOnly && (canEditProject || canDeleteProject), [readOnly, canEditProject, canDeleteProject]);

  const { sortedRows, headerSort } = useTableSort(items, PROJECT_SORT_COLUMNS, {
    defaultCompare: defaultProjectSort,
  });

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await createProject({ name: name.trim(), description: description.trim() || null });
      setName("");
      setDescription("");
      setShowForm(false);
      await load();
    } catch (err) {
      if (isAxiosError(err)) {
        const d = err.response?.data?.detail;
        setError(typeof d === "string" ? d : "Não foi possível criar o projeto (apenas ADMIN).");
      } else {
        setError("Erro inesperado.");
      }
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Projetos</h2>
          <p className="text-sm text-slate-500">Lista e cadastro de projetos</p>
        </div>
        {!readOnly && canCreateProject && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setShowForm((v) => !v)}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
            >
              {showForm ? "Fechar formulário" : "Novo projeto"}
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {showForm && !readOnly && canCreateProject && (
        <form
          onSubmit={handleCreate}
          className="max-w-lg space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h3 className="font-medium text-slate-900">Criar projeto</h3>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Nome</label>
            <input
              required
              minLength={2}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="Nome do projeto"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">Descrição</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="Opcional"
            />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {creating ? "Salvando…" : "Salvar"}
          </button>
        </form>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
          Carregando…
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Filtro</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as ProjectStatusFilter)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
              >
                <option value="ALL">Todos</option>
                <option value="ACTIVE">Ativos</option>
                <option value="CLOSED">Encerrados</option>
              </select>
            </label>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/80">
              <tr>
                <SortableTh label="Nome" column="name" variant="standard" {...headerSort} />
                <SortableTh label="Status" column="status" variant="standard" className="w-32" {...headerSort} />
                <SortableTh label="Descrição" column="description" variant="standard" {...headerSort} />
                <th className="px-4 py-3 font-medium text-slate-600 w-[260px]" />
              </tr>
            </thead>
            <tbody>
              {sortedRows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                    Nenhum projeto encontrado.
                  </td>
                </tr>
              ) : (
                sortedRows.map((p) => (
                  <tr key={p.id} className="border-b border-slate-50 last:border-0">
                    <td className="min-w-0 max-w-[300px] px-4 py-3 align-middle font-medium text-slate-900">
                      <TruncatedCell value={p.name} maxWidthClass="max-w-[300px]" />
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${statusLabel(p).cls}`}
                      >
                        {statusLabel(p).label}
                      </span>
                    </td>
                    <td className="min-w-0 max-w-[360px] px-4 py-3 align-middle text-slate-600">
                      <TruncatedCell value={p.description} empty="—" maxWidthClass="max-w-[360px]" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap justify-end gap-2">
                        <Link
                          to={`/projects/list/${p.id}`}
                          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-slate-50"
                        >
                          Custos
                        </Link>

                        {canManageAny && (
                          <>
                            {canEditProject && (
                              <button
                                type="button"
                                disabled={busyProjectId === p.id}
                                onClick={async () => {
                                  setError(null);
                                  if (p.is_active) {
                                    const ok = window.confirm(
                                      "Encerrar projeto? Ele não aparecerá mais para novos lançamentos."
                                    );
                                    if (!ok) return;
                                  }
                                  setBusyProjectId(p.id);
                                  try {
                                    if (p.is_active) await deactivateProject(p.id);
                                    else await activateProject(p.id);
                                    await load();
                                  } catch (err) {
                                    const d = isAxiosError(err) ? err.response?.data?.detail : null;
                                    setError(typeof d === "string" ? d : "Não foi possível atualizar o status do projeto.");
                                  } finally {
                                    setBusyProjectId(null);
                                  }
                                }}
                                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
                              >
                                {p.is_active ? "Encerrar" : "Reativar"}
                              </button>
                            )}

                            {canDeleteProject && (
                              <button
                                type="button"
                                disabled={busyProjectId === p.id}
                                onClick={async () => {
                                  const ok = window.confirm(
                                    "Excluir projeto? Esta ação não remove dados financeiros existentes."
                                  );
                                  if (!ok) return;
                                  setBusyProjectId(p.id);
                                  setError(null);
                                  try {
                                    await softDeleteProject(p.id);
                                    await load();
                                  } catch (err) {
                                    const d = isAxiosError(err) ? err.response?.data?.detail : null;
                                    setError(typeof d === "string" ? d : "Não foi possível excluir o projeto.");
                                  } finally {
                                    setBusyProjectId(null);
                                  }
                                }}
                                className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                              >
                                Excluir
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}
