import { useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { formatApiError } from "@/utils/apiError";
import { listProjects } from "@/services/projects";
import {
  createCommitment,
  KIND_LABELS,
  listAgendaUsers,
  MODALITY_LABELS,
  updateCommitment,
  type AgendaUser,
  type Commitment,
  type CommitmentKind,
  type CommitmentModality,
} from "@/services/projectAgenda";

/**
 * Cadastro de compromisso da Agenda de Projetos.
 *
 * O formulário muda com o TIPO, porque os dois usos pedem coisas diferentes: reunião/evento/visita
 * precisam de hora, local e participantes; obrigação/prazo precisam de responsável e data-limite.
 * Mostrar tudo sempre faria o usuário preencher campo que não se aplica.
 */

/** "2026-09-15T14:30" (input local) → ISO com fuso, que é o que o backend guarda. */
function paraIso(data: string, hora: string): string | null {
  if (!data) return null;
  const dt = new Date(`${data}T${hora || "00:00"}`);
  return Number.isNaN(dt.getTime()) ? null : dt.toISOString();
}

/** ISO do backend → partes para os inputs `date` e `time`. */
function deIso(raw: string | null): { data: string; hora: string } {
  if (!raw) return { data: "", hora: "" };
  const d = new Date(raw);
  const p = (n: number) => String(n).padStart(2, "0");
  return {
    data: `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`,
    hora: `${p(d.getHours())}:${p(d.getMinutes())}`,
  };
}

const TIPOS_COM_HORA: CommitmentKind[] = ["REUNIAO", "EVENTO", "VISITA"];

export function CommitmentModal({
  commitment,
  defaultDate,
  onClose,
  onSaved,
}: {
  commitment: Commitment | null;
  /** Dia clicado no calendário ("AAAA-MM-DD"): o formulário nasce já naquela data. */
  defaultDate?: string | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const editando = Boolean(commitment);
  const inicio = deIso(commitment?.starts_at ?? null);
  const prazo = deIso(commitment?.due_at ?? null);

  const [kind, setKind] = useState<CommitmentKind>(commitment?.kind ?? "REUNIAO");
  const [title, setTitle] = useState(commitment?.title ?? "");
  const [description, setDescription] = useState(commitment?.description ?? "");
  // Ao criar pelo calendário, a data vem do dia clicado; ao editar, do próprio registro.
  const [dataInicio, setDataInicio] = useState(inicio.data || defaultDate || "");
  const [horaInicio, setHoraInicio] = useState(inicio.hora || "09:00");
  const [dataPrazo, setDataPrazo] = useState(prazo.data || (commitment ? "" : defaultDate || ""));
  const [duracao, setDuracao] = useState(commitment?.duration_minutes?.toString() ?? "");
  const [location, setLocation] = useState(commitment?.location ?? "");
  const [modality, setModality] = useState<CommitmentModality>(commitment?.modality ?? "PRESENCIAL");
  const [projectId, setProjectId] = useState(commitment?.project_id ?? "");
  const [ownerId, setOwnerId] = useState(commitment?.owner_user_id ?? "");
  const [participantes, setParticipantes] = useState<string[]>(
    commitment?.participants.map((p) => p.user_id) ?? [],
  );
  const [externos, setExternos] = useState(commitment?.external_participants ?? "");

  const [usuarios, setUsuarios] = useState<AgendaUser[]>([]);
  const [projetos, setProjetos] = useState<{ id: string; name: string }[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    void listAgendaUsers().then(setUsuarios).catch(() => setUsuarios([]));
    void listProjects()
      .then((rows) => setProjetos(rows.map((p) => ({ id: p.id, name: p.name }))))
      .catch(() => setProjetos([]));
  }, []);

  const temHora = useMemo(() => TIPOS_COM_HORA.includes(kind), [kind]);

  async function salvar() {
    setErro(null);
    if (!title.trim()) {
      setErro("Informe o título do compromisso.");
      return;
    }
    setSalvando(true);
    try {
      const payload = {
        kind,
        title: title.trim(),
        description: description.trim() || null,
        starts_at: temHora ? paraIso(dataInicio, horaInicio) : null,
        due_at: dataPrazo ? paraIso(dataPrazo, "23:59") : null,
        duration_minutes: duracao ? Number(duracao) : null,
        location: location.trim() || null,
        modality: temHora ? modality : null,
        project_id: projectId || null,
        owner_user_id: ownerId || null,
        participant_ids: participantes,
        external_participants: externos.trim() || null,
      };
      if (editando && commitment) await updateCommitment(commitment.id, payload);
      else await createCommitment(payload);
      await onSaved();
    } catch (e) {
      setErro(isAxiosError(e) ? formatApiError(e) : "Não foi possível salvar o compromisso.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/30 p-4">
      <div className="my-8 w-full max-w-2xl rounded-xl bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold text-slate-900">
            {editando ? "Editar compromisso" : "Novo compromisso"}
          </h3>
          <button type="button" onClick={onClose} className="rounded px-2 py-1 text-slate-400 hover:bg-slate-100">
            ✕
          </button>
        </div>

        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap gap-2">
            {(Object.keys(KIND_LABELS) as CommitmentKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ring-1 ${
                  kind === k
                    ? "bg-indigo-600 text-white ring-indigo-600"
                    : "bg-white text-slate-700 ring-slate-200 hover:bg-slate-50"
                }`}
              >
                {KIND_LABELS[k]}
              </button>
            ))}
          </div>

          <label className="block text-xs font-medium text-slate-600">
            Título
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={
                kind === "OBRIGACAO"
                  ? "Ex.: Resposta da Vilela Advogados"
                  : "Ex.: Reunião de gestores"
              }
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>

          <label className="block text-xs font-medium text-slate-600">
            {kind === "OBRIGACAO" ? "O que precisa ser feito" : "Descrição"}
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder={
                kind === "OBRIGACAO" ? "Ex.: Trazer o retorno do escritório sobre a renegociação." : "Opcional"
              }
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>

          {/* Reunião/evento/visita acontecem numa HORA; obrigação/prazo têm data-limite. */}
          <div className="flex flex-wrap items-end gap-3">
            {temHora ? (
              <>
                <label className="text-xs font-medium text-slate-600">
                  Data
                  <input
                    type="date"
                    value={dataInicio}
                    onChange={(e) => setDataInicio(e.target.value)}
                    className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                  />
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Hora
                  <input
                    type="time"
                    value={horaInicio}
                    onChange={(e) => setHoraInicio(e.target.value)}
                    className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                  />
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Duração (min)
                  <input
                    value={duracao}
                    onChange={(e) => setDuracao(e.target.value.replace(/\D/g, ""))}
                    inputMode="numeric"
                    placeholder="60"
                    className="mt-1 block w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                  />
                </label>
              </>
            ) : null}
            <label className="text-xs font-medium text-slate-600">
              {temHora ? "Prazo (opcional)" : "Prazo limite"}
              <input
                type="date"
                value={dataPrazo}
                onChange={(e) => setDataPrazo(e.target.value)}
                className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              />
            </label>
          </div>

          {temHora ? (
            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-[14rem] flex-1 text-xs font-medium text-slate-600">
                Local
                <input
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="Sede, sala 2 — ou o link da chamada"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                />
              </label>
              <label className="text-xs font-medium text-slate-600">
                Modalidade
                <select
                  value={modality}
                  onChange={(e) => setModality(e.target.value as CommitmentModality)}
                  className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                >
                  {(Object.keys(MODALITY_LABELS) as CommitmentModality[]).map((m) => (
                    <option key={m} value={m}>{MODALITY_LABELS[m]}</option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}

          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[13rem] flex-1 text-xs font-medium text-slate-600">
              Responsável {kind === "REUNIAO" ? "(quem convocou)" : ""}
              <select
                value={ownerId}
                onChange={(e) => setOwnerId(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              >
                <option value="">Sem responsável</option>
                {usuarios.map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
            </label>
            <label className="min-w-[13rem] flex-1 text-xs font-medium text-slate-600">
              Projeto (opcional)
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              >
                <option value="">Sem projeto</option>
                {projetos.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </label>
          </div>

          <div>
            <p className="text-xs font-medium text-slate-600">Participantes</p>
            <div className="mt-1 flex flex-wrap gap-1.5 rounded-lg border border-slate-200 p-2">
              {usuarios.map((u) => {
                const marcado = participantes.includes(u.id);
                return (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() =>
                      setParticipantes((prev) =>
                        marcado ? prev.filter((x) => x !== u.id) : [...prev, u.id],
                      )
                    }
                    className={`rounded-full px-2 py-0.5 text-xs ring-1 ${
                      marcado
                        ? "bg-indigo-600 text-white ring-indigo-600"
                        : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    {u.full_name}
                  </button>
                );
              })}
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              O responsável entra como participante automaticamente.
            </p>
          </div>

          <label className="block text-xs font-medium text-slate-600">
            Participantes externos
            <input
              value={externos}
              onChange={(e) => setExternos(e.target.value)}
              placeholder="Quem não tem acesso ao sistema — ex.: Vilela Advogados"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
        </div>

        {erro ? (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{erro}</div>
        ) : null}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
            Cancelar
          </button>
          <button
            type="button"
            disabled={salvando || !title.trim()}
            onClick={() => void salvar()}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {salvando ? "Salvando…" : "Salvar compromisso"}
          </button>
        </div>
      </div>
    </div>
  );
}
