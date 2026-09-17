import { api } from "@/services/api";

/**
 * Agenda do workspace Projetos.
 *
 * Módulo próprio, sem nenhuma relação com a agenda do Jurídico: os tipos, os endpoints e os
 * registros são exclusivos daqui (ver docs/ETAPA0_AGENDA_PROJETOS.md).
 */

/** ASSUNTO = item de pauta (tem obrigações filhas; não aparece sozinho no calendário). */
export type CommitmentKind = "REUNIAO" | "OBRIGACAO" | "EVENTO" | "VISITA" | "ASSUNTO";
export type CommitmentStatus = "AGENDADO" | "CONCLUIDO" | "CANCELADO" | "ADIADO";
export type CommitmentModality = "PRESENCIAL" | "VIRTUAL" | "HIBRIDA";

export const KIND_LABELS: Record<CommitmentKind, string> = {
  REUNIAO: "Reunião",
  OBRIGACAO: "Obrigação",
  EVENTO: "Evento",
  VISITA: "Visita",
  ASSUNTO: "Item de pauta",
};

/** Cor por tipo — o que permite reconhecer a natureza do compromisso de relance no calendário. */
export const KIND_STYLES: Record<CommitmentKind, string> = {
  REUNIAO: "bg-indigo-100 text-indigo-800 ring-indigo-200",
  OBRIGACAO: "bg-amber-100 text-amber-900 ring-amber-200",
  EVENTO: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  VISITA: "bg-sky-100 text-sky-800 ring-sky-200",
  ASSUNTO: "bg-slate-100 text-slate-700 ring-slate-200",
};

export const MODALITY_LABELS: Record<CommitmentModality, string> = {
  PRESENCIAL: "Presencial",
  VIRTUAL: "Virtual",
  HIBRIDA: "Híbrida",
};

export const STATUS_LABELS: Record<CommitmentStatus, string> = {
  AGENDADO: "Agendado",
  CONCLUIDO: "Concluído",
  CANCELADO: "Cancelado",
  ADIADO: "Adiado",
};

export interface CommitmentParticipant {
  user_id: string;
  full_name: string;
}

export interface CommitmentAttachment {
  id: string;
  file_name: string;
  mime_type: string | null;
  size_bytes: number;
  /** Destaca a ATA da reunião entre os demais documentos. */
  is_minutes: boolean;
  created_at: string;
}

export interface Commitment {
  id: string;
  kind: CommitmentKind;
  title: string;
  description: string | null;
  starts_at: string | null;
  due_at: string | null;
  all_day: boolean;
  duration_minutes: number | null;
  location: string | null;
  modality: CommitmentModality | null;
  project_id: string | null;
  project_name: string | null;
  owner_user_id: string | null;
  /** Nomes de todos os responsáveis, juntos. */
  owner_name: string | null;
  /** Responsáveis (pode haver mais de um); o principal vem primeiro. */
  owners: CommitmentParticipant[];
  /** Obrigação de um item de pauta: o item a que pertence. */
  parent_id: string | null;
  parent_title: string | null;
  external_participants: string | null;
  status: CommitmentStatus;
  completed_at: string | null;
  completion_note: string | null;
  /** Ocorrências da mesma repetição (a gerencial de toda quarta). */
  series_id: string | null;
  /** Tem prazo, já passou e ninguém fechou. Compromisso sem data nunca atrasa. */
  is_overdue: boolean;
  participants: CommitmentParticipant[];
  attachments: CommitmentAttachment[];
  created_by_id: string | null;
}

export interface AgendaCounters {
  overdue: number;
  overdue_mine: number;
  this_week: number;
  this_week_mine: number;
}

export interface AgendaUser {
  id: string;
  full_name: string;
}

export interface CommitmentInput {
  kind: CommitmentKind;
  title: string;
  description?: string | null;
  starts_at?: string | null;
  due_at?: string | null;
  all_day?: boolean;
  duration_minutes?: number | null;
  location?: string | null;
  modality?: CommitmentModality | null;
  project_id?: string | null;
  owner_user_id?: string | null;
  /** Vários responsáveis; tem precedência sobre `owner_user_id`. */
  owner_ids?: string[];
  participant_ids?: string[];
  external_participants?: string | null;
  /** Repetição: a cada quantas semanas, por quantas ocorrências. Ausente = compromisso único. */
  repeat_every_weeks?: number | null;
  repeat_count?: number | null;
  status?: CommitmentStatus;
}

const BASE = "/project-agenda";

export async function listAgendaUsers(): Promise<AgendaUser[]> {
  const { data } = await api.get<AgendaUser[]>(`${BASE}/users`);
  return data;
}

export async function fetchAgendaCounters(): Promise<AgendaCounters> {
  const { data } = await api.get<AgendaCounters>(`${BASE}/counters`);
  return data;
}

export async function listCommitments(params: {
  start?: string;
  end?: string;
  only_mine?: boolean;
  project_id?: string;
  kind?: string;
  status?: string;
}): Promise<Commitment[]> {
  const { data } = await api.get<Commitment[]>(`${BASE}/commitments`, { params });
  return data;
}

export async function createCommitment(payload: CommitmentInput): Promise<Commitment> {
  const { data } = await api.post<Commitment>(`${BASE}/commitments`, payload);
  return data;
}

export async function updateCommitment(
  id: string,
  payload: Partial<CommitmentInput>,
): Promise<Commitment> {
  const { data } = await api.patch<Commitment>(`${BASE}/commitments/${id}`, payload);
  return data;
}

export async function completeCommitment(
  id: string,
  note: string | null,
  meetingId?: string | null,
): Promise<Commitment> {
  const { data } = await api.post<Commitment>(`${BASE}/commitments/${id}/complete`, {
    completion_note: note,
    meeting_id: meetingId ?? null,
  });
  return data;
}

/** Altera o prazo de uma obrigação; de → para e o motivo vão para o histórico do item. */
export async function rescheduleCommitment(
  id: string,
  payload: { due_at: string; reason?: string | null; meeting_id?: string | null },
): Promise<Commitment> {
  const { data } = await api.post<Commitment>(`${BASE}/commitments/${id}/reschedule`, payload);
  return data;
}

export interface ObligationInput {
  title: string;
  description?: string | null;
  owner_ids: string[];
  due_at?: string | null;
}

/** Obrigações de um item de pauta (em aberto primeiro). */
export async function listObligations(itemId: string): Promise<Commitment[]> {
  const { data } = await api.get<Commitment[]>(`${BASE}/commitments/${itemId}/obligations`);
  return data;
}

export async function createObligation(itemId: string, payload: ObligationInput): Promise<Commitment[]> {
  const { data } = await api.post<Commitment[]>(`${BASE}/commitments/${itemId}/obligations`, payload);
  return data;
}

export async function reopenCommitment(id: string): Promise<Commitment> {
  const { data } = await api.post<Commitment>(`${BASE}/commitments/${id}/reopen`, {});
  return data;
}

export async function deleteCommitment(id: string): Promise<void> {
  await api.delete(`${BASE}/commitments/${id}`);
}

export async function uploadCommitmentAttachment(
  id: string,
  file: File,
  isMinutes: boolean,
): Promise<CommitmentAttachment> {
  const form = new FormData();
  form.append("file", file);
  form.append("is_minutes", String(isMinutes));
  const { data } = await api.post<CommitmentAttachment>(`${BASE}/commitments/${id}/attachments`, form);
  return data;
}

export async function deleteCommitmentAttachment(id: string, attachmentId: string): Promise<void> {
  await api.delete(`${BASE}/commitments/${id}/attachments/${attachmentId}`);
}

/** URL do anexo. `inline` abre no navegador (o "Ver"); sem ele, baixa. */
export function commitmentAttachmentUrl(id: string, attachmentId: string, inline: boolean): string {
  return `${BASE}/commitments/${id}/attachments/${attachmentId}${inline ? "?inline=true" : ""}`;
}

// --- pauta da reunião: itens que rolam de uma reunião para a próxima ---------------------

export type CommitmentOutcome = "OPEN" | "DONE" | "PARTIAL" | "EXTENDED";

export const OUTCOME_LABELS: Record<CommitmentOutcome, string> = {
  OPEN: "Em aberto",
  DONE: "Concluído",
  PARTIAL: "Parcial",
  EXTENDED: "Estendido",
};

export const OUTCOME_STYLES: Record<CommitmentOutcome, string> = {
  OPEN: "bg-white text-slate-600 ring-slate-300",
  DONE: "bg-emerald-50 text-emerald-800 ring-emerald-300",
  PARTIAL: "bg-amber-50 text-amber-900 ring-amber-300",
  EXTENDED: "bg-indigo-50 text-indigo-800 ring-indigo-300",
};

export type CommitmentUpdateKind = "OBSERVACAO" | "ATUALIZACAO" | "CONCLUSAO" | "PRAZO";

export const UPDATE_KIND_LABELS: Record<CommitmentUpdateKind, string> = {
  OBSERVACAO: "Observação",
  ATUALIZACAO: "Atualização",
  CONCLUSAO: "Conclusão",
  PRAZO: "Prazo alterado",
};

export const UPDATE_KIND_STYLES: Record<CommitmentUpdateKind, string> = {
  OBSERVACAO: "bg-slate-100 text-slate-700 ring-slate-200",
  ATUALIZACAO: "bg-amber-50 text-amber-900 ring-amber-200",
  CONCLUSAO: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  PRAZO: "bg-sky-50 text-sky-800 ring-sky-200",
};

/** Andamento de um item (linha do tempo). */
export interface CommitmentUpdate {
  id: string;
  commitment_id: string;
  kind: CommitmentUpdateKind;
  body: string;
  author_id: string | null;
  author_name: string | null;
  meeting_id: string | null;
  meeting_date: string | null;
  created_at: string;
}

export async function listCommitmentUpdates(commitmentId: string): Promise<CommitmentUpdate[]> {
  const { data } = await api.get<CommitmentUpdate[]>(`${BASE}/commitments/${commitmentId}/updates`);
  return data;
}

export async function addCommitmentUpdate(
  commitmentId: string,
  payload: { kind: "OBSERVACAO" | "ATUALIZACAO"; body: string; meeting_id?: string | null },
): Promise<CommitmentUpdate[]> {
  const { data } = await api.post<CommitmentUpdate[]>(`${BASE}/commitments/${commitmentId}/updates`, payload);
  return data;
}

export async function deleteCommitmentUpdate(updateId: string): Promise<void> {
  await api.delete(`${BASE}/updates/${updateId}`);
}

export interface AgendaItem extends Commitment {
  occurrence_id: string;
  outcome: CommitmentOutcome;
  /** 1 = nasceu nesta reunião; 2+ = veio estendido de uma anterior. */
  occurrence_number: number;
  total_occurrences: number;
  extended_to_meeting_id: string | null;
  extended_to_date: string | null;
  came_from_date: string | null;
  /** Andamentos do item (todas as reuniões) e o mais recente. */
  updates_count: number;
  last_update: CommitmentUpdate | null;
  /** Resumo das obrigações do item (mostrado na linha da pauta). */
  obligations_total: number;
  obligations_open: number;
  obligations_overdue: number;
}

export interface MeetingOption {
  id: string;
  title: string;
  starts_at: string | null;
  /** Permite destacar a próxima ocorrência da MESMA série ao levar um item adiante. */
  series_id: string | null;
}

export async function listMeetingItems(meetingId: string): Promise<AgendaItem[]> {
  const { data } = await api.get<AgendaItem[]>(`${BASE}/commitments/${meetingId}/items`);
  return data;
}

export async function addMeetingItem(
  meetingId: string,
  payload: {
    title: string;
    description?: string | null;
    external_participants?: string | null;
    project_id?: string | null;
    /** Primeira obrigação do item (opcional). */
    first_obligation?: ObligationInput | null;
  },
): Promise<AgendaItem[]> {
  const { data } = await api.post<AgendaItem[]>(`${BASE}/commitments/${meetingId}/items`, payload);
  return data;
}

/** Marca o desfecho do item NAQUELA reunião. EXTENDED exige a reunião de destino. */
export async function setItemOutcome(
  occurrenceId: string,
  meetingId: string,
  outcome: CommitmentOutcome,
  nextMeetingId?: string | null,
  /** DONE: o que gerou a conclusão; PARTIAL/EXTENDED: o que avançou/falta (vira andamento). */
  note?: string | null,
  /** DONE: concluir junto as obrigações em aberto do item. */
  completeObligations = false,
): Promise<AgendaItem[]> {
  const { data } = await api.post<AgendaItem[]>(
    `${BASE}/occurrences/${occurrenceId}/outcome`,
    {
      outcome,
      next_meeting_id: nextMeetingId ?? null,
      note: note ?? null,
      complete_obligations: completeObligations,
    },
    { params: { meeting_id: meetingId } },
  );
  return data;
}

/** Leva para a pauta da reunião um compromisso que já existe (criado direto no calendário). */
export async function linkMeetingItem(meetingId: string, commitmentId: string): Promise<AgendaItem[]> {
  const { data } = await api.post<AgendaItem[]>(`${BASE}/commitments/${meetingId}/items/link`, {
    commitment_id: commitmentId,
  });
  return data;
}

/** Compromissos em aberto que podem ir para a pauta (sem os que já estão na desta reunião). */
export async function listOpenCommitments(params: { meetingId?: string; q?: string }): Promise<Commitment[]> {
  const { data } = await api.get<Commitment[]>(`${BASE}/open-commitments`, {
    params: { meeting_id: params.meetingId, q: params.q || undefined },
  });
  return data;
}

export async function listUpcomingMeetings(): Promise<MeetingOption[]> {
  const { data } = await api.get<MeetingOption[]>(`${BASE}/meetings`);
  return data;
}

/** Estado da repetição — quantas ocorrências existem e o que um "excluir a série" levaria. */
export interface SeriesSummary {
  series_id: string;
  every_weeks: number;
  total: number;
  /** Desta ocorrência em diante. */
  from_here: number;
  /** Quantas dessas já têm ata ou pauta: apagar aí destrói registro. */
  from_here_with_content: number;
  last_starts_at: string | null;
}

/** 404 quando o compromisso não se repete — o chamador trata como "sem série". */
export async function fetchSeries(commitmentId: string): Promise<SeriesSummary> {
  const { data } = await api.get<SeriesSummary>(`${BASE}/commitments/${commitmentId}/series`);
  return data;
}

/** Acrescenta ocorrências ao FIM da série, no ritmo que ela já tem. */
export async function extendSeries(commitmentId: string, count: number): Promise<Commitment[]> {
  const { data } = await api.post<Commitment[]>(
    `${BASE}/commitments/${commitmentId}/series/extend`,
    { count },
  );
  return data;
}

/** Apaga esta ocorrência e as seguintes. As já realizadas ficam. */
export async function deleteSeriesFrom(commitmentId: string): Promise<number> {
  const { data } = await api.delete<{ deleted: number }>(
    `${BASE}/commitments/${commitmentId}/series`,
  );
  return data.deleted;
}
