import { api } from "./api";

/** Compromisso com data. A agenda é uma visualização destes registros (M4). */
export interface LegalEvent {
  id: string;
  title: string;
  event_type: string;
  scheduled_for: string | null;
  due_at: string | null;
  status: string;
  location: string | null;
  modality: string | null;
  notes: string | null;
  outcome: string | null;
  case_id: string | null;
  case_number: string | null;
  claimant: string | null;
  created_at: string;
}

/** Item da Central de Trabalho — um compromisso com o contexto do processo embutido. */
export interface WorkItem {
  id: string;
  title: string;
  event_type: string;
  scheduled_for: string | null;
  due_at: string | null;
  location: string | null;
  modality: string | null;
  case_id: string | null;
  case_number: string | null;
  claimant: string | null;
  overdue: boolean;
}

export interface WorkCenter {
  today: string;
  agora: WorkItem[];
  semana: WorkItem[];
  sem_dono: { case_id: string; case_number: string; claimant: string | null }[];
  parados: { case_id: string; case_number: string; claimant: string | null; days: number }[];
  stale_days: number;
  proximas_audiencias: WorkItem[];
}

export interface LegalExecutiveSummary {
  em_andamento: number;
  acordos: number;
  valor_acordos: number;
  pendente: number;
  encerrados: number;
}

/** Fato consumado. A timeline nunca mostra futuro — isso é da agenda (M3/M4). */
export interface LegalTimelineEntry {
  id: string;
  occurred_at: string;
  entry_type: string;
  title: string;
  description: string | null;
  source: string;
  is_milestone: boolean;
}

export const EVENT_TYPES: { value: string; label: string }[] = [
  { value: "AUDIENCIA", label: "Audiência" },
  { value: "PERICIA", label: "Perícia" },
  { value: "SESSAO_ARBITRAL", label: "Sessão arbitral" },
  { value: "REUNIAO", label: "Reunião" },
  { value: "PRAZO_PROCESSUAL", label: "Prazo processual" },
  { value: "PRAZO_INTERNO", label: "Prazo interno" },
  { value: "DILIGENCIA", label: "Diligência" },
  { value: "OUTRO", label: "Outro" },
];

export const EVENT_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  EVENT_TYPES.map((t) => [t.value, t.label]),
);

export async function fetchWorkCenter(): Promise<WorkCenter> {
  const { data } = await api.get<WorkCenter>("/legal/work-center");
  return data;
}

export async function fetchLegalSummary(): Promise<LegalExecutiveSummary> {
  const { data } = await api.get<LegalExecutiveSummary>("/legal/summary");
  return data;
}

export async function listEvents(start: Date, end: Date): Promise<LegalEvent[]> {
  const { data } = await api.get<LegalEvent[]>("/legal/events", {
    params: { start: start.toISOString(), end: end.toISOString() },
  });
  return data;
}

export async function createEvent(payload: {
  title: string;
  event_type: string;
  scheduled_for: string | null;
  location?: string | null;
  modality?: string | null;
  notes?: string | null;
  case_id?: string | null;
}): Promise<LegalEvent> {
  const { data } = await api.post<LegalEvent>("/legal/events", payload);
  return data;
}

export async function concludeEvent(id: string, outcome: string | null): Promise<LegalEvent> {
  const { data } = await api.post<LegalEvent>(`/legal/events/${id}/conclude`, { outcome });
  return data;
}

export async function rescheduleEvent(
  id: string,
  newDatetime: string,
  reason: string | null,
): Promise<LegalEvent> {
  const { data } = await api.post<LegalEvent>(`/legal/events/${id}/reschedule`, {
    new_datetime: newDatetime,
    reason,
  });
  return data;
}

export async function fetchCaseTimeline(caseId: string): Promise<LegalTimelineEntry[]> {
  const { data } = await api.get<LegalTimelineEntry[]>(`/legal/cases/${caseId}/timeline`);
  return data;
}

export async function addCaseNote(
  caseId: string,
  payload: { title: string; description?: string | null },
): Promise<LegalTimelineEntry> {
  const { data } = await api.post<LegalTimelineEntry>(`/legal/cases/${caseId}/timeline`, payload);
  return data;
}
