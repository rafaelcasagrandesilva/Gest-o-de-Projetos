import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { DebtLedgerModal } from "@/components/company-finance/DebtLedgerModal";
import { fetchDebtLedger, type DebtLedger } from "@/services/companyFinance";
import { formatApiError } from "@/utils/apiError";
import { formatCurrencyOrDash } from "@/utils/currency";

/**
 * Resumo da evolução da dívida no cartão do item — a tela padrão de um endividamento SEM
 * cronograma.
 *
 * Deliberadamente PEQUENO: no cartão fica só a leitura (quatro números e a taxa), e toda a
 * edição vive no modal `DebtLedgerModal`, exatamente como o Cronograma Financeiro faz com o
 * "Gerenciar cronograma". A primeira versão desta tela trazia a planilha inteira inline e ficou
 * grande e confusa demais para um cartão que se expande no meio de uma lista.
 *
 * Nenhuma regra financeira mora aqui: o razão vem calculado do backend
 * (app/services/debt_accrual.py), que é onde ele é testado.
 */

/** "AAAA-MM-01" → "MM/AAAA". */
function mesBr(iso: string): string {
  return `${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
}

function taxaBr(taxa: number): string {
  if (!Number.isFinite(taxa) || taxa === 0) return "0%";
  return `${String(Number((taxa * 100).toFixed(4))).replace(".", ",")}%`;
}

function Stat({ label, value, hint, strong }: { label: string; value: string; hint?: string; strong?: boolean }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`tabular-nums ${strong ? "text-base font-semibold text-slate-900" : "text-sm font-semibold text-slate-800"}`}>
        {value}
      </p>
      {hint ? <p className="text-[10px] leading-tight text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function DebtLedgerPanel({
  itemId,
  titulo,
  subtitulo,
  readOnly,
  readOnlyMessage,
  onSaved,
  refreshKey = 0,
}: {
  itemId: string;
  titulo: string;
  subtitulo?: string | null;
  readOnly: boolean;
  readOnlyMessage: string;
  /** Recarrega o item no cartão de fora (Total pago, Restante, Progresso). */
  onSaved: () => void | Promise<void>;
  refreshKey?: number;
}) {
  const [ledger, setLedger] = useState<DebtLedger | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [modalAberto, setModalAberto] = useState(false);

  const load = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      setLedger(await fetchDebtLedger(itemId, 6));
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Erro ao carregar a evolução da dívida.");
    } finally {
      setCarregando(false);
    }
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (carregando && !ledger) {
    return <p className="py-3 text-center text-xs text-slate-500">Carregando a evolução…</p>;
  }
  if (!ledger) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        {erro ?? "Evolução indisponível."}
      </div>
    );
  }

  const r = ledger.resumo;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Evolução da dívida</p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {ledger.usando_taxa_padrao
              ? `Correndo no padrão do SGC (${taxaBr(r.taxa_vigente)} ao mês) — nenhuma taxa definida para esta dívida.`
              : ledger.tem_correcao
                ? `Correção de ${taxaBr(r.taxa_vigente)} ao mês.`
                : "Dívida congelada — o saldo só muda com pagamento."}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setModalAberto(true)}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
        >
          Gerenciar evolução
        </button>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <Stat label="Principal" value={formatCurrencyOrDash(r.principal)} hint={`desde ${mesBr(ledger.origem)}`} />
        <Stat
          label="Juros acumulados"
          value={formatCurrencyOrDash(r.total_encargos)}
          hint={`${formatCurrencyOrDash(r.encargos_capitalizados)} no saldo`}
        />
        <Stat
          label="Pago"
          value={formatCurrencyOrDash(r.total_pago)}
          hint={`${formatCurrencyOrDash(r.total_amortizado)} amortizaram`}
        />
        <Stat
          label="Saldo hoje"
          value={formatCurrencyOrDash(r.saldo_atual)}
          hint={r.competencia_final ? `em ${mesBr(r.competencia_final)}` : undefined}
          strong
        />
      </div>

      {erro ? <p className="mt-2 text-xs text-red-700">{erro}</p> : null}

      {modalAberto ? (
        <DebtLedgerModal
          itemId={itemId}
          titulo={titulo}
          subtitulo={subtitulo}
          readOnly={readOnly}
          readOnlyMessage={readOnlyMessage}
          onClose={() => setModalAberto(false)}
          onSaved={async () => {
            await load();
            await onSaved();
          }}
        />
      ) : null}
    </div>
  );
}
