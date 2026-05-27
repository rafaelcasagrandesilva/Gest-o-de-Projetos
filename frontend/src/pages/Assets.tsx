import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AssetExpirationBadge } from "@/components/assets/AssetExpirationBadge";
import { AssetPhysicalConditionBadge } from "@/components/assets/AssetPhysicalConditionBadge";
import { AssetStatusBadge } from "@/components/assets/AssetStatusBadge";
import { AssetMoneyInput } from "@/components/assets/AssetMoneyInput";
import { ASSET_STATUS_LABELS, formatBRL, parseBRLInput } from "@/components/assets/assetLabels";
import { AssetSizeField } from "@/components/assets/AssetSizeField";
import { EPI_MACRO_CATEGORY, PATRIMONIAL_MACRO_CATEGORIES } from "@/components/assets/assetCategories";
import { assetSupportsSize, formatAssetCategoryLine, SIZE_SUGGESTIONS } from "@/components/assets/assetSize";
import { CostCenterSelect } from "@/components/company-finance/CostCenterSelect";
import { CC_REF_ADMINISTRATIVO, CC_REF_ALMOXARIFADO } from "@/components/company-finance/costCenter";
import { CollaboratorSelect } from "@/components/CollaboratorSelect";
import { hasPermission } from "@/permissions";
import { useAuth } from "@/context/AuthContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import {
  createAsset,
  fetchAssetCategories,
  listAssets,
  listEpis,
  type AssetListItem,
  type AssetPhysicalCondition,
  type AssetStatus,
} from "@/services/assets";
import { listProjects, type Project } from "@/services/projects";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import { ASSET_SORT_COLUMNS, defaultAssetSort } from "@/tableSort/assets";

const STATUS_OPTIONS: { value: AssetStatus | ""; label: string }[] = [
  { value: "", label: "Todos os status" },
  ...(Object.entries(ASSET_STATUS_LABELS) as [AssetStatus, string][]).map(([value, label]) => ({
    value,
    label,
  })),
];

const EXPIRATION_FILTERS = [
  { value: "", label: "Validade (todos)" },
  { value: "expired", label: "Vencidos" },
  { value: "30", label: "Vence em 30 dias" },
  { value: "7", label: "Vence em 7 dias" },
  { value: "tomorrow", label: "Vence amanhã" },
];

export type AssetInventoryVariant = "patrimonial" | "epi";

type AssetsPageProps = {
  variant?: AssetInventoryVariant;
};

export function Assets({ variant = "patrimonial" }: AssetsPageProps) {
  const isEpi = variant === "epi";
  const listBasePath = isEpi ? "/epis" : "/assets";
  const categoryScope = isEpi ? "epi" : "patrimonial";

  const { user } = useAuth();
  const { setWorkspace } = useWorkspace();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    setWorkspace("assets");
  }, [setWorkspace]);
  const canEdit = hasPermission(user?.permission_names, "assets.edit");

  const [items, setItems] = useState<AssetListItem[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState<AssetStatus | "">("");
  const [employeeId, setEmployeeId] = useState("");
  const [costCenterRef, setCostCenterRef] = useState("");
  const [expiration, setExpiration] = useState("");
  const [sizeFilter, setSizeFilter] = useState("");
  const [withoutHolderOnly, setWithoutHolderOnly] = useState(false);
  const [physicalConditionFilter, setPhysicalConditionFilter] = useState<AssetPhysicalCondition | "">("");

  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createCategory, setCreateCategory] = useState("");
  const [createCostCenter, setCreateCostCenter] = useState(
    isEpi ? CC_REF_ALMOXARIFADO : CC_REF_ADMINISTRATIVO,
  );
  const [createPurchaseValue, setCreatePurchaseValue] = useState("");
  const [createSize, setCreateSize] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const common = {
        q: q.trim() || undefined,
        category: !isEpi && category ? category : undefined,
        status: status || undefined,
        employee_id: employeeId || undefined,
        cost_center_ref: costCenterRef || undefined,
        expiration: expiration || undefined,
        size: sizeFilter.trim() || undefined,
        without_holder: withoutHolderOnly || undefined,
        physical_condition: physicalConditionFilter || undefined,
      };
      const data = isEpi
        ? await listEpis(common)
        : await listAssets({ ...common, exclude_epi: true });
      setItems(data);
    } catch {
      setError(isEpi ? "Não foi possível carregar os EPIs." : "Não foi possível carregar os ativos.");
    } finally {
      setLoading(false);
    }
  }, [
    isEpi,
    q,
    category,
    status,
    employeeId,
    costCenterRef,
    expiration,
    sizeFilter,
    withoutHolderOnly,
    physicalConditionFilter,
  ]);

  useEffect(() => {
    setExpiration(searchParams.get("expiration") ?? "");
    setWithoutHolderOnly(
      searchParams.get("without_holder") === "true" || searchParams.get("sem_responsavel") === "true",
    );
    const phys = searchParams.get("physical_condition") ?? searchParams.get("estado_fisico");
    if (phys === "FAIR" || phys === "mau_estado") setPhysicalConditionFilter("FAIR");
    else if (phys === "DAMAGED") setPhysicalConditionFilter("DAMAGED");
    else setPhysicalConditionFilter("");
  }, [searchParams]);

  const activeDeepFilters = useMemo(() => {
    const tags: { label: string; clear: () => void }[] = [];
    if (expiration) {
      const label = EXPIRATION_FILTERS.find((o) => o.value === expiration)?.label ?? expiration;
      tags.push({
        label: `Validade: ${label}`,
        clear: () => {
          setExpiration("");
          const next = new URLSearchParams(searchParams);
          next.delete("expiration");
          setSearchParams(next);
        },
      });
    }
    if (withoutHolderOnly) {
      tags.push({
        label: "Sem responsável",
        clear: () => {
          setWithoutHolderOnly(false);
          const next = new URLSearchParams(searchParams);
          next.delete("without_holder");
          next.delete("sem_responsavel");
          setSearchParams(next);
        },
      });
    }
    if (physicalConditionFilter) {
      tags.push({
        label: `Estado: ${physicalConditionFilter === "FAIR" ? "Mau estado" : "Quebrado"}`,
        clear: () => {
          setPhysicalConditionFilter("");
          const next = new URLSearchParams(searchParams);
          next.delete("physical_condition");
          next.delete("estado_fisico");
          setSearchParams(next);
        },
      });
    }
    return tags;
  }, [expiration, withoutHolderOnly, physicalConditionFilter, searchParams, setSearchParams]);

  const showCreateSize = assetSupportsSize(createCategory);
  const fallbackCategories = useMemo(
    () => (isEpi ? [EPI_MACRO_CATEGORY] : [...PATRIMONIAL_MACRO_CATEGORIES]),
    [isEpi],
  );
  const categoryOptions = categories.length ? categories : fallbackCategories;

  useEffect(() => {
    void (async () => {
      try {
        const [cats, projs] = await Promise.all([
          fetchAssetCategories(categoryScope),
          listProjects(),
        ]);
        setCategories(cats);
        setProjects(projs);
        if (isEpi) {
          setCreateCategory(EPI_MACRO_CATEGORY);
        } else if (cats.length && !createCategory) {
          setCreateCategory(cats[0]);
        }
      } catch {
        setCategories(fallbackCategories);
        if (isEpi) setCreateCategory(EPI_MACRO_CATEGORY);
        else if (!createCategory) setCreateCategory(fallbackCategories[0] ?? "");
      }
    })();
  }, [categoryScope, createCategory, isEpi, fallbackCategories]);

  useEffect(() => {
    void load();
  }, [load]);

  const { sortedRows, headerSort } = useTableSort(items, ASSET_SORT_COLUMNS, {
    defaultCompare: defaultAssetSort,
  });

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!createName.trim() || !createCategory) return;
    try {
      let purchaseValue: number | null = null;
      if (!isEpi) {
        const pv = createPurchaseValue.trim() ? parseBRLInput(createPurchaseValue) : null;
        if (pv != null && pv < 0) {
          setError("Valor do item não pode ser negativo.");
          return;
        }
        purchaseValue = pv && pv > 0 ? pv : null;
      }
      const row = await createAsset({
        name: createName.trim(),
        category: isEpi ? EPI_MACRO_CATEGORY : createCategory,
        cost_center_ref: createCostCenter,
        purchase_value: purchaseValue,
        size: showCreateSize && createSize.trim() ? createSize.trim() : null,
      });
      setShowCreate(false);
      setCreateName("");
      setCreatePurchaseValue("");
      setCreateSize("");
      navigate(`${listBasePath}/${row.id}`);
    } catch {
      setError(isEpi ? "Não foi possível cadastrar o EPI." : "Não foi possível criar o ativo.");
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {isEpi ? "EPIs" : "Gestão de Ativos"}
          </h1>
          <p className="text-sm text-slate-500">
            {isEpi
              ? "Controle operacional, validade e almoxarifado"
              : "Patrimônio reutilizável e equipamentos corporativos"}
          </p>
        </div>
        {canEdit ? (
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            {isEpi ? "Novo EPI" : "Novo ativo"}
          </button>
        ) : null}
      </div>

      {!isEpi && activeDeepFilters.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-sm">
          <span className="font-medium text-indigo-900">Filtro do dashboard:</span>
          {activeDeepFilters.map((f) => (
            <button
              key={f.label}
              type="button"
              onClick={f.clear}
              className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-indigo-800 shadow-sm hover:bg-indigo-100"
            >
              {f.label}
              <span aria-hidden>×</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-3 lg:grid-cols-7">
        <input
          type="search"
          placeholder="Buscar código, nome, tags…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm md:col-span-2"
        />
        {!isEpi ? (
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Categoria (todas)</option>
            {categoryOptions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : null}
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as AssetStatus | "")}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value || "all"} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={expiration}
          onChange={(e) => setExpiration(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          {EXPIRATION_FILTERS.map((o) => (
            <option key={o.value || "all"} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={sizeFilter}
          onChange={(e) => setSizeFilter(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Tamanho (todos)</option>
          {SIZE_SUGGESTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <CostCenterSelect
          value={costCenterRef}
          onChange={setCostCenterRef}
          projects={projects}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <div className="md:col-span-2">
          <CollaboratorSelect
            label="Responsável"
            value={employeeId}
            onChange={setEmployeeId}
            placeholder="Filtrar por responsável…"
          />
        </div>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <SortableTh label="Código" column="code" variant="standard" {...headerSort} />
              <SortableTh label="Item" column="name" variant="standard" {...headerSort} />
              <SortableTh label="Categoria" column="category" variant="standard" {...headerSort} />
              <SortableTh label="Responsável" column="holder" variant="standard" {...headerSort} />
              <SortableTh label="Centro de custo" column="cost_center" variant="standard" {...headerSort} />
              {!isEpi ? (
                <SortableTh label="Valor" column="value" variant="standard" {...headerSort} />
              ) : null}
              <th className="px-4 py-3">Indicadores</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={isEpi ? 7 : 8} className="px-4 py-8 text-center text-slate-500">
                  Carregando…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={isEpi ? 7 : 8} className="px-4 py-8 text-center text-slate-500">
                  {isEpi ? "Nenhum EPI encontrado." : "Nenhum ativo encontrado."}
                </td>
              </tr>
            ) : (
              sortedRows.map((row) => {
                const catLine = formatAssetCategoryLine(row.category, row.subcategory, row.size);
                return (
                <tr key={row.id} className="border-t border-slate-100 hover:bg-slate-50/80">
                  <td className="px-4 py-3 font-mono text-xs">{row.asset_code}</td>
                  <td className="px-4 py-3 font-medium text-slate-900">{row.name}</td>
                  <td className="px-4 py-3 text-slate-600">
                    <div>{catLine.primary}</div>
                    {catLine.secondary ? (
                      <div className="text-xs text-slate-500">• {catLine.secondary}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">{row.current_holder_name ?? "—"}</td>
                  <td className="px-4 py-3">{row.cost_center_label ?? "—"}</td>
                  {!isEpi ? (
                    <td className="px-4 py-3 text-slate-700">
                      {row.purchase_value != null ? formatBRL(row.purchase_value) : "—"}
                    </td>
                  ) : null}
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      <AssetStatusBadge status={row.status} />
                      <AssetPhysicalConditionBadge condition={row.physical_condition} />
                      <AssetExpirationBadge
                        show={row.has_inspection_control}
                        level={row.expiration_alert}
                        compact
                      />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link to={`${listBasePath}/${row.id}`} className="text-indigo-600 hover:underline">
                      Detalhes
                    </Link>
                  </td>
                </tr>
              );
              })
            )}
          </tbody>
        </table>
      </div>

      {showCreate ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <form
            onSubmit={(e) => void handleCreate(e)}
            className="w-full max-w-md space-y-4 rounded-xl bg-white p-6 shadow-xl"
          >
            <h2 className="text-lg font-semibold">{isEpi ? "Novo EPI" : "Novo ativo"}</h2>
            <label className="block text-sm">
              <span className="text-slate-600">Nome do item</span>
              <input
                required
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="Ex.: Botina Eletricista, Multímetro Fluke 117…"
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            {!isEpi ? (
              <label className="block text-sm">
                <span className="text-slate-600">Categoria</span>
                <select
                  value={createCategory}
                  onChange={(e) => {
                    setCreateCategory(e.target.value);
                    setCreateSize("");
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                >
                  {categoryOptions.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {showCreateSize ? (
              <AssetSizeField
                value={createSize}
                onChange={setCreateSize}
                className="block text-sm"
              />
            ) : null}
            {!isEpi ? (
              <label className="block text-sm">
                <span className="text-slate-600">Valor do item (R$)</span>
                <AssetMoneyInput value={createPurchaseValue} onChange={setCreatePurchaseValue} />
              </label>
            ) : null}
            <label className="block text-sm">
              <span className="text-slate-600">Centro de custo</span>
              <CostCenterSelect
                value={createCostCenter}
                onChange={setCreateCostCenter}
                projects={projects}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="rounded-lg border px-4 py-2 text-sm">
                Cancelar
              </button>
              <button type="submit" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white">
                Criar e abrir
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
