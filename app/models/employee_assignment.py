"""Alocação do colaborador — o vínculo CONTRATUAL entre a pessoa e um contrato/centro de custo.

Camada acima de `ProjectLabor`, não substituta dele:

    Employee  →  1..N EmployeeAssignment  (contrato: vale de tal data a tal data)
                        ↓ gera
                 ProjectLabor              (execução: uma linha por competência)
                        ↓ já alimenta
                 Folha · Contas a Pagar · custos de projeto · dashboards · relatórios

Por que assim: `ProjectLabor` é MENSAL e já é consumido por ~17 módulos financeiros. Uma segunda
entidade gerando dinheiro em paralelo duplicaria as regras e criaria duas verdades. Então a
Alocação responde "quem é contratado por qual contrato, com que valor, de quando até quando" e
projeta isso nas linhas mensais; o cálculo do dinheiro continua num lugar só.

O nome do modelo é `EmployeeAssignment` (e não `EmployeeAllocation`) porque este último já existe
no sistema — é o vínculo percentual legado colaborador×projeto, hoje com ZERO linhas. Na interface
esta entidade se chama **Alocação**.

Histórico é regra: nada é apagado. Sair de um contrato = `status=ENCERRADA` + `end_date`. Entrar em
outro = nova Alocação. Assim a trajetória do colaborador é reconstruível.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class AllocationType(str, Enum):
    """Modelo de remuneração da alocação — a intenção do cadastro, explícita.

    INDEPENDENTE: o colaborador tem contratos distintos e cada um paga o SEU valor. Não existe
    percentual (é sempre 100%). É o caso da esmagadora maioria e, por isso, o padrão.

    RATEIO: um único custo do colaborador é DIVIDIDO entre projetos por percentual. É o
    comportamento histórico do sistema, preservado sem nenhuma mudança de cálculo.

    Antes disto os dois casos eram o mesmo campo (`allocation_percentage`), e nada distinguia
    "100% porque é o contrato dele" de "100% porque ninguém rateou". O tipo remove a ambiguidade
    na origem e dá lugar para cada modelo ganhar regra própria sem espalhar `if` pelo sistema.
    """

    INDEPENDENTE = "INDEPENDENTE"
    RATEIO = "RATEIO"


class AssignmentStatus(str, Enum):
    """Os três desfechos possíveis de um vínculo — semanticamente distintos, nunca DELETE.

    ATIVA      → vínculo vigente.
    ENCERRADA  → vínculo que EXISTIU e terminou normalmente. Deixou rastro financeiro; some das
                 projeções futuras, mas continua no histórico e nos meses já fechados.
    CANCELADA  → vínculo criado POR ENGANO e sem nenhum efeito financeiro. É o "excluir" seguro:
                 some da interface por padrão, mas a linha permanece auditável. Só é permitido
                 enquanto a alocação não gerou nada (ver `EmployeeAssignmentService.cancel`).
    """

    ATIVA = "ATIVA"
    ENCERRADA = "ENCERRADA"
    CANCELADA = "CANCELADA"


class EmployeeAssignment(TimestampUUIDMixin, Base):
    __tablename__ = "employee_assignments"

    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Opcional: uma alocação pode existir só no Centro de Custo (administrativo, sem contrato).
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Centro de Custo como TEXTO, seguindo o vocabulário único do sistema (CostCenterService) —
    # o mesmo padrão de `employees.cost_center`. Não é FK de propósito.
    cost_center: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    allocation_type: Mapped[AllocationType] = mapped_column(
        SAEnum(AllocationType, name="employee_allocation_type"),
        nullable=False,
        default=AllocationType.INDEPENDENTE,
        server_default=AllocationType.INDEPENDENTE.value,
        index=True,
    )

    # --- Remuneração própria (só faz sentido em INDEPENDENTE) --------------------------------
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary_base: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    allowance: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)  # ajuda de custo
    hours_per_month: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # NULL = herda o tipo de pagamento do cadastro do colaborador (CLT/PJ). Preparado para o caso
    # futuro de contratos com naturezas diferentes; hoje ninguém precisa preencher.
    employment_type: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # --- Participação em rateio (só faz sentido em RATEIO) -----------------------------------
    # Em INDEPENDENTE fica sempre 100: o cálculo de ProjectLabor multiplica por (pct/100), então
    # 100 é o elemento neutro e a matemática existente continua idêntica.
    allocation_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=100, server_default="100"
    )

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        SAEnum(AssignmentStatus, name="employee_assignment_status"),
        nullable=False,
        default=AssignmentStatus.ATIVA,
        server_default=AssignmentStatus.ATIVA.value,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cancelamento (engano). O MOTIVO fica na auditoria, junto com o diff — aqui ficam só os
    # carimbos que tornam o estado auto-explicativo em qualquer consulta ao banco.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Marca as alocações criadas pelo backfill da migration (não vieram de cadastro manual).
    # Útil para auditoria e para não confundir "o sistema deduziu" com "alguém cadastrou".
    is_backfilled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    employee: Mapped["Employee"] = relationship(back_populates="assignments")  # noqa: F821
    # `selectin`: o projeto vem junto na mesma carga. Sem isto, ler `row.project.name` no router
    # dispara lazy load FORA do contexto async → MissingGreenlet → 500. E um 500 não passa pelo
    # middleware de CORS, então o browser mostra apenas "Network Error".
    project: Mapped["Project | None"] = relationship("Project", lazy="selectin")  # noqa: F821

    @property
    def effective_percent(self) -> float:
        """Percentual que vale no cálculo: rateio usa o informado; independente é sempre 100."""
        if self.allocation_type == AllocationType.RATEIO:
            return float(self.allocation_percent or 0)
        return 100.0

    def is_open_on(self, day: date) -> bool:
        """Alocação vigente na data (ATIVA e dentro do período).

        ENCERRADA e CANCELADA nunca são vigentes — logo nenhuma delas participa de projeção.
        """
        if self.status != AssignmentStatus.ATIVA:
            return False
        if self.start_date and day < self.start_date:
            return False
        if self.end_date and day > self.end_date:
            return False
        return True
