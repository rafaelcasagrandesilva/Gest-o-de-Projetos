import { Money } from "@/components/Money";
import { DetailMoney, DetailRow, StatusPill, formatCount, formatDateBR } from "@/components/legal/LegalPanelPieces";
import { LEGAL_STATUS_LABELS, type LegalCase, type LegalPersonDetail } from "@/services/legal";

/**
 * Ficha da pessoa: dados pessoais/contratuais, totais derivados dos processos e a LISTA
 * dos processos relacionados. Clicar num processo entrega o controle ao chamador (`onOpenCase`),
 * que abre o detalhe — é a navegação "colaborador → processo" pedida na especificação.
 */
export function LegalPersonModal({
  person,
  onClose,
  onOpenCase,
  onSeeAllCases,
}: {
  person: LegalPersonDetail;
  onClose: () => void;
  onOpenCase: (legalCase: LegalCase) => void;
  onSeeAllCases?: (personId: string) => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Pessoa ${person.full_name}`}
      onClick={onClose}
    >
      <div
        className="my-8 w-full max-w-4xl rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold text-slate-900">{person.full_name}</h2>
            <p className="mt-0.5 text-sm text-slate-500">
              {person.cpf ?? "CPF não informado"}
              {person.role ? ` · ${person.role}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            Fechar
          </button>
        </div>

        <div className="space-y-5 px-5 py-4">
          <section>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Vínculo</h3>
            <dl className="grid gap-3 sm:grid-cols-3">
              <DetailRow label="Empresa">{person.company ?? "—"}</DetailRow>
              <DetailRow label="Projeto / Contrato">{person.project ?? "—"}</DetailRow>
              <DetailRow label="Cliente">{person.client ?? "—"}</DetailRow>
              <DetailRow label="Admissão">{formatDateBR(person.admission_date)}</DetailRow>
              <DetailRow label="Desligamento">{formatDateBR(person.termination_date)}</DetailRow>
              <DetailRow label="Processos">{formatCount(person.case_count)}</DetailRow>
              <DetailRow label="Valor da rescisão">
                <DetailMoney value={person.severance_amount} />
              </DetailRow>
              <DetailRow label="Saldo FGTS">
                <DetailMoney value={person.fgts_balance} />
              </DetailRow>
            </dl>
          </section>

          <section>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Totais dos processos
            </h3>
            <dl className="grid gap-3 sm:grid-cols-5">
              <DetailRow label="Valor da causa">
                <DetailMoney value={person.total_claimed} />
              </DetailRow>
              <DetailRow label="Considerado">
                <DetailMoney value={person.total_considered} />
              </DetailRow>
              <DetailRow label="Acordado">
                <DetailMoney value={person.total_agreed} />
              </DetailRow>
              <DetailRow label="Pago">
                <DetailMoney value={person.total_paid} />
              </DetailRow>
              <DetailRow label="Pendente">
                <DetailMoney value={person.total_pending} />
              </DetailRow>
            </dl>
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between gap-3">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Processos relacionados
              </h3>
              {person.case_count > 0 && onSeeAllCases ? (
                <button
                  type="button"
                  onClick={() => onSeeAllCases(person.id)}
                  className="text-xs font-medium text-indigo-600 hover:underline"
                >
                  Ver na tela de Processos →
                </button>
              ) : null}
            </div>
            {person.cases.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-200 py-6 text-center text-sm text-slate-400">
                Esta pessoa não possui processo cadastrado.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-3 py-2 font-semibold">Processo</th>
                      <th className="px-3 py-2 font-semibold">UF</th>
                      <th className="px-3 py-2 font-semibold">Status</th>
                      <th className="px-3 py-2 text-right font-semibold">Considerado</th>
                      <th className="px-3 py-2 text-right font-semibold">Valor da causa</th>
                      <th className="px-3 py-2 text-center font-semibold">JusBrasil</th>
                    </tr>
                  </thead>
                  <tbody>
                    {person.cases.map((c) => (
                      <tr key={c.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                        <td className="px-3 py-2">
                          <button
                            type="button"
                            onClick={() => onOpenCase(c)}
                            className="font-medium tabular-nums text-indigo-600 hover:underline"
                          >
                            {c.case_number}
                          </button>
                        </td>
                        <td className="px-3 py-2 text-slate-600">{c.uf ?? "—"}</td>
                        <td className="px-3 py-2">
                          <StatusPill status={c.status} label={LEGAL_STATUS_LABELS[c.status]} />
                        </td>
                        <td className="px-3 py-2">
                          <Money value={c.amount_considered} />
                        </td>
                        <td className="px-3 py-2">
                          <Money value={c.amount_claimed} />
                        </td>
                        <td className="px-3 py-2 text-center">
                          {c.jusbrasil_url ? (
                            <a
                              href={c.jusbrasil_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              title="Abrir no JusBrasil"
                              className="text-indigo-600 hover:underline"
                            >
                              ↗
                            </a>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {person.notes ? (
            <section>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Observações
              </h3>
              <p className="whitespace-pre-line text-sm text-slate-700">{person.notes}</p>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
