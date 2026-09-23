import { useState } from "react";
import { Dialog } from "@/components/project-agenda/AgendaDialogs";
import { CommitmentUpdates } from "@/components/project-agenda/CommitmentUpdates";
import { AgendaMeetingsInfo, ItemObligations } from "@/components/project-agenda/ItemObligations";
import type { AgendaItem, AgendaUser } from "@/services/projectAgenda";

/**
 * Um item de pauta aberto: as OBRIGAÇÕES dele e o histórico.
 *
 * O item é o assunto; quem cobra são as obrigações — cada uma com um ou mais responsáveis e prazo,
 * e cada uma aparece no calendário e no "só os meus" de todos os responsáveis. Na reunião, cada
 * obrigação recebe conclusão ou prazo novo, e novas obrigações nascem aqui. A pauta mostra só o
 * título e o resumo; o detalhe vive nesta janela.
 *
 * O painel de obrigações é o MESMO do detalhe aberto pelo calendário (ItemObligations).
 */

export function AgendaItemDialog({
  item,
  meetingId,
  users,
  podeEditar,
  onChanged,
  onClose,
}: {
  item: AgendaItem;
  meetingId: string;
  users: AgendaUser[];
  podeEditar: boolean;
  onChanged: () => void | Promise<void>;
  onClose: () => void;
}) {
  const [historicoAberto, setHistoricoAberto] = useState(false);
  /** Muda a cada alteração para o histórico recarregar (conclusões e prazos entram lá). */
  const [versao, setVersao] = useState(0);

  return (
    <Dialog
      title={item.title}
      subtitle={item.external_participants ? `Envolvidos: ${item.external_participants}` : undefined}
      wide="xl"
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
          Fechar
        </button>
      }
    >
      <div className="mb-3">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Em pauta {item.occurrence_number > 1 ? `· ${item.occurrence_number}ª vez` : ""}
        </p>
        <AgendaMeetingsInfo pautas={item.agenda_meetings ?? []} reuniaoAtualId={meetingId} />
      </div>
      {item.description ? (
        <p className="mb-3 whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">{item.description}</p>
      ) : null}

      <ItemObligations
        itemId={item.id}
        meetingId={meetingId}
        users={users}
        podeEditar={podeEditar}
        onChanged={async () => {
          setVersao((v) => v + 1);
          await onChanged();
        }}
      />

      {/* Histórico recolhido: conclusões, prazos alterados e atualizações. Não ocupa a tela. */}
      <div className="mt-4 rounded-lg border border-slate-200">
        <button
          type="button"
          onClick={() => setHistoricoAberto((v) => !v)}
          className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 hover:bg-slate-50"
        >
          <span>Histórico e atualizações</span>
          <span className={`transition-transform ${historicoAberto ? "rotate-90" : ""}`}>›</span>
        </button>
        {historicoAberto ? (
          <div className="border-t border-slate-100 p-3">
            <CommitmentUpdates key={versao} commitmentId={item.id} meetingId={meetingId} podeEditar={podeEditar} />
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
