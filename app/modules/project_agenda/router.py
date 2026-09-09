"""Agenda do workspace Projetos.

Recurso próprio (`project_agenda.*`), um por menu, como o resto do sistema. Nenhum endpoint
daqui lê ou escreve nada do módulo Jurídico — as duas agendas são independentes por decisão de
produto (ver docs/ETAPA0_AGENDA_PROJETOS.md).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.permission_codes import (
    PROJECT_AGENDA_CREATE,
    PROJECT_AGENDA_DELETE,
    PROJECT_AGENDA_LIST,
    PROJECT_AGENDA_READ,
    PROJECT_AGENDA_UPDATE,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.project_agenda import (
    AgendaCountersRead,
    AgendaItemCreate,
    AgendaItemOutcome,
    AgendaItemRead,
    AgendaUserRead,
    CommitmentAttachmentRead,
    CommitmentComplete,
    CommitmentCreate,
    CommitmentRead,
    CommitmentUpdate,
    MeetingOptionRead,
)
from app.services.project_agenda_service import ProjectAgendaService
from app.utils.media_type import resolve_media_type

router = APIRouter()

_list = [Depends(require_permission(PROJECT_AGENDA_LIST))]
_read = [Depends(require_permission(PROJECT_AGENDA_READ))]
_create = [Depends(require_permission(PROJECT_AGENDA_CREATE))]
_update = [Depends(require_permission(PROJECT_AGENDA_UPDATE))]
_delete = [Depends(require_permission(PROJECT_AGENDA_DELETE))]


@router.get("/users", response_model=list[AgendaUserRead], dependencies=_list)
async def list_agenda_users(db: AsyncSession = Depends(get_db)) -> list[AgendaUserRead]:
    """Usuários selecionáveis como responsável/participante.

    Só usuários ATIVOS: atribuir a quem não entra mais no sistema é o mesmo que não atribuir.
    """
    rows = (
        await db.execute(
            select(User.id, User.full_name)
            .where(User.is_active.is_(True), User.deleted_at.is_(None))
            .order_by(User.full_name)
        )
    ).all()
    return [AgendaUserRead(id=uid, full_name=nome) for uid, nome in rows]


@router.get("/counters", response_model=AgendaCountersRead, dependencies=_list)
async def agenda_counters(
    db: AsyncSession = Depends(get_db), actor: User = Depends(get_current_user)
) -> AgendaCountersRead:
    """Atrasados e desta semana, no total e os do usuário logado."""
    return AgendaCountersRead.model_validate(await ProjectAgendaService(db).counters(user_id=actor.id))


@router.get("/commitments", response_model=list[CommitmentRead], dependencies=_list)
async def list_commitments(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    only_mine: bool = Query(default=False),
    project_id: UUID | None = Query(default=None),
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> list[CommitmentRead]:
    """Compromissos da janela. `only_mine` traz o que o usuário responde OU participa."""
    svc = ProjectAgendaService(db)
    rows = await svc.list_between(
        start=start,
        end=end,
        only_user_id=actor.id if only_mine else None,
        project_id=project_id,
        kind=kind,
        status=status,
    )
    return [CommitmentRead.model_validate(r) for r in await svc.to_read(rows)]


@router.post("/commitments", response_model=CommitmentRead, status_code=201, dependencies=_create)
async def create_commitment(
    payload: CommitmentCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CommitmentRead:
    svc = ProjectAgendaService(db)
    dados = payload.model_dump()
    semanas = dados.pop("repeat_every_weeks", None)
    quantas = dados.pop("repeat_count", None)
    if semanas and quantas:
        # Repetição: cria as ocorrências de uma vez. A primeira é a que volta na resposta.
        criadas = await svc.create_series(
            data=dados, every_weeks=semanas, count=quantas, actor_id=actor.id
        )
        await db.commit()
        return await _one(svc, criadas[0].id)
    row = await svc.create(data=dados, actor_id=actor.id)
    await db.commit()
    return (await _one(svc, row.id))


@router.get("/commitments/{commitment_id}", response_model=CommitmentRead, dependencies=_read)
async def get_commitment(
    commitment_id: UUID, db: AsyncSession = Depends(get_db)
) -> CommitmentRead:
    return await _one(ProjectAgendaService(db), commitment_id)


@router.get("/meetings", response_model=list[MeetingOptionRead], dependencies=_list)
async def list_upcoming_meetings(db: AsyncSession = Depends(get_db)) -> list[MeetingOptionRead]:
    """Reuniões futuras — o destino possível de um item estendido."""
    rows = await ProjectAgendaService(db).upcoming_meetings()
    return [
        MeetingOptionRead(id=r.id, title=r.title, starts_at=r.starts_at, series_id=r.series_id)
        for r in rows
    ]


@router.get(
    "/commitments/{commitment_id}/items", response_model=list[AgendaItemRead], dependencies=_read
)
async def list_meeting_items(
    commitment_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[AgendaItemRead]:
    """Itens em pauta nesta reunião, com o desfecho dela e quantas vezes o assunto já rolou."""
    return [
        AgendaItemRead.model_validate(d)
        for d in await ProjectAgendaService(db).agenda_items(commitment_id)
    ]


@router.post(
    "/commitments/{commitment_id}/items",
    response_model=list[AgendaItemRead],
    status_code=201,
    dependencies=_create,
)
async def add_meeting_item(
    commitment_id: UUID,
    payload: AgendaItemCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> list[AgendaItemRead]:
    """Anota uma linha da ata. O item vira compromisso e entra em pauta nesta reunião."""
    svc = ProjectAgendaService(db)
    if await svc._load(commitment_id) is None:
        raise HTTPException(status_code=404, detail="Reunião não encontrada.")
    await svc.add_agenda_item(
        meeting_id=commitment_id, data=payload.model_dump(), actor_id=actor.id
    )
    await db.commit()
    return [AgendaItemRead.model_validate(d) for d in await svc.agenda_items(commitment_id)]


@router.post(
    "/occurrences/{occurrence_id}/outcome",
    response_model=list[AgendaItemRead],
    dependencies=_update,
)
async def set_item_outcome(
    occurrence_id: UUID,
    payload: AgendaItemOutcome,
    meeting_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[AgendaItemRead]:
    """Marca o desfecho do item nesta reunião: concluído, parcial ou estendido para a próxima."""
    svc = ProjectAgendaService(db)
    await svc.set_outcome(
        occurrence_id=occurrence_id,
        outcome=payload.outcome,
        next_meeting_id=payload.next_meeting_id,
    )
    await db.commit()
    return [AgendaItemRead.model_validate(d) for d in await svc.agenda_items(meeting_id)]


@router.patch("/commitments/{commitment_id}", response_model=CommitmentRead, dependencies=_update)
async def update_commitment(
    commitment_id: UUID,
    payload: CommitmentUpdate,
    db: AsyncSession = Depends(get_db),
) -> CommitmentRead:
    svc = ProjectAgendaService(db)
    row = await svc.update(commitment_id=commitment_id, data=payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado.")
    await db.commit()
    return await _one(svc, commitment_id)


@router.post("/commitments/{commitment_id}/complete", response_model=CommitmentRead, dependencies=_update)
async def complete_commitment(
    commitment_id: UUID,
    payload: CommitmentComplete,
    db: AsyncSession = Depends(get_db),
) -> CommitmentRead:
    """Fecha o ciclo da obrigação atribuída: quem entregou marca como concluído."""
    svc = ProjectAgendaService(db)
    if await svc.complete(commitment_id=commitment_id, note=payload.completion_note) is None:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado.")
    await db.commit()
    return await _one(svc, commitment_id)


@router.post("/commitments/{commitment_id}/reopen", response_model=CommitmentRead, dependencies=_update)
async def reopen_commitment(
    commitment_id: UUID, db: AsyncSession = Depends(get_db)
) -> CommitmentRead:
    svc = ProjectAgendaService(db)
    if await svc.reopen(commitment_id=commitment_id) is None:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado.")
    await db.commit()
    return await _one(svc, commitment_id)


@router.delete("/commitments/{commitment_id}", status_code=204, dependencies=_delete)
async def delete_commitment(commitment_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    if not await ProjectAgendaService(db).delete(commitment_id=commitment_id):
        raise HTTPException(status_code=404, detail="Compromisso não encontrado.")
    await db.commit()


# --- anexos (a ATA da reunião e documentos de apoio) --------------------------------------


@router.post(
    "/commitments/{commitment_id}/attachments",
    response_model=CommitmentAttachmentRead,
    status_code=201,
    dependencies=_update,
)
async def upload_attachment(
    commitment_id: UUID,
    file: UploadFile = File(...),
    is_minutes: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> CommitmentAttachmentRead:
    """Anexa um arquivo ao compromisso. `is_minutes` marca a ATA entre os documentos."""
    svc = ProjectAgendaService(db)
    if await svc._load(commitment_id) is None:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado.")
    row = await svc.add_attachment(
        commitment_id=commitment_id,
        file_name=file.filename or "anexo",
        body=await file.read(),
        mime_type=file.content_type,
        is_minutes=is_minutes,
        actor_id=actor.id,
    )
    await db.commit()
    return CommitmentAttachmentRead.model_validate(
        {
            "id": row.id,
            "file_name": row.file_name,
            "mime_type": row.mime_type,
            "size_bytes": row.size_bytes,
            "is_minutes": row.is_minutes,
            "created_at": row.created_at,
        }
    )


@router.get("/commitments/{commitment_id}/attachments/{attachment_id}", dependencies=_read)
async def download_attachment(
    commitment_id: UUID,
    attachment_id: UUID,
    inline: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Baixa (ou abre) o anexo. `inline=true` é o "Ver" — regra única de anexos do sistema."""
    svc = ProjectAgendaService(db)
    row = await svc.get_attachment(commitment_id=commitment_id, attachment_id=attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Anexo não encontrado.")
    caminho = svc.disk_path(row)
    if not caminho.is_file():
        raise HTTPException(
            status_code=404,
            detail="Arquivo não encontrado no armazenamento do servidor. Reenvie o anexo.",
        )
    headers = {"Content-Disposition": f'inline; filename="{row.file_name}"'} if inline else None
    return FileResponse(
        caminho,
        media_type=resolve_media_type(row.mime_type, row.file_name),
        filename=None if inline else row.file_name,
        headers=headers,
    )


@router.delete(
    "/commitments/{commitment_id}/attachments/{attachment_id}", status_code=204, dependencies=_update
)
async def delete_attachment(
    commitment_id: UUID, attachment_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    if not await ProjectAgendaService(db).delete_attachment(
        commitment_id=commitment_id, attachment_id=attachment_id
    ):
        raise HTTPException(status_code=404, detail="Anexo não encontrado.")
    await db.commit()


async def _one(svc: ProjectAgendaService, commitment_id: UUID) -> CommitmentRead:
    row = await svc._load(commitment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado.")
    return CommitmentRead.model_validate((await svc.to_read([row]))[0])
