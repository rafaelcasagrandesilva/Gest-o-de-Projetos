import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isAxiosError } from "axios";
import {
  fetchDebtLedger,
  planDebtInstallments,
  previewDebtLedger,
  replaceDebtLedger,
  type DebtLedger,
  type DebtLedgerRowInput,
  type DebtPlanMode,
} from "@/services/companyFinance";
import { formatApiError } from "@/utils/apiError";
import {
  formatCurrencyInputFromApi,
  formatCurrencyOrDash,
  parseCurrencyInput,
} from "@/utils/currency";

/**
 * Evolução da dívida — a planilha do financeiro dentro do SGC.
 *
 * Mesmo formato do editor de Cronograma Financeiro (modal + tabela editável na própria linha +
 * resumo de fechamento no rodapé), porque é o formato que a equipe já usa e entende. A tabela
 * reproduz a planilha do controle de acordos, coluna por coluna:
 *
 *     MÊS · SALDO INICIAL · APORTE · TAXA · JUROS · PAGAMENTO · SALDO FINAL
 *
 * As três colunas digitáveis (APORTE, TAXA, PAGAMENTO) são exatamente as três da planilha:
 * o resto é calculado. A regra da coluna TAXA:
 *
 *   - **em branco** → herda o mês anterior; se ninguém definiu nada em nenhum mês, a dívida
 *     corre no padrão do SGC (0,5% a.m.) — é o "se eu não mexer em nada, quero ver a evolução";
 *   - **um número** → cria a vigência NAQUELE mês e vale dali para frente;
 *   - **zero** → congela a dívida a partir dali (é como se registra um acordo fechado).
 *
 * Nenhuma regra financeira mora aqui: cada tecla dispara um `preview` no backend, que devolve o
 * razão inteiro recalculado pelo MESMO motor que grava (app/services/debt_accrual.py). É o que
 * garante que o que se vê digitando é o que fica salvo.
 */

/** "AAAA-MM-01" → "MM/AAAA". */
function mesBr(iso: string): string {
  return `${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
}

/** "AAAA-MM-01" → "AAAA-MM". */
function mesKey(iso: string): string {
  return iso.slice(0, 7);
}

/** Decimal ao mês → "1,5" (só o número, para caber na caixa da linha). */
function taxaInput(taxa: number): string {
  if (!Number.isFinite(taxa)) return "";
  return String(Number((taxa * 100).toFixed(4))).replace(".", ",");
}

function taxaBr(taxa: number): string {
  if (!Number.isFinite(taxa) || taxa === 0) return "0%";
  return `${taxaInput(taxa)}%`;
}

/** "1,5" → 0.015. Vazio → null (a linha não define taxa). */
function parseTaxa(raw: string): number | null {
  const t = raw.trim();
  if (t.length === 0) return null;
  const n = Number(t.replace(/\s|%/g, "").replace(",", "."));
  return Number.isFinite(n) ? n / 100 : null;
}

/** Edição de uma linha: só o que o usuário digitou (string vazia = caixa vazia). */
interface Edicao {
  taxa?: string;
  aporte?: string;
  pagamento?: string;
}

export function DebtLedgerModal({
  itemId,
  titulo,
  subtitulo,
  readOnly,
  readOnlyMessage,
  onClose,
  onSaved,
}: {
  itemId: string;
  titulo: string;
  subtitulo?: string | null;
  readOnly: boolean;
  readOnlyMessage: string;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const [ledger, setLedger] = useState<DebtLedger | null>(null);
  const [edicoes, setEdicoes] = useState<Record<string, Edicao>>({});
  const [planoAberto, setPlanoAberto] = useState(false);
  const [planoMes, setPlanoMes] = useState("");
  const [planoModo, setPlanoModo] = useState<DebtPlanMode>("AMORT_FIXA");
  const [planoValor, setPlanoValor] = useState("");
  const [planoParcelas, setPlanoParcelas] = useState("12");
  const [planoResumo, setPlanoResumo] = useState<string | null>(null);

  const [inicioMes, setInicioMes] = useState("");
  const [inicioValor, setInicioValor] = useState("");
  const [projecao, setProjecao] = useState(6);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sujo, setSujo] = useState(false);
  /** Guarda os parâmetros originais para saber o que mudou de verdade. */
  const original = useRef<{ mes: string; valor: string } | null>(null);

  /** Monta o payload da tela: parâmetros + uma linha por competência editada. */
  const montarPayload = useCallback(
    (base: DebtLedger | null) => {
      const linhas: DebtLedgerRowInput[] = [];
      // Inclui também os meses de vigências/eventos JÁ GRAVADOS que não aparecem como linha
      // (ex.: uma taxa lançada em mês anterior ao início da dívida). Sem isso, salvar de novo
      // apagaria silenciosamente o que não estivesse visível na tabela.
      const meses = new Set<string>([
        ...Object.keys(edicoes),
        ...(base?.linhas ?? []).map((l) => mesKey(l.competencia)),
        ...(base?.taxas ?? []).map((t) => mesKey(t.valid_from)),
        ...(base?.eventos ?? []).map((e) => mesKey(e.competencia)),
      ]);
      for (const mes of [...meses].sort()) {
        const ed = edicoes[mes];
        const linhaBase = base?.linhas.find((l) => mesKey(l.competencia) === mes);
        // Sem edição na linha, preserva o que já estava gravado (taxa só quando é vigência
        // PRÓPRIA da dívida — taxa herdada/padrão não vira vigência nova ao salvar).
        const vigenciaPropria = base?.taxas.find((t) => mesKey(t.valid_from) === mes);
        const row: DebtLedgerRowInput = { competencia: `${mes}-01` };

        if (ed?.taxa !== undefined) {
          row.taxa = parseTaxa(ed.taxa);
        } else if (vigenciaPropria) {
          row.taxa = vigenciaPropria.monthly_rate;
        }

        const eventoGravado = base?.eventos.find(
          (e) => mesKey(e.competencia) === mes && e.kind === "APORTE",
        );
        if (ed?.aporte !== undefined) {
          const v = parseCurrencyInput(ed.aporte);
          row.aporte = ed.aporte.trim().length > 0 && v > 0 ? v : null;
        } else if (linhaBase && linhaBase.aporte > 0) {
          row.aporte = linhaBase.aporte;
        } else if (eventoGravado) {
          row.aporte = eventoGravado.amount;
        }
        if (linhaBase && linhaBase.abatimento > 0) row.abatimento = linhaBase.abatimento;
        if (linhaBase && linhaBase.encargo_manual > 0) row.encargo_manual = linhaBase.encargo_manual;

        if (ed?.pagamento !== undefined) {
          row.pagamento = ed.pagamento.trim().length > 0 ? parseCurrencyInput(ed.pagamento) : null;
        }

        const temAlgo =
          row.taxa != null ||
          row.aporte != null ||
          row.abatimento != null ||
          row.encargo_manual != null ||
          "pagamento" in row;
        if (temAlgo) linhas.push(row);
      }
      return {
        start_month: inicioMes ? `${inicioMes}-01` : null,
        principal: inicioValor.trim().length ? parseCurrencyInput(inicioValor) : null,
        linhas,
      };
    },
    [edicoes, inicioMes, inicioValor],
  );

  // Carga inicial.
  useEffect(() => {
    let vivo = true;
    void (async () => {
      try {
        // Abertura lê o razão GRAVADO (e não um preview vazio): é ele que traz as vigências
        // e os aportes já salvos, que a tela precisa conhecer para reenviá-los no payload.
        const data = await fetchDebtLedger(itemId, projecao);
        if (!vivo) return;
        setLedger(data);
        const mes = mesKey(data.origem);
        const valor = formatCurrencyInputFromApi(data.resumo.principal);
        setInicioMes(mes);
        setInicioValor(valor);
        original.current = { mes, valor };
        const fim = data.resumo.competencia_final;
        if (fim) {
          const [y, m] = [Number(fim.slice(0, 4)), Number(fim.slice(5, 7))];
          const prox = m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`;
          setPlanoMes(prox);
        }
      } catch (e) {
        if (vivo) setErro(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar a evolução.");
      } finally {
        if (vivo) setCarregando(false);
      }
    })();
    return () => {
      vivo = false;
    };
    // Só na montagem: as recargas seguintes passam pelo preview com o que está digitado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId]);

  // Recalcula enquanto digita (debounce curto — cada tecla não precisa de uma ida ao servidor).
  useEffect(() => {
    if (carregando || !ledger) return;
    const t = window.setTimeout(() => {
      void (async () => {
        try {
          setLedger(await previewDebtLedger(itemId, montarPayload(ledger), projecao));
          setErro(null);
        } catch (e) {
          setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível recalcular.");
        }
      })();
    }, 350);
    return () => window.clearTimeout(t);
    // `ledger` fora das dependências de propósito: ele é o RESULTADO do preview, e incluí-lo
    // criaria um laço infinito de recálculo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edicoes, inicioMes, inicioValor, projecao, itemId, carregando]);

  /** Gera as parcelas a partir do saldo do razão e preenche a coluna Pagamento. */
  async function gerarParcelas() {
    if (!ledger) return;
    setSalvando(true);
    setErro(null);
    setPlanoResumo(null);
    try {
      const plano = await planDebtInstallments(itemId, {
        start_month: `${planoMes}-01`,
        mode: planoModo,
        amount: planoModo === "N_PARCELAS" ? null : parseCurrencyInput(planoValor),
        count: planoModo === "N_PARCELAS" ? Number(planoParcelas) : null,
      });
      // As parcelas entram como EDIÇÃO (não gravam): a tabela recalcula e você confere antes
      // de salvar — mesmo fluxo do gerador por faixas do Cronograma.
      setEdicoes((prev) => {
        const next = { ...prev };
        for (const p of plano.parcelas) {
          next[mesKey(p.competencia)] = {
            ...next[mesKey(p.competencia)],
            pagamento: formatCurrencyInputFromApi(p.valor),
          };
        }
        return next;
      });
      setSujo(true);
      setPlanoAberto(false);
      setPlanoResumo(
        `${plano.parcelas.length} parcelas a partir de ${mesBr(plano.competencia_inicial)} ` +
          `sobre o saldo de ${formatCurrencyOrDash(plano.saldo_base)} — ` +
          `total ${formatCurrencyOrDash(plano.total_pago)}, sendo ${formatCurrencyOrDash(plano.total_juros)} de juros. ` +
          `Confira na tabela e salve.`,
      );
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível gerar as parcelas.");
    } finally {
      setSalvando(false);
    }
  }

  function editar(mes: string, campo: keyof Edicao, valor: string) {
    setSujo(true);
    setEdicoes((prev) => ({ ...prev, [mes]: { ...prev[mes], [campo]: valor } }));
  }

  async function salvar() {
    if (!ledger) return;
    setSalvando(true);
    setErro(null);
    try {
      const salvo = await replaceDebtLedger(itemId, montarPayload(ledger), projecao);
      setLedger(salvo);
      setEdicoes({});
      setSujo(false);
      original.current = {
        mes: mesKey(salvo.origem),
        valor: formatCurrencyInputFromApi(salvo.resumo.principal),
      };
      await onSaved();
      if (salvo.payable_sync_warning) setErro(salvo.payable_sync_warning);
      else onClose();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar.");
    } finally {
      setSalvando(false);
    }
  }

  const r = ledger?.resumo;
  const linhas = useMemo(() => {
    if (!ledger) return [];
    return ledger.tem_correcao ? ledger.linhas : ledger.linhas.filter((l) => !l.is_projected);
  }, [ledger]);

  const mudouParametros =
    original.current != null &&
    (original.current.mes !== inicioMes || original.current.valor !== inicioValor);
  const podeSalvar = !readOnly && !salvando && (sujo || mudouParametros);

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/30 p-4">
      <div className="my-6 w-full max-w-5xl rounded-xl bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-slate-800">Evolução da dívida</h4>
            <p className="mt-0.5 text-xs text-slate-500">
              {titulo}
              {subtitulo ? ` · ${subtitulo}` : null}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            title="Fechar"
          >
            ✕
          </button>
        </div>

        {carregando ? (
          <p className="py-10 text-center text-sm text-slate-500">Carregando…</p>
        ) : !ledger || !r ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {erro ?? "Evolução indisponível."}
          </div>
        ) : (
          <>
            {/* Parâmetros da dívida — o equivalente ao "gerador por faixas" do cronograma. */}
            <div className="mt-4 rounded-lg border border-indigo-200 bg-indigo-50/60 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-800">
                Parâmetros da dívida
              </p>
              <p className="mt-0.5 text-xs text-slate-600">
                De quanto era e desde quando. O restante é digitado na tabela, mês a mês, como na
                planilha.
              </p>
              <div className="mt-3 flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1 text-xs">
                  <span className="font-medium text-slate-600">Mês de início</span>
                  <input
                    type="month"
                    value={inicioMes}
                    disabled={readOnly}
                    onChange={(e) => setInicioMes(e.target.value)}
                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  <span className="font-medium text-slate-600">Valor de origem</span>
                  <input
                    value={inicioValor}
                    disabled={readOnly}
                    onChange={(e) => setInicioValor(e.target.value)}
                    inputMode="decimal"
                    className="w-36 rounded border border-slate-300 px-2 py-1.5 text-sm tabular-nums"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  <span className="font-medium text-slate-600">Projetar</span>
                  <select
                    value={projecao}
                    onChange={(e) => setProjecao(Number(e.target.value))}
                    className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                  >
                    {[0, 3, 6, 12, 24].map((n) => (
                      <option key={n} value={n}>
                        {n === 0 ? "sem projeção" : `${n} meses`}
                      </option>
                    ))}
                  </select>
                </label>
                {/* A origem é a evidência MAIS ANTIGA da dívida: um lançamento anterior ao
                    início informado puxa o razão para trás. Sem dizer isso, o usuário mexe no
                    campo e não entende por que a tabela não obedece. */}
                {inicioMes && mesKey(ledger.origem) !== inicioMes ? (
                  <p className="w-full rounded-md bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900 ring-1 ring-amber-200">
                    A evolução começa em <strong>{mesBr(ledger.origem)}</strong>, e não em{" "}
                    {inicioMes.slice(5, 7)}/{inicioMes.slice(0, 4)}: existe lançamento ou aporte
                    nesse mês anterior. Apague-o para a dívida começar onde você indicou.
                  </p>
                ) : null}
                <p className="ml-auto max-w-sm text-[11px] leading-snug text-slate-600">
                  O <strong>#</strong> da tabela é o número do mês, para conferir linha a linha
                  contra um controle de fora. Na coluna <strong>Taxa</strong>: em branco herda o
                  mês anterior, <strong>0</strong> congela a dívida a partir dali.{" "}
                  {ledger.usando_taxa_padrao ? (
                    <span className="text-indigo-700">
                      Hoje esta dívida corre no padrão do SGC ({taxaBr(r.taxa_vigente)} a.m.).
                    </span>
                  ) : null}
                </p>
              </div>
            </div>

            {/* Gerador de parcelas — o caso "acordo de parcelas fixas COM juros correndo".
                Fica aqui, e não no Cronograma Financeiro, porque é o razão que faz o juro
                incidir sobre o saldo mês a mês. O Cronograma continua sendo o lugar do acordo
                que CONGELA a dívida num total já fechado. */}
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                disabled={readOnly}
                title={readOnly ? readOnlyMessage : undefined}
                onClick={() => setPlanoAberto((v) => !v)}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
              >
                {planoAberto ? "Fechar gerador" : "Gerar parcelas de um acordo"}
              </button>
              {planoResumo ? (
                <p className="flex-1 rounded-md bg-emerald-50 px-2 py-1.5 text-[11px] text-emerald-900 ring-1 ring-emerald-200">
                  {planoResumo}
                </p>
              ) : null}
            </div>

            {planoAberto ? (
              <div className="mt-2 space-y-3 rounded-lg border border-indigo-200 bg-indigo-50/60 p-3">
                <p className="text-xs text-slate-700">
                  Preenche a coluna <strong>Pagamento</strong> dos meses à frente, com o juro
                  incidindo sobre o saldo de cada mês. Os valores entram como rascunho: você
                  confere na tabela e só então salva.
                </p>
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="font-medium text-slate-600">1ª parcela em</span>
                    <input
                      type="month"
                      value={planoMes}
                      onChange={(e) => setPlanoMes(e.target.value)}
                      className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="font-medium text-slate-600">Como o acordo foi feito</span>
                    <select
                      value={planoModo}
                      onChange={(e) => setPlanoModo(e.target.value as DebtPlanMode)}
                      className="rounded border border-slate-300 px-2 py-1.5 text-sm"
                    >
                      <option value="AMORT_FIXA">Abater valor fixo + juros do mês</option>
                      <option value="PARCELA_FIXA">Parcela fixa (juros dentro)</option>
                      <option value="N_PARCELAS">Quitar em N parcelas iguais</option>
                    </select>
                  </label>
                  {planoModo === "N_PARCELAS" ? (
                    <label className="flex flex-col gap-1 text-xs">
                      <span className="font-medium text-slate-600">Parcelas</span>
                      <input
                        value={planoParcelas}
                        onChange={(e) => setPlanoParcelas(e.target.value.replace(/\D/g, ""))}
                        inputMode="numeric"
                        className="w-20 rounded border border-slate-300 px-2 py-1.5 text-sm tabular-nums"
                      />
                    </label>
                  ) : (
                    <label className="flex flex-col gap-1 text-xs">
                      <span className="font-medium text-slate-600">
                        {planoModo === "AMORT_FIXA" ? "Abater por mês" : "Valor da parcela"}
                      </span>
                      <input
                        value={planoValor}
                        onChange={(e) => setPlanoValor(e.target.value)}
                        inputMode="decimal"
                        placeholder="10.000,00"
                        className="w-32 rounded border border-slate-300 px-2 py-1.5 text-sm tabular-nums"
                      />
                    </label>
                  )}
                  <button
                    type="button"
                    disabled={
                      salvando ||
                      !planoMes ||
                      (planoModo === "N_PARCELAS"
                        ? !(Number(planoParcelas) > 0)
                        : !(parseCurrencyInput(planoValor) > 0))
                    }
                    onClick={() => void gerarParcelas()}
                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {salvando ? "Calculando…" : "Gerar"}
                  </button>
                </div>
                <p className="text-[11px] leading-snug text-slate-600">
                  <strong>Abater valor fixo + juros</strong>: você tira o mesmo tanto de dívida
                  todo mês e paga o juro por cima — a parcela cai com o tempo (foi assim o acordo
                  original desta planilha). <strong>Parcela fixa</strong>: você paga sempre o
                  mesmo valor e o juro sai de dentro dele.
                </p>
              </div>
            ) : null}

            <div className="mt-3 max-h-[22rem] overflow-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[54rem] text-sm">
                <thead className="sticky top-0 z-10 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
                  <tr className="border-b border-slate-200">
                    {/* O "#" espelha a coluna Mês (1, 2, 3…) da planilha do financeiro: é por ele
                        que se confere linha a linha contra o controle de fora. Sem ele, um mês de
                        início errado passa despercebido — as datas continuam parecendo certas
                        enquanto a SEQUÊNCIA inteira está deslocada. */}
                    <th className="px-2 py-2 text-right text-slate-400">#</th>
                    <th className="px-2 py-2 text-left">Mês</th>
                    <th className="px-2 py-2 text-right">Saldo inicial</th>
                    <th className="px-2 py-2 text-right">Aporte</th>
                    <th className="px-2 py-2 text-right">Taxa %</th>
                    <th className="px-2 py-2 text-right">Juros</th>
                    <th className="px-2 py-2 text-right">Pagamento</th>
                    <th className="px-2 py-2 text-right">Saldo final</th>
                    <th className="px-2 py-2 text-right">Juros acum.</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {linhas.map((ln, i) => {
                    const mes = mesKey(ln.competencia);
                    const ed = edicoes[mes] ?? {};
                    const vigenciaPropria = ledger.taxas.find((t) => mesKey(t.valid_from) === mes);
                    const primeiraProjecao = ln.is_projected && !linhas[i - 1]?.is_projected;
                    return (
                      <tr
                        key={ln.competencia}
                        className={`${ln.is_projected ? "bg-slate-50/70 text-slate-500" : ""} ${
                          primeiraProjecao ? "border-t-2 border-dashed border-slate-300" : ""
                        }`}
                      >
                        <td className="px-2 py-1 text-right text-xs tabular-nums text-slate-400">{i + 1}</td>
                        <td className="whitespace-nowrap px-2 py-1 font-medium">
                          {mesBr(ln.competencia)}
                          {primeiraProjecao ? (
                            <span className="ml-1.5 rounded bg-slate-200 px-1 py-px text-[9px] uppercase text-slate-600">
                              projeção
                            </span>
                          ) : null}
                        </td>
                        <td className="px-2 py-1 text-right tabular-nums">
                          {formatCurrencyOrDash(ln.saldo_inicial)}
                        </td>
                        <td className="px-2 py-1 text-right">
                          <input
                            value={ed.aporte ?? (ln.aporte > 0 ? formatCurrencyInputFromApi(ln.aporte) : "")}
                            disabled={readOnly}
                            onChange={(e) => editar(mes, "aporte", e.target.value)}
                            className="w-24 rounded border border-slate-200 bg-white px-1.5 py-1 text-right text-sm tabular-nums focus:border-indigo-400"
                            placeholder="—"
                            inputMode="decimal"
                          />
                        </td>
                        <td className="px-2 py-1 text-right">
                          <input
                            value={
                              ed.taxa ?? (vigenciaPropria ? taxaInput(vigenciaPropria.monthly_rate) : "")
                            }
                            disabled={readOnly}
                            onChange={(e) => editar(mes, "taxa", e.target.value)}
                            className={`w-16 rounded border px-1.5 py-1 text-right text-sm tabular-nums focus:border-indigo-400 ${
                              vigenciaPropria ? "border-indigo-300 bg-indigo-50/50" : "border-slate-200 bg-white"
                            }`}
                            // Herdada aparece como sombra: o número que vale, sem estar digitado.
                            placeholder={taxaInput(ln.taxa)}
                            inputMode="decimal"
                          />
                        </td>
                        <td className="px-2 py-1 text-right tabular-nums">
                          {ln.encargo > 0 ? (
                            <span className="text-amber-700">{formatCurrencyOrDash(ln.encargo)}</span>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                        <td className="px-2 py-1 text-right">
                          {/* Mês futuro também aceita valor: é assim que se registra a parcela
                              de um acordo (e é o que o gerador preenche). Conta como PLANO, não
                              como pago — o "Saldo hoje" do rodapé ignora o que está à frente do
                              mês corrente.
                              A caixa edita só a parte da GRADE; o que veio de Retirada de
                              Repasse aparece ao lado, em leitura, porque é lançamento do Ledger
                              (append-only) e não se corrige por aqui. */}
                          {ln.pagamento_repasse > 0 ? (
                            <span
                              className="mr-1.5 rounded bg-violet-50 px-1 py-px text-[10px] font-medium tabular-nums text-violet-700 ring-1 ring-violet-200"
                              title="Retirada do Saldo de Repasse — não gera título no Contas a Pagar"
                            >
                              repasse {formatCurrencyOrDash(ln.pagamento_repasse)}
                            </span>
                          ) : null}
                          <input
                            value={
                              ed.pagamento ??
                              (ln.pagamento - ln.pagamento_repasse > 0
                                ? formatCurrencyInputFromApi(ln.pagamento - ln.pagamento_repasse)
                                : "")
                            }
                            disabled={readOnly}
                            onChange={(e) => editar(mes, "pagamento", e.target.value)}
                            className={`w-28 rounded border border-slate-200 px-1.5 py-1 text-right text-sm tabular-nums focus:border-indigo-400 ${
                              ln.is_projected ? "bg-slate-50" : "bg-white"
                            }`}
                            placeholder="—"
                            inputMode="decimal"
                          />
                        </td>
                        <td className="px-2 py-1 text-right font-medium tabular-nums">
                          {formatCurrencyOrDash(ln.saldo_final)}
                        </td>
                        <td className="px-2 py-1 text-right tabular-nums text-slate-500">
                          {formatCurrencyOrDash(ln.encargo_acumulado)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Fechamento, no mesmo lugar e no mesmo espírito do resumo verde do cronograma. */}
            <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-xs sm:grid-cols-3 lg:grid-cols-5">
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-500">Principal</p>
                <p className="text-sm font-semibold tabular-nums text-slate-800">
                  {formatCurrencyOrDash(r.principal)}
                </p>
                <p className="text-[10px] text-slate-500">desde {mesBr(ledger.origem)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-500">Juros acumulados</p>
                <p className="text-sm font-semibold tabular-nums text-slate-800">
                  {formatCurrencyOrDash(r.total_encargos)}
                </p>
                <p className="text-[10px] text-slate-500">
                  {formatCurrencyOrDash(r.encargos_capitalizados)} no saldo
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-500">Pago</p>
                <p className="text-sm font-semibold tabular-nums text-slate-800">
                  {formatCurrencyOrDash(r.total_pago)}
                </p>
                <p className="text-[10px] text-slate-500">
                  {formatCurrencyOrDash(r.total_amortizado)} amortizaram
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-500">Saldo hoje</p>
                <p className="text-base font-semibold tabular-nums text-emerald-900">
                  {formatCurrencyOrDash(r.saldo_atual)}
                </p>
                <p className="text-[10px] text-slate-500">
                  {r.competencia_final ? `em ${mesBr(r.competencia_final)}` : ""}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-500">Projeção</p>
                <p className="text-sm font-semibold tabular-nums text-slate-800">
                  {r.saldo_projetado != null ? formatCurrencyOrDash(r.saldo_projetado) : "—"}
                </p>
                <p className="text-[10px] text-slate-500">
                  {r.competencia_projecao ? `em ${mesBr(r.competencia_projecao)}, sem pagar` : "sem projeção"}
                </p>
              </div>
            </div>

            {erro ? (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {erro}
              </div>
            ) : null}

            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={!podeSalvar}
                title={readOnly ? readOnlyMessage : undefined}
                onClick={() => void salvar()}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {salvando ? "Salvando…" : "Salvar evolução"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
