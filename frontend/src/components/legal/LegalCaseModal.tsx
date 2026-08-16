import { DetailMoney, DetailRow, StatusPill, formatDateBR } from "@/components/legal/LegalPanelPieces";
import { LEGAL_STATUS_LABELS, LEGAL_TYPE_LABELS, type LegalCase } from "@/services/legal";

/**
 * Detalhe do processo. Abre sobre a tela (sem trocar de rota) para não perder os filtros —
 * é o comportamento "navegar sem trocar de tela" do Painel de Passivo.
 *
 * `onOpenPerson` liga o processo à sua pessoa; a tela de Processos usa isso para
 * levar o usuário até a ficha da pessoa.
 */
export function LegalCaseModal({
  legalCase,
  onClose,
  onOpenPerson,
}: {
  legalCase: LegalCase;
  onClose: () => void;
  onOpenPerson?: (personId: string) => void;
}) {
  const c = legalCase;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Processo ${c.case_number}`}
      onClick={onClose}
    >
      <div
        className="my-8 w-full max-w-3xl rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold tabular-nums text-slate-900">{c.case_number}</h2>
              <StatusPill status={c.status} label={LEGAL_STATUS_LABELS[c.status]} />
              <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-600">
                {LEGAL_TYPE_LABELS[c.case_type]}
              </span>
            </div>
            <p className="mt-1 truncate text-sm text-slate-500">
              {c.person_name ?? c.claimant_name ?? "Reclamante não identificado"}
              {c.person_cpf ? ` · ${c.person_cpf}` : ""}
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
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Partes</h3>
            <dl className="grid gap-3 sm:grid-cols-2">
              <DetailRow label="Reclamante">{c.claimant_name ?? "—"}</DetailRow>
              <DetailRow label="Reclamado">{c.defendant_name ?? "—"}</DetailRow>
              <DetailRow label="Empresa">{c.company ?? "—"}</DetailRow>
              <DetailRow label="Cliente">{c.client ?? "—"}</DetailRow>
              <DetailRow label="Projeto / Contrato">{c.project ?? "—"}</DetailRow>
              <DetailRow label="Pessoa">
                {c.person_id && onOpenPerson ? (
                  <button
                    type="button"
                    onClick={() => onOpenPerson(c.person_id as string)}
                    className="font-medium text-indigo-600 hover:underline"
                  >
                    {c.person_name ?? "Ver ficha"}
                  </button>
                ) : (
                  (c.person_name ?? "—")
                )}
              </DetailRow>
            </dl>
          </section>

          <section>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Processo</h3>
            <dl className="grid gap-3 sm:grid-cols-3">
              <DetailRow label="Estado">{c.uf ?? "—"}</DetailRow>
              <DetailRow label="Foro">{c.court ?? "—"}</DetailRow>
              <DetailRow label="Comarca">{c.city ?? "—"}</DetailRow>
              <DetailRow label="Classe processual">{c.nature ?? "—"}</DetailRow>
              <DetailRow label="Distribuição">{formatDateBR(c.distribution_date)}</DetailRow>
              <DetailRow label="Audiência">{formatDateBR(c.hearing_date)}</DetailRow>
            </dl>
          </section>

          <section>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Valores</h3>
            <dl className="grid gap-3 sm:grid-cols-3">
              <DetailRow label="Valor da causa">
                <DetailMoney value={c.amount_claimed} />
              </DetailRow>
              <DetailRow label="Valor considerado">
                <DetailMoney value={c.amount_considered} />
              </DetailRow>
              <DetailRow label="Valor acordado">
                <DetailMoney value={c.amount_agreed} />
              </DetailRow>
              <DetailRow label="Valor pago">
                <DetailMoney value={c.amount_paid} />
              </DetailRow>
              <DetailRow label="Valor pendente">
                <DetailMoney value={c.amount_pending} />
              </DetailRow>
              <DetailRow label="Condições do acordo">{c.agreement_terms ?? "—"}</DetailRow>
            </dl>
          </section>

          <section>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Última movimentação
            </h3>
            <p className="text-sm text-slate-700">
              {c.last_movement ?? "Sem movimentação registrada."}
            </p>
            {c.last_movement_date ? (
              <p className="mt-0.5 text-xs text-slate-500">em {formatDateBR(c.last_movement_date)}</p>
            ) : null}
          </section>

          {c.notes ? (
            <section>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Observações
              </h3>
              <p className="whitespace-pre-line text-sm text-slate-700">{c.notes}</p>
            </section>
          ) : null}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-5 py-3">
          {c.jusbrasil_url ? (
            <a
              href={c.jusbrasil_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Abrir no JusBrasil ↗
            </a>
          ) : (
            <span className="text-xs text-slate-400">Sem link do JusBrasil para este processo.</span>
          )}
        </div>
      </div>
    </div>
  );
}
