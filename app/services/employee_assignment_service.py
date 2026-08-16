"""Alocações contratuais do colaborador — CRUD e a regra que destrava o multi-contrato.

O NÓ que esta camada desata: `create_labor` sempre exigiu que a soma dos percentuais do
colaborador na competência não passasse de 100%. Isso é correto para RATEIO (um custo dividido não
pode virar 130% de si mesmo) e é justamente o que IMPEDIA a remuneração independente — dois
contratos legítimos a 100% somam 200% e eram recusados.

Com o tipo explícito na Alocação a regra fica correta nos dois casos:

    RATEIO        → entra na soma; o teto de 100% continua valendo, sem nenhuma mudança.
    INDEPENDENTE  → NÃO entra na soma; cada contrato paga o seu valor, 100% cada.

Conservador por construção: o teto só é dispensado quando existe uma Alocação INDEPENDENTE
governando aquele par (colaborador, projeto). Par sem Alocação mantém exatamente o comportamento
de hoje — nenhum vínculo antigo muda de regra por omissão.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_assignment import AllocationType, AssignmentStatus, EmployeeAssignment
from app.models.payment_component import PaymentVariableComponent
from app.models.project_operational import ProjectLabor
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.utils import model_to_dict

# Campos de remuneração própria: só existem em INDEPENDENTE.
_OWN_PAY_FIELDS = ("salary_base", "allowance", "hours_per_month", "employment_type")


class EmployeeAssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # Histórico/versionamento pela infraestrutura que o resto do sistema já usa
        # (`audit_logs` com diff em `field_changes`). Não há tabela paralela: quem alterou, quando,
        # e o antes/depois de CADA campo ficam registrados — inclusive mudanças de valor DENTRO da
        # mesma alocação, que de outra forma seriam sobrescritas e perdidas para sempre.
        self.audit = AuditService(session)

    AUDIT_ENTITY = "employee_assignment"

    def _describe(self, row: EmployeeAssignment) -> str:
        alvo = row.project.name if row.project else (row.cost_center or "sem projeto")
        return f"Alocação · {alvo}"

    # -- Consulta -----------------------------------------------------------------------

    async def list_for_employee(
        self,
        employee_id: UUID,
        *,
        include_closed: bool = True,
        include_cancelled: bool = False,
    ) -> list[EmployeeAssignment]:
        """Canceladas ficam FORA por padrão: foram criadas por engano e não devem poluir a tela.
        A linha continua no banco e auditável — some da interface, não do histórico."""
        stmt = select(EmployeeAssignment).where(EmployeeAssignment.employee_id == employee_id)
        if not include_closed:
            stmt = stmt.where(EmployeeAssignment.status == AssignmentStatus.ATIVA)
        elif not include_cancelled:
            stmt = stmt.where(EmployeeAssignment.status != AssignmentStatus.CANCELADA)
        stmt = stmt.order_by(
            EmployeeAssignment.status, EmployeeAssignment.start_date.desc().nullslast(),
            EmployeeAssignment.created_at,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, assignment_id: UUID) -> EmployeeAssignment | None:
        return await self.session.get(EmployeeAssignment, assignment_id)

    async def governing(
        self, *, employee_id: UUID, project_id: UUID, on_date: date | None = None
    ) -> EmployeeAssignment | None:
        """A Alocação que governa este par. Vigente na data quando informada; senão, a ativa."""
        stmt = select(EmployeeAssignment).where(
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.project_id == project_id,
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        if not rows:
            return None
        if on_date is not None:
            vigentes = sorted(
                (r for r in rows if r.is_open_on(on_date)),
                key=lambda r: (r.start_date or date.min, r.created_at),
                reverse=True,
            )
            if vigentes:
                return vigentes[0]
        # Ordem determinística (mais recente primeiro): nunca depender da ordem do banco.
        ativas = sorted(
            (r for r in rows if r.status == AssignmentStatus.ATIVA),
            key=lambda r: (r.start_date or date.min, r.created_at),
            reverse=True,
        )
        return ativas[0] if ativas else None

    async def is_independent(
        self, *, employee_id: UUID, project_id: UUID, on_date: date | None = None
    ) -> bool:
        """True só quando existe Alocação INDEPENDENTE explícita — na dúvida, comportamento antigo."""
        row = await self.governing(employee_id=employee_id, project_id=project_id, on_date=on_date)
        return bool(row and row.allocation_type == AllocationType.INDEPENDENTE)

    async def independent_project_ids(self, employee_id: UUID, on_date: date | None = None) -> set[UUID]:
        """Projetos em que o colaborador tem remuneração INDEPENDENTE.

        Usado pelo teto de 100%: as linhas destes projetos ficam FORA da soma de rateio.
        """
        stmt = select(EmployeeAssignment).where(
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.allocation_type == AllocationType.INDEPENDENTE,
            EmployeeAssignment.project_id.isnot(None),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        out: set[UUID] = set()
        for r in rows:
            if on_date is not None and not r.is_open_on(on_date):
                continue
            if on_date is None and r.status != AssignmentStatus.ATIVA:
                continue
            if r.project_id:
                out.add(r.project_id)
        return out

    # -- Escrita ------------------------------------------------------------------------

    @staticmethod
    def _normalize(data: dict) -> dict:
        """Aplica a semântica do TIPO — a interface e a API não podem divergir aqui.

        INDEPENDENTE: percentual é sempre 100 (elemento neutro do cálculo existente).
        RATEIO: percentual obrigatório entre 1 e 100, e os campos de remuneração própria são
        limpos, porque nesse modelo o valor vem do cadastro do colaborador e é dividido.
        """
        out = dict(data)
        tipo = out.get("allocation_type") or AllocationType.INDEPENDENTE
        tipo = AllocationType(tipo)
        out["allocation_type"] = tipo

        if tipo == AllocationType.INDEPENDENTE:
            out["allocation_percent"] = 100
            return out

        pct = out.get("allocation_percent")
        pct = 100.0 if pct is None else float(pct)
        if pct < 1 or pct > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Em participação em rateio, o percentual deve estar entre 1 e 100.",
            )
        out["allocation_percent"] = pct
        for f in _OWN_PAY_FIELDS:
            out[f] = None
        return out

    async def _assert_rateio_within_100(
        self, *, employee_id: UUID, allocation_percent: float, exclude_id: UUID | None
    ) -> None:
        """Soma apenas as alocações de RATEIO ativas — INDEPENDENTE não disputa esse teto."""
        stmt = select(EmployeeAssignment).where(
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.allocation_type == AllocationType.RATEIO,
            EmployeeAssignment.status == AssignmentStatus.ATIVA,
        )
        rows = [r for r in (await self.session.execute(stmt)).scalars().all() if r.id != exclude_id]
        total = sum(float(r.allocation_percent or 0) for r in rows) + float(allocation_percent)
        if total > 100.0001:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"A soma dos percentuais de RATEIO deste colaborador ficaria em {total:.0f}%. "
                    "Um custo dividido não pode passar de 100%. Se são contratos distintos com "
                    "valores próprios, use o tipo “Remuneração independente”."
                ),
            )

    async def _assert_single_active(
        self, *, employee_id: UUID, project_id: UUID | None, exclude_id: UUID | None
    ) -> None:
        """UMA alocação ATIVA por (colaborador, projeto).

        `governing()` escolhe a alocação que projeta o valor na linha mensal; com duas ativas para
        o mesmo par a escolha seria ambígua e o dinheiro projetado, imprevisível — a mesma classe
        de bug do desempate por cenário no backfill. O banco também garante isso (índice único
        parcial), mas validar aqui devolve uma mensagem legível em vez de erro de constraint.
        """
        if project_id is None:
            return  # alocações só de Centro de Custo podem coexistir
        stmt = select(EmployeeAssignment).where(
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.project_id == project_id,
            EmployeeAssignment.status == AssignmentStatus.ATIVA,
        )
        for r in (await self.session.execute(stmt)).scalars().all():
            if r.id != exclude_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Este colaborador já possui uma alocação ATIVA neste projeto. "
                        "Encerre a atual antes de criar outra — assim o histórico fica correto."
                    ),
                )

    async def create(
        self,
        *,
        employee_id: UUID,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> EmployeeAssignment:
        payload = self._normalize(data)
        if payload["allocation_type"] == AllocationType.RATEIO:
            await self._assert_rateio_within_100(
                employee_id=employee_id,
                allocation_percent=payload["allocation_percent"],
                exclude_id=None,
            )
        await self._assert_single_active(
            employee_id=employee_id, project_id=payload.get("project_id"), exclude_id=None
        )
        row = EmployeeAssignment(employee_id=employee_id, **payload)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        await self.audit.log_action(
            user=actor, action="create", entity=self.AUDIT_ENTITY, entity_id=row.id,
            before=None, after=model_to_dict(row),
            context={"descricao": f"Criou {self._describe(row)}"}, request=request,
        )
        return row

    async def update(
        self,
        assignment_id: UUID,
        data: dict,
        *,
        actor: User | None = None,
        request: Request | None = None,
    ) -> EmployeeAssignment:
        row = await self.get(assignment_id)
        if row is None:
            raise LookupError("Alocação não encontrada.")
        before = model_to_dict(row)
        merged = {
            "allocation_type": data.get("allocation_type", row.allocation_type),
            "allocation_percent": data.get("allocation_percent", row.allocation_percent),
        }
        payload = self._normalize({**data, **merged})
        if payload["allocation_type"] == AllocationType.RATEIO:
            await self._assert_rateio_within_100(
                employee_id=row.employee_id,
                allocation_percent=payload["allocation_percent"],
                exclude_id=row.id,
            )
        await self._assert_single_active(
            employee_id=row.employee_id,
            project_id=payload.get("project_id", row.project_id),
            exclude_id=row.id,
        )
        for key, value in payload.items():
            setattr(row, key, value)
        await self.session.commit()
        await self.session.refresh(row)
        await self.audit.log_action(
            user=actor, action="update", entity=self.AUDIT_ENTITY, entity_id=row.id,
            before=before, after=model_to_dict(row),
            context={"descricao": f"Alterou {self._describe(row)}"}, request=request,
        )
        return row

    async def close(
        self,
        assignment_id: UUID,
        *,
        end_date: date | None = None,
        actor: User | None = None,
        request: Request | None = None,
    ) -> EmployeeAssignment:
        """Encerrar NUNCA apaga: muda o status e carimba a data de fim (histórico é a regra)."""
        row = await self.get(assignment_id)
        if row is None:
            raise LookupError("Alocação não encontrada.")
        before = model_to_dict(row)
        row.status = AssignmentStatus.ENCERRADA
        row.end_date = end_date or date.today()
        await self.session.commit()
        await self.session.refresh(row)
        await self.audit.log_action(
            user=actor, action="update", entity=self.AUDIT_ENTITY, entity_id=row.id,
            before=before, after=model_to_dict(row),
            context={"descricao": f"Encerrou {self._describe(row)}"}, request=request,
        )
        return row

    async def financial_footprint(self, row: EmployeeAssignment) -> dict[str, int]:
        """Quanto esta alocação já produziu de efeito financeiro.

        A pegada é o par (colaborador, projeto) em `project_labors` — é dali que saem Folha, Contas
        a Pagar, custos do projeto e dashboards. Os componentes variáveis de projeto pendem de
        `project_labor_id`, então já estariam cobertos; ainda assim são contados à parte para que a
        mensagem ao usuário diga exatamente o que existe.

        Alocação só de Centro de Custo (sem projeto) não tem pegada por este caminho.
        """
        if row.project_id is None:
            return {"labors": 0, "components": 0}

        labors = (
            await self.session.execute(
                select(func.count())
                .select_from(ProjectLabor)
                .where(
                    ProjectLabor.employee_id == row.employee_id,
                    ProjectLabor.project_id == row.project_id,
                )
            )
        ).scalar_one()

        components = (
            await self.session.execute(
                select(func.count())
                .select_from(PaymentVariableComponent)
                .join(ProjectLabor, ProjectLabor.id == PaymentVariableComponent.project_labor_id)
                .where(
                    ProjectLabor.employee_id == row.employee_id,
                    ProjectLabor.project_id == row.project_id,
                )
            )
        ).scalar_one()

        return {"labors": int(labors), "components": int(components)}

    async def cancel(
        self,
        assignment_id: UUID,
        *,
        reason: str | None = None,
        actor: User | None = None,
        request: Request | None = None,
    ) -> EmployeeAssignment:
        """Cancelar = "isto foi criado por engano". Só vale enquanto NÃO houve efeito financeiro.

        Com efeito financeiro o cancelamento é RECUSADO e o usuário é orientado a Encerrar — assim
        o mês que já foi pago continua explicável, em vez de referenciar um vínculo que "nunca
        existiu". É a diferença entre apagar um erro e reescrever a história.
        """
        row = await self.get(assignment_id)
        if row is None:
            raise LookupError("Alocação não encontrada.")
        if row.status == AssignmentStatus.CANCELADA:
            return row  # idempotente
        if row.status == AssignmentStatus.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Esta alocação já foi encerrada — ela existiu de fato e não pode ser tratada "
                    "como engano. O histórico permanece como está."
                ),
            )

        pegada = await self.financial_footprint(row)
        if pegada["labors"] or pegada["components"]:
            partes = []
            if pegada["labors"]:
                partes.append(f"{pegada['labors']} competência(s) de mão de obra")
            if pegada["components"]:
                partes.append(f"{pegada['components']} componente(s) variável(is)")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Não é possível cancelar: esta alocação já gerou "
                    + " e ".join(partes)
                    + ". Use ENCERRAR para finalizar o vínculo preservando o histórico "
                    "financeiro — cancelar é apenas para alocações criadas por engano."
                ),
            )

        before = model_to_dict(row)
        row.status = AssignmentStatus.CANCELADA
        row.cancelled_at = datetime.now(timezone.utc)
        row.cancelled_by_id = getattr(actor, "id", None)
        await self.session.commit()
        await self.session.refresh(row)
        await self.audit.log_action(
            user=actor, action="update", entity=self.AUDIT_ENTITY, entity_id=row.id,
            before=before, after=model_to_dict(row),
            context={
                "descricao": f"Cancelou {self._describe(row)}",
                "motivo": (reason or "").strip() or "não informado",
                "sem_efeito_financeiro": True,
            },
            request=request,
        )
        return row

    async def reopen(
        self, assignment_id: UUID, *, actor: User | None = None, request: Request | None = None
    ) -> EmployeeAssignment:
        row = await self.get(assignment_id)
        if row is None:
            raise LookupError("Alocação não encontrada.")
        if row.status == AssignmentStatus.CANCELADA:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Alocação cancelada não é reativada: ela representa um cadastro feito por "
                    "engano. Crie uma nova alocação — o cancelamento permanece registrado."
                ),
            )
        before = model_to_dict(row)
        await self._assert_single_active(
            employee_id=row.employee_id, project_id=row.project_id, exclude_id=row.id
        )
        if row.allocation_type == AllocationType.RATEIO:
            await self._assert_rateio_within_100(
                employee_id=row.employee_id,
                allocation_percent=float(row.allocation_percent or 0),
                exclude_id=row.id,
            )
        row.status = AssignmentStatus.ATIVA
        row.end_date = None
        await self.session.commit()
        await self.session.refresh(row)
        await self.audit.log_action(
            user=actor, action="update", entity=self.AUDIT_ENTITY, entity_id=row.id,
            before=before, after=model_to_dict(row),
            context={"descricao": f"Reativou {self._describe(row)}"}, request=request,
        )
        return row
