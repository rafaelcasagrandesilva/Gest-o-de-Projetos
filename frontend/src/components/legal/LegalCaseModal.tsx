import { useEffect, useMemo, useState } from "react";
import { DetailMoney, DetailRow, StatusPill, formatDateBR } from "@/components/legal/LegalPanelPieces";
import { LegalCaseTimeline } from "@/components/legal/LegalCaseTimeline";
import { usePermission } from "@/hooks/usePermission";
import { LEGAL_STATUS_LABELS, LEGAL_TYPE_LABELS, type LegalCase } from "@/services/legal";
import { EVENT_TYPE_LABELS, listEvents, type LegalEvent } from "@/services/legalOperation";

/**
 * Ficha 360° do processo — a central operacional do caso, não um formulário de cadastro.
 * Abre sobre a tela (sem trocar de rota) para não perder os filtros da listagem.
 *
 * A hierarquia responde, nesta ordem:
 *   1. Resumo           quem é, onde está, quanto vale
 *   2. Próximas ações   o que eu preciso fazer neste processo
 *   3. Timeline         o que já aconteceu (M3)
 *   4. Complementos     financeiro, negociação, documentos e dados do processo
 *
 * Os blocos preparados para as fases seguintes mostram o que JÁ existe hoje e dizem o que entra
 * depois. Nada é inventado (M13): o que não se sabe aparece como "—".
 */

const TIPOS_PRAZO = new Set(["PRAZO_PROCESSUAL", "PRAZO_INTERNO"]);

/** Situação financeira derivada do que existe hoje (status + valores). Fase 2 traz o eixo real. */
function situacaoFinanceira(c: LegalCase): { label: string; tone: string } {
  if (c.status === "ACORDO_FINALIZADO") return { label: "Quitado", tone: "text-emerald-700" };
  if (c.status === "ACORDO") return { label: "Em negociação", tone: "text-amber-700" };
  if ((c.amount_pending ?? 0) > 0) return { label: "A pagar", tone: "text-amber-700" };
  return { label: "Sem obrigação", tone: "text-slate-600" };
}

/** Estado da negociação derivado do status atual — prepara o card da Fase 2. */
function situacaoNegociacao(c: LegalCase): { label: string; detalhe: string; tone: string } {
  if (c.status === "ACORDO_FINALIZADO")
    return {
      label: "Acordo firmado",
      detalhe: c.agreement_terms ?? "Condições registradas no processo.",
      tone: "border-emerald-200 bg-emerald-50 text-emerald-800",
    };
  if (c.status === "ACORDO")
    return {
      label: "Negociação em andamento",
      detalhe: c.agreement_terms ?? "Sem proposta formalizada registrada.",
      tone: "border-amber-200 bg-amber-50 text-amber-900",
    };
  return {
    label: "Sem negociação",
    detalhe: "Nenhuma rodada aberta para este processo.",
    tone: "border-slate-200 bg-slate-50 text-slate-600",
  };
}

const CATEGORIAS_DOCUMENTO = [
  "Inicial",
  "Contestação",
  "Sentença",
  "Acordo",
  "Comprovantes",
  "Ata de audiência",
];

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
  const canWriteTimeline = usePermission("legal_cases.update");
  const [eventos, setEventos] = useState<LegalEvent[]>([]);

  useEffect(() => {
    let cancelled = false;
    // A janela começa ATRÁS de hoje de propósito: compromisso vencido e não concluído continua
    // sendo pendência — e é a mais urgente delas.
    const inicio = new Date();
    inicio.setHours(0, 0, 0, 0);
    inicio.setDate(inicio.getDate() - 90);
    const fim = new Date();
    fim.setDate(fim.getDate() + 180);
    void listEvents(inicio, fim, c.id)
      .then((rows) => {
        if (!cancelled) setEventos(rows.filter((e) => e.status === "AGENDADO"));
      })
      .catch(() => {
        if (!cancelled) setEventos([]);
      });
    return () => {
      cancelled = true;
    };
  }, [c.id]);

  const agora = useMemo(() => new Date(), [eventos]);
  const futuros = useMemo(
    () => eventos.filter((e) => e.scheduled_for && new Date(e.scheduled_for) >= agora),
    [eventos, agora],
  );
  const proximaAudiencia = useMemo(
    () => futuros.find((e) => e.event_type === "AUDIENCIA") ?? null,
    [futuros],
  );
  const proximoPrazo = useMemo(
    () => futuros.find((e) => TIPOS_PRAZO.has(e.event_type)) ?? null,
    [futuros],
  );
  const financeiro = situacaoFinanceira(c);
  const negociacao = situacaoNegociacao(c);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Processo ${c.case_number}`}
      onClick={onClose}
    >
      <div
        className="my-8 w-full max-w-5xl rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* -------- Cabeçalho -------- */}
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-4">
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
          <div className="flex shrink-0 items-center gap-2">
            {c.jusbrasil_url ? (
              <a
                href={c.jusbrasil_url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
              >
                JusBrasil ↗
              </a>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              Fechar
            </button>
          </div>
        </div>

        {/* -------- 1. RESUMO DO CASO -------- */}
        <div className="border-b border-slate-100 bg-slate-50/60 px-6 py-4">
          <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Resumo do caso
          </h3>
          <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
            <Resumo label="Reclamante">
              {c.person_id && onOpenPerson ? (
                <button
                  type="button"
                  onClick={() => onOpenPerson(c.person_id as string)}
                  className="max-w-full truncate text-left text-indigo-700 hover:underline"
                >
                  {c.person_name ?? c.claimant_name ?? "—"}
                </button>
              ) : (
                (c.person_name ?? c.claimant_name ?? "—")
              )}
            </Resumo>
            <Resumo label="Empresa">{c.company ?? "—"}</Resumo>
            <Resumo label="Projeto / contrato">{c.project ?? "—"}</Resumo>
            <Resumo label="Responsável">
              <span className="text-amber-700">Não atribuído</span>
            </Resumo>
            <Resumo label="Etapa">{LEGAL_STATUS_LABELS[c.status]}</Resumo>
            <Resumo label="Situação financeira">
              <span className={financeiro.tone}>{financeiro.label}</span>
            </Resumo>
            <Resumo label="Próxima audiência">
              {proximaAudiencia?.scheduled_for
                ? new Date(proximaAudiencia.scheduled_for).toLocaleDateString("pt-BR")
                : "—"}
            </Resumo>
            <Resumo label="Próximo prazo">
              {proximoPrazo?.scheduled_for
                ? new Date(proximoPrazo.scheduled_for).toLocaleDateString("pt-BR")
                : "—"}
            </Resumo>
            <Resumo label="Última movimentação">
              {c.last_movement_date ? formatDateBR(c.last_movement_date) : "—"}
            </Resumo>
            <Resumo label="Foro / estado">{[c.court, c.uf].filter(Boolean).join(" · ") || "—"}</Resumo>
          </dl>
        </div>

        <div className="grid gap-6 px-6 py-5 lg:grid-cols-3">
          {/* -------- Coluna principal: o que fazer e o que aconteceu -------- */}
          <div className="space-y-6 lg:col-span-2">
            {/* 2. PRÓXIMAS AÇÕES */}
            <section>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  Próximas ações
                </h3>
                <span className="text-[11px] text-slate-400">
                  {eventos.length + 1} pendente{eventos.length + 1 === 1 ? "" : "s"}
                </span>
              </div>
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <ul>
                  {/* Pendência real, derivada do cadastro: ninguém responde por este processo. */}
                  <li className="flex items-center gap-3 border-b border-slate-100 px-4 py-2.5">
                    <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" />
                    <span className="min-w-0 flex-1 text-sm text-slate-800">
                      Definir responsável jurídico
                    </span>
                    <span className="shrink-0 text-xs text-amber-700">pendente</span>
                  </li>
                  {eventos.map((e) => {
                    const atrasado = Boolean(e.scheduled_for && new Date(e.scheduled_for) < agora);
                    return (
                      <li
                        key={e.id}
                        className={`flex items-center gap-3 border-b border-slate-100 px-4 py-2.5 last:border-0 ${
                          atrasado ? "bg-red-50/50" : ""
                        }`}
                      >
                        <span
                          className={`h-2 w-2 shrink-0 rounded-full ${
                            atrasado ? "bg-red-600" : TIPOS_PRAZO.has(e.event_type) ? "bg-red-500" : "bg-indigo-500"
                          }`}
                        />
                        <span className="min-w-0 flex-1 truncate text-sm text-slate-800">
                          {e.title}
                          <span className="ml-2 text-xs text-slate-400">
                            {EVENT_TYPE_LABELS[e.event_type] ?? e.event_type}
                          </span>
                        </span>
                        {atrasado && (
                          <span className="shrink-0 rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-medium text-red-700">
                            atrasado
                          </span>
                        )}
                        <span className="shrink-0 text-xs tabular-nums text-slate-600">
                          {e.scheduled_for
                            ? new Date(e.scheduled_for).toLocaleDateString("pt-BR")
                            : "sem data"}
                        </span>
                      </li>
                    );
                  })}
                  {eventos.length === 0 && (
                    <li className="px-4 py-2.5 text-sm text-slate-500">
                      Nenhum compromisso agendado.{" "}
                      <span className="text-slate-400">Agende pela Agenda do workspace.</span>
                    </li>
                  )}
                </ul>
              </div>
            </section>

            {/* 3. TIMELINE — o elemento central da tela */}
            <LegalCaseTimeline caseId={c.id} canWrite={canWriteTimeline} />
          </div>

          {/* -------- Coluna lateral: complementos -------- */}
          <div className="space-y-5">
            {/* 4. SITUAÇÃO FINANCEIRA */}
            <section className="rounded-lg border border-slate-200 p-4">
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Situação financeira
              </h3>
              <dl className="space-y-2">
                <LinhaValor label="Valor da causa">
                  <DetailMoney value={c.amount_claimed} />
                </LinhaValor>
                <LinhaValor label="Valor considerado">
                  <DetailMoney value={c.amount_considered} />
                </LinhaValor>
                <LinhaValor label="Valor acordado">
                  <DetailMoney value={c.amount_agreed} />
                </LinhaValor>
                <LinhaValor label="Valor pago">
                  <DetailMoney value={c.amount_paid} />
                </LinhaValor>
                <div className="border-t border-slate-100 pt-2">
                  <LinhaValor label="Saldo pendente" destaque>
                    <DetailMoney value={c.amount_pending} />
                  </LinhaValor>
                </div>
              </dl>
              <p className="mt-3 border-t border-slate-100 pt-2 text-[11px] leading-relaxed text-slate-400">
                Parcelas, pagamentos e depósitos entram na Fase 2, integrados ao Contas a Pagar.
              </p>
            </section>

            {/* 5. NEGOCIAÇÃO */}
            <section className="rounded-lg border border-slate-200 p-4">
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Negociação
              </h3>
              <div className={`rounded-lg border px-3 py-2 ${negociacao.tone}`}>
                <p className="text-sm font-medium">{negociacao.label}</p>
                <p className="mt-0.5 text-xs opacity-80">{negociacao.detalhe}</p>
              </div>
              <p className="mt-3 border-t border-slate-100 pt-2 text-[11px] leading-relaxed text-slate-400">
                Rodadas, propostas e contrapropostas entram na Fase 2.
              </p>
            </section>

            {/* 6. DOCUMENTOS */}
            <section className="rounded-lg border border-slate-200 p-4">
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Documentos
              </h3>
              <p className="text-sm text-slate-500">Nenhum documento anexado.</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {CATEGORIAS_DOCUMENTO.map((cat) => (
                  <span
                    key={cat}
                    className="rounded border border-dashed border-slate-200 px-1.5 py-0.5 text-[11px] text-slate-400"
                  >
                    {cat}
                  </span>
                ))}
              </div>
              <p className="mt-3 border-t border-slate-100 pt-2 text-[11px] leading-relaxed text-slate-400">
                Anexos entram na Fase 3, no mesmo volume persistente das NFs.
              </p>
            </section>

            {/* 7. DADOS DO PROCESSO */}
            <section className="rounded-lg border border-slate-200 p-4">
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Dados do processo
              </h3>
              <dl className="grid gap-3">
                <DetailRow label="Reclamado">{c.defendant_name ?? "—"}</DetailRow>
                <DetailRow label="Cliente">{c.client ?? "—"}</DetailRow>
                <DetailRow label="Comarca">{c.city ?? "—"}</DetailRow>
                <DetailRow label="Classe processual">{c.nature ?? "—"}</DetailRow>
                <DetailRow label="Distribuição">
                  {c.distribution_date ? formatDateBR(c.distribution_date) : "—"}
                </DetailRow>
              </dl>
              {c.notes ? (
                <p className="mt-3 whitespace-pre-line border-t border-slate-100 pt-2 text-xs text-slate-600">
                  {c.notes}
                </p>
              ) : null}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

function Resumo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="truncate text-sm text-slate-800">{children}</dd>
    </div>
  );
}

function LinhaValor({
  label,
  children,
  destaque,
}: {
  label: string;
  children: React.ReactNode;
  destaque?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className={`text-xs ${destaque ? "font-medium text-slate-700" : "text-slate-500"}`}>
        {label}
      </dt>
      <dd className={`tabular-nums ${destaque ? "font-semibold text-slate-900" : "text-slate-700"}`}>
        {children}
      </dd>
    </div>
  );
}
