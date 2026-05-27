import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import {
  fetchReceivablesView,
  createReceivableManualItem,
  deleteReceivableManualItem,
  updateReceivableManualItem,
  type PeriodField,
  type ReceivableViewRow,
  type ReceivableViewType,
} from "@/services/receivables";
import { PeriodFilter } from "@/components/PeriodFilter";
import { TruncatedCell, TruncatedText } from "@/components/TruncatedText";
import { formatApiError } from "@/utils/apiError";
import { SortableTh } from "@/components/table";
import { useTableSort } from "@/hooks/useTableSort";
import {
  type ReceivableUiStatus,
  type ReceivableViewItem,
  RECEIVABLE_VIEW_SORT_COLUMNS,
  defaultReceivableViewSort,
} from "@/tableSort/receivables";

function formatBRL(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDateBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function todayIsoLocal(): string {
  const t = new Date();
  const y = t.getFullYear();
  const m = String(t.getMonth() + 1).padStart(2, "0");
  const d = String(t.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function monthToYm(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function computeUiStatus(inv: ReceivableViewRow): ReceivableUiStatus {
  const net = Number(inv.net_value ?? 0);
  const remaining = Number(inv.remaining ?? Math.max(0, net - Number(inv.total_received ?? 0)));
  if (remaining <= 0.01) return "RECEBIDO";
  const due = inv.due_date.slice(0, 10);
  if (todayIsoLocal() > due) return "EM_ATRASO";
  return "ABERTO";
}

function statusLabel(s: ReceivableUiStatus): string {
  if (s === "RECEBIDO") return "Recebido";
  if (s === "EM_ATRASO") return "Em atraso";
  return "Aberto";
}

function statusBadgeClass(s: ReceivableUiStatus): string {
  if (s === "RECEBIDO") return "bg-emerald-100 text-emerald-900 ring-emerald-200";
  if (s === "EM_ATRASO") return "bg-red-100 text-red-900 ring-red-200";
  return "bg-slate-100 text-slate-800 ring-slate-200";
}

export function Receivables() {
  const [periodMode, setPeriodMode] = useState<"MONTH" | "ALL">("MONTH");
  const [period, setPeriod] = useState(() => monthToYm(new Date()));
  const [periodField, setPeriodField] = useState<PeriodField>("due");
  const [statusFilter, setStatusFilter] = useState<ReceivableUiStatus | "">("");
  const [clienteFilter, setClienteFilter] = useState("");
  const [tipoFilter, setTipoFilter] = useState<"" | ReceivableViewType>("");

  const [rows, setRows] = useState<ReceivableViewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [manualModalOpen, setManualModalOpen] = useState(false);
  const [editingManual, setEditingManual] = useState<ReceivableViewRow | null>(null);

  const ym = useMemo(() => {
    const [y, m] = period.split("-").map(Number);
    return { year: y, month: m };
  }, [period]);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const params: Parameters<typeof fetchReceivablesView>[0] = {
        period_field: periodField,
      };
      if (periodMode === "MONTH") {
        params.year = ym.year;
        params.month = ym.month;
      }
      if (clienteFilter.trim()) params.client = clienteFilter.trim();
      if (tipoFilter) params.tipo = tipoFilter;

      const list = await fetchReceivablesView(params);
      setRows(list);
    } catch (e) {
      if (isAxiosError(e)) setError(formatApiError(e));
      else setError("Erro ao carregar.");
    } finally {
      setLoading(false);
    }
  }, [periodMode, ym.year, ym.month, periodField, clienteFilter, tipoFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const viewRows = useMemo((): ReceivableViewItem[] => {
    const base = rows
      .map((r) => {
        const net = Number(r.net_value ?? 0);
        const recv = Number(r.total_received ?? 0);
        const saldo = Number(r.remaining ?? Math.max(0, net - recv));
        const uiStatus = computeUiStatus(r);
        const tipo = (r.tipo ?? "NF") as ReceivableViewType;
        return { r, tipo, net, recv, saldo, uiStatus };
      });

    if (!statusFilter) return base;
    return base.filter((x) => x.uiStatus === statusFilter);
  }, [rows, statusFilter]);

  const { sortedRows, headerSort } = useTableSort(viewRows, RECEIVABLE_VIEW_SORT_COLUMNS, {
    defaultCompare: defaultReceivableViewSort,
  });

  const kpis = useMemo(() => {
    let total = 0;
    let recebido = 0;
    let atraso = 0;
    for (const { r, net, recv, saldo, uiStatus } of viewRows) {
      // Evita dupla contagem quando ANTECIPACAO aparece como linha separada:
      // - NF: conta apenas o recebido do cliente (antecipação vem em linha própria)
      // - ANTECIPACAO: conta o próprio valor (net_value == total_received)
      // - MANUAL: usa total_received (já é o recebido)
      total += net;
      if (r.tipo === "NF") recebido += Number(r.amount_received_customer ?? 0);
      else recebido += recv;
      if (uiStatus === "EM_ATRASO") atraso += saldo;
    }
    total = Math.round(total * 100) / 100;
    recebido = Math.round(recebido * 100) / 100;
    const emAberto = Math.round((total - recebido) * 100) / 100;
    return { total_receber: total, recebido, em_aberto: emAberto, em_atraso: Math.round(atraso * 100) / 100 };
  }, [viewRows]);

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Contas a receber</h1>
        <p className="mt-1 text-sm text-slate-600">Visão financeira gerada a partir das NFs existentes.</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Kpi label="Total a receber" value={formatBRL(kpis.total_receber)} />
        <Kpi label="Recebido" value={formatBRL(kpis.recebido)} />
        <Kpi label="Em aberto" value={formatBRL(kpis.em_aberto)} accent="text-amber-800" />
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <PeriodFilter mode={periodMode} value={period} onModeChange={setPeriodMode} onChange={setPeriod} />

          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Campo do período</span>
            <select
              value={periodField}
              onChange={(e) => setPeriodField(e.target.value as PeriodField)}
              disabled={periodMode === "ALL"}
              className="rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-60"
            >
              <option value="issue">Emissão</option>
              <option value="due">Vencimento</option>
            </select>
          </label>

          <label className="flex min-w-[160px] flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Status</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="">Todos</option>
              <option value="ABERTO">Aberto</option>
              <option value="RECEBIDO">Recebido</option>
              <option value="EM_ATRASO">Em atraso</option>
            </select>
          </label>

          <label className="flex min-w-[160px] flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Tipo</span>
            <select
              value={tipoFilter}
              onChange={(e) => setTipoFilter(e.target.value as typeof tipoFilter)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="">Todos</option>
              <option value="NF">NF</option>
              <option value="MANUAL">Manual</option>
              <option value="ANTECIPACAO">Antecipação</option>
              <option value="BORDERO">Borderô</option>
            </select>
          </label>

          <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Cliente</span>
            <input
              value={clienteFilter}
              onChange={(e) => setClienteFilter(e.target.value)}
              placeholder="Buscar…"
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="w-fit rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            Atualizar
          </button>

          <button
            type="button"
            onClick={() => {
              setEditingManual(null);
              setManualModalOpen(true);
            }}
            className="w-fit rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            + Adicionar receita
          </button>
        </div>
      </section>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1100px] w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <SortableTh label="Tipo" column="tipo" {...headerSort} />
              <SortableTh label="Cliente" column="client" {...headerSort} />
              <SortableTh label="NF / Referência" column="number" {...headerSort} />
              <SortableTh label="Emissão" column="issue_date" {...headerSort} />
              <SortableTh label="Vencimento" column="due_date" {...headerSort} />
              <SortableTh label="Valor líquido" column="net" {...headerSort} align="right" />
              <SortableTh label="Recebido (antecipação)" column="advance" {...headerSort} align="right" />
              <SortableTh label="Recebido (cliente)" column="customer" {...headerSort} align="right" />
              <SortableTh label="Recebido em" column="received_at" {...headerSort} />
              <SortableTh label="Saldo" column="saldo" {...headerSort} align="right" />
              <SortableTh label="Status" column="status" {...headerSort} />
              <th className="px-2 py-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && viewRows.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-3 py-8 text-center text-slate-500">
                  Carregando…
                </td>
              </tr>
            ) : viewRows.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-3 py-8 text-center text-slate-500">
                  {periodMode === "ALL" ? "Nenhuma conta a receber encontrada." : "Nenhuma conta a receber no período."}
                </td>
              </tr>
            ) : (
              sortedRows.map(({ r, tipo, net, saldo, uiStatus }) => (
                <tr key={r.id} className="hover:bg-slate-50/80">
                  <td className="px-2 py-2">
                    {tipo === "MANUAL" ? (
                      <span
                        title={r.observacao ? "Possui observação" : undefined}
                        className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-800 ring-1 ring-slate-200"
                      >
                        MANUAL
                      </span>
                    ) : (
                      <span className="inline-flex rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-900 ring-1 ring-indigo-200">
                        NF
                      </span>
                    )}
                  </td>
                  <td className="min-w-0 max-w-[300px] px-2 py-2 align-middle text-slate-700">
                    <TruncatedCell value={r.client} maxWidthClass="max-w-[300px]" />
                  </td>
                  <td className="min-w-0 max-w-[320px] px-2 py-2 align-middle">
                    {tipo === "MANUAL" ? (
                      <div className="min-w-0 space-y-0.5">
                        <TruncatedText className="font-medium text-slate-900" maxWidthClass="max-w-[300px]">
                          {r.descricao || "—"}
                        </TruncatedText>
                        <TruncatedText className="text-xs text-slate-500" maxWidthClass="max-w-[300px]">
                          {r.numero_referencia || "—"}
                        </TruncatedText>
                      </div>
                    ) : (
                      <TruncatedText className="font-medium" maxWidthClass="max-w-[280px]">
                        {r.number}
                      </TruncatedText>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2">{formatDateBr(r.issue_date)}</td>
                  <td className="whitespace-nowrap px-2 py-2">{formatDateBr(r.due_date)}</td>
                  <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">{formatBRL(net)}</td>
                  <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">
                    {formatBRL(Number(r.amount_received_advance ?? 0))}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">
                    {formatBRL(Number(r.amount_received_customer ?? 0))}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2">
                    {uiStatus !== "RECEBIDO" || !r.received_at ? "—" : formatDateBr(r.received_at)}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">{formatBRL(saldo)}</td>
                  <td className="px-2 py-2">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${statusBadgeClass(uiStatus)}`}
                    >
                      {statusLabel(uiStatus)}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-right">
                    {tipo === "MANUAL" ? (
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            setEditingManual(r);
                            setManualModalOpen(true);
                          }}
                          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          onClick={async () => {
                            if (!window.confirm("Excluir esta receita manual?")) return;
                            try {
                              await deleteReceivableManualItem(r.id);
                              await load();
                            } catch (e) {
                              if (isAxiosError(e)) setError(formatApiError(e));
                              else setError("Erro ao excluir.");
                            }
                          }}
                          className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
                        >
                          Excluir
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <ManualReceivableModal
        open={manualModalOpen}
        onClose={() => setManualModalOpen(false)}
        initial={editingManual}
        onSaved={async () => {
          setManualModalOpen(false);
          setEditingManual(null);
          await load();
        }}
        onError={(msg) => setError(msg)}
      />
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-lg font-semibold tabular-nums text-slate-900 ${accent ?? ""}`}>{value}</p>
    </div>
  );
}

function toNumberOrNull(v: string): number | null {
  const s = v.replace(/\./g, "").replace(",", ".").trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function ManualReceivableModal({
  open,
  onClose,
  initial,
  onSaved,
  onError,
}: {
  open: boolean;
  onClose: () => void;
  initial: ReceivableViewRow | null;
  onSaved: () => void | Promise<void>;
  onError: (msg: string) => void;
}) {
  const isEdit = Boolean(initial && (initial.tipo ?? "NF") === "MANUAL");

  const [descricao, setDescricao] = useState("");
  const [cliente, setCliente] = useState("");
  const [numeroRef, setNumeroRef] = useState("");
  const [dataEmissao, setDataEmissao] = useState(() => todayIsoLocal());
  const [dataVenc, setDataVenc] = useState(() => todayIsoLocal());
  const [valorLiquido, setValorLiquido] = useState("");
  const [valorRecebido, setValorRecebido] = useState("");
  const [dataReceb, setDataReceb] = useState("");
  const [observacao, setObservacao] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (isEdit && initial) {
      setDescricao(initial.descricao ?? "");
      setCliente(initial.client ?? "");
      setNumeroRef(initial.numero_referencia ?? "");
      setDataEmissao(initial.issue_date ?? todayIsoLocal());
      setDataVenc(initial.due_date ?? todayIsoLocal());
      setValorLiquido(String(initial.net_value ?? ""));
      setValorRecebido(String(initial.amount_received_customer ?? ""));
      setDataReceb(initial.received_at ?? "");
      setObservacao(initial.observacao ?? "");
    } else {
      setDescricao("");
      setCliente("");
      setNumeroRef("");
      setDataEmissao(todayIsoLocal());
      setDataVenc(todayIsoLocal());
      setValorLiquido("");
      setValorRecebido("");
      setDataReceb("");
      setObservacao("");
    }
  }, [open, isEdit, initial]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-[720px] rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">{isEdit ? "Editar receita" : "Adicionar receita"}</h2>
            <p className="mt-1 text-xs text-slate-600">Lançamento manual em Contas a Receber.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            Fechar
          </button>
        </div>

        <form
          className="space-y-4 px-5 py-4"
          onSubmit={async (e) => {
            e.preventDefault();
            onError("");

            const net = toNumberOrNull(valorLiquido);
            if (!net || net <= 0) return onError("Informe um valor líquido válido.");
            const received = toNumberOrNull(valorRecebido);
            if (received !== null && received > net + 0.01) return onError("Valor recebido não pode ser maior que o valor líquido.");
            const dr = dataReceb.trim();
            if (dr && (received === null || received <= 0)) {
              return onError("Se informar data de recebimento, informe valor recebido maior que zero.");
            }

            setSaving(true);
            try {
              const payload = {
                descricao: descricao.trim(),
                cliente: cliente.trim(),
                numero_referencia: numeroRef.trim() ? numeroRef.trim() : null,
                data_emissao: dataEmissao,
                data_vencimento: dataVenc,
                valor_liquido: net,
                valor_recebido: received ?? null,
                data_recebimento:
                  received !== null && received > 0 && dr ? dr : null,
                observacao: observacao.trim() ? observacao.trim() : null,
              };

              if (!payload.descricao) return onError("Informe a descrição.");
              if (!payload.cliente) return onError("Informe o cliente.");

              if (isEdit && initial) await updateReceivableManualItem(initial.id, payload);
              else await createReceivableManualItem(payload);

              await onSaved();
            } catch (err) {
              if (isAxiosError(err)) onError(formatApiError(err));
              else onError("Erro ao salvar.");
            } finally {
              setSaving(false);
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Cliente</span>
              <input
                value={cliente}
                onChange={(e) => setCliente(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2"
                placeholder="Ex.: ACME LTDA"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Nº referência (opcional)</span>
              <input
                value={numeroRef}
                onChange={(e) => setNumeroRef(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2"
                placeholder="Ex.: PED-123"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Descrição</span>
            <input
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
              placeholder="Ex.: Receita de consultoria"
            />
          </label>

          <div className="grid gap-3 md:grid-cols-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Data emissão</span>
              <input
                type="date"
                value={dataEmissao}
                onChange={(e) => setDataEmissao(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Data vencimento</span>
              <input
                type="date"
                value={dataVenc}
                onChange={(e) => setDataVenc(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Data recebimento</span>
              <input
                type="date"
                value={dataReceb}
                onChange={(e) => setDataReceb(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Valor líquido</span>
              <input
                value={valorLiquido}
                onChange={(e) => setValorLiquido(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2"
                placeholder="0,00"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700">Valor recebido (opcional)</span>
              <input
                value={valorRecebido}
                onChange={(e) => setValorRecebido(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2"
                placeholder="0,00"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Observação (opcional)</span>
            <textarea
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
              className="min-h-[90px] rounded-lg border border-slate-300 px-3 py-2"
              placeholder="Contexto financeiro, detalhes, etc."
            />
          </label>

          <div className="flex justify-end gap-2 border-t border-slate-200 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
              disabled={saving}
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {saving ? "Salvando…" : "Salvar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

