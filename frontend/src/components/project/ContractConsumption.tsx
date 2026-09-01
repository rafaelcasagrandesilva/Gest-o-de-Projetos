import { formatCurrencyOrDash, formatCurrencyShortOrDash } from "@/utils/currency";
import type { Project } from "@/services/projects";

/**
 * Consumo do contrato — quanto do valor contratado já foi faturado.
 *
 * REGRA DO NEGÓCIO: entra apenas **NF faturada** (não cancelada). Pré-faturadas ficam de fora,
 * mesmo quando representam valor relevante — decisão registrada em 01/09/2026.
 *
 * A base é o valor do contrato somado aos aditivos. Sem valor de contrato cadastrado, a tela diz
 * "não informado" em vez de exibir um percentual inventado.
 */

/** Faixas de atenção: o contrato apertando é informação de gestão, não decoração. */
function faixa(pct: number): { barra: string; texto: string } {
  if (pct >= 100) return { barra: "bg-red-600", texto: "text-red-700" };
  if (pct >= 80) return { barra: "bg-amber-500", texto: "text-amber-700" };
  return { barra: "bg-indigo-600", texto: "text-indigo-700" };
}

/** Versão compacta para a lista de projetos: barra + percentual. */
export function ContractConsumptionBar({ project }: { project: Project }) {
  const pct = project.contract_consumed_pct;
  if (pct == null) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  const cor = faixa(pct);
  // Só o percentual e a barra: o valor cheio está no detalhe e no title, para a coluna não
  // roubar largura das ações da linha.
  return (
    <div
      className="flex w-24 flex-col gap-1"
      title={`Faturado ${formatCurrencyOrDash(project.invoiced_total)} de ${formatCurrencyOrDash(
        project.contract_total_value,
      )} (${formatCurrencyShortOrDash(project.contract_balance)} a faturar)`}
    >
      <span className={`text-sm font-semibold tabular-nums ${cor.texto}`}>
        {pct.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%
      </span>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${cor.barra}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    </div>
  );
}

/** Versão detalhada para a aba Contrato: os quatro números que sustentam o percentual. */
export function ContractConsumptionPanel({ project }: { project: Project }) {
  const pct = project.contract_consumed_pct;
  const cor = pct == null ? null : faixa(pct);

  return (
    <section className="rounded-lg border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Consumo do contrato
        </h4>
        <span className="text-[11px] text-slate-400">somente NFs faturadas</span>
      </div>

      {pct == null ? (
        <p className="mt-3 text-sm text-slate-500">
          Valor do contrato não informado — preencha o campo acima para acompanhar o consumo.
        </p>
      ) : (
        <>
          <div className="mt-3 flex items-end justify-between gap-4">
            <div>
              <p className={`text-3xl font-semibold tabular-nums ${cor?.texto}`}>
                {pct.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%
              </p>
              <p className="text-xs text-slate-500">do contrato já faturado</p>
            </div>
            {pct >= 100 ? (
              <span className="rounded bg-red-100 px-2 py-1 text-xs font-medium text-red-700">
                contrato estourado
              </span>
            ) : pct >= 80 ? (
              <span className="rounded bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800">
                atenção — acima de 80%
              </span>
            ) : null}
          </div>

          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-200">
            <div className={`h-full rounded-full ${cor?.barra}`} style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>

          <dl className="mt-4 grid gap-3 sm:grid-cols-3">
            <Numero label="Contrato + aditivos" valor={project.contract_total_value} />
            <Numero label="Faturado" valor={project.invoiced_total} />
            <Numero
              label="Saldo a faturar"
              valor={project.contract_balance}
              destaque={(project.contract_balance ?? 0) < 0 ? "text-red-700" : undefined}
            />
          </dl>

          {(project.additive_value_total ?? 0) > 0 && (
            <p className="mt-3 border-t border-slate-200 pt-2 text-[11px] text-slate-500">
              Inclui {formatCurrencyOrDash(project.additive_value_total)} em aditivos contratuais.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function Numero({
  label,
  valor,
  destaque,
}: {
  label: string;
  valor: number | null | undefined;
  destaque?: string;
}) {
  return (
    <div>
      <dt className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`text-sm font-medium tabular-nums ${destaque ?? "text-slate-800"}`}>
        {formatCurrencyOrDash(valor)}
      </dd>
    </div>
  );
}
