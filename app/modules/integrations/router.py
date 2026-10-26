"""Integrações de sistema para sistema (sem usuário): hoje só o Medição (Fiscalização AT).

Segurança:
- chave no header `X-Integration-Key`; o SGC guarda só o SHA-256 (`MEDICAO_INTEGRATION_KEY_SHA256`);
- só os projetos liberados em `MEDICAO_INTEGRATION_PROJECTS`;
- somente leitura, sem efeito colateral (não gera nem atualiza o Contas a Pagar);
- cada consulta (e cada chave recusada) fica na auditoria; limite de requisições por IP.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.services.audit_service import AuditService, _client_ip
from app.services.medicao_integration import MedicaoIntegrationService, allowed_projects, key_matches

router = APIRouter()

LIMITE_POR_MINUTO = 60
_janelas: dict[str, deque] = defaultdict(deque)
_SEM_ID = UUID(int=0)


def _limitar(request: Request) -> None:
    ip = _client_ip(request) or "?"
    agora = time.monotonic()
    janela = _janelas[ip]
    while janela and agora - janela[0] > 60:
        janela.popleft()
    if len(janela) >= LIMITE_POR_MINUTO:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas requisições. Tente em 1 minuto.")
    janela.append(agora)


async def _autorizar(
    request: Request,
    x_integration_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    _limitar(request)
    if not (settings.medicao_integration_key_sha256 or "").strip():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Integração com o Medição desligada.")
    if not key_matches(x_integration_key, settings.medicao_integration_key_sha256):
        await AuditService(db).log_action(
            user=None, action="denied", entity="integration_medicao", entity_id=_SEM_ID, before=None, after=None,
            context={"path": request.url.path}, request=request, force_log=True,
        )
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de integração inválida.")


def _projeto_liberado(project_id: UUID) -> None:
    if str(project_id).lower() not in allowed_projects(settings.medicao_integration_projects):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Projeto não liberado para a integração.")


async def _auditar(db: AsyncSession, request: Request, project_id: UUID, contexto: dict) -> None:
    await AuditService(db).log_action(
        user=None, action="read", entity="integration_medicao", entity_id=project_id, before=None, after=None,
        context=contexto, request=request, force_log=True,
    )
    await db.commit()


@router.get("/medicao/projects/{project_id}/employees", dependencies=[Depends(_autorizar)])
async def colaboradores(project_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Colaboradores do projeto, para vincular ao cadastro do Medição (id, nome, e-mail, vínculo)."""
    _projeto_liberado(project_id)
    svc = MedicaoIntegrationService(db)
    projeto = await svc.project(project_id)
    if projeto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projeto não encontrado.")
    dados = await svc.employees(projeto)
    await _auditar(db, request, project_id, {"consulta": "colaboradores"})
    return {"project_id": str(project_id), "employees": dados}


@router.get("/medicao/projects/{project_id}/months/{competencia}", dependencies=[Depends(_autorizar)])
async def mes(project_id: UUID, competencia: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Impostos, antecipação, veículos por condutor e folha paga por colaborador do mês (YYYY-MM)."""
    _projeto_liberado(project_id)
    try:
        ano, m = (int(x) for x in competencia.split("-"))
        comp = date(ano, m, 1)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Competência no formato AAAA-MM.") from None
    svc = MedicaoIntegrationService(db)
    projeto = await svc.project(project_id)
    if projeto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projeto não encontrado.")
    dados = await svc.month(projeto, comp)
    await _auditar(db, request, project_id, {"consulta": "mes", "competencia": comp.isoformat()})
    return dados
