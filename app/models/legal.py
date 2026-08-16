"""Workspace Jurídico — entidades base (Fase 1).

Modelagem deliberada: a entidade PRINCIPAL é o **Processo** (`LegalCase`). O ex-colaborador
(`LegalPerson`) é apenas uma pessoa VINCULADA ao processo, não o seu dono. Por isso `person_id` é
opcional: um processo cível/tributário da empresa, ou um trabalhista cujo reclamante ainda não foi
identificado, existe sem pessoa vinculada.

    LegalPerson  0..1 ──< LegalCase  (uma pessoa pode ter N processos)

Preparado para evoluir sem remodelagem: o processo é a âncora de UUID para as tabelas futuras
(movimentações, pagamentos, acordos, parcelamentos, timeline), que entram como `case_id` — tudo
aditivo. `case_type` já distingue trabalhista/cível/tributário, e os agregados por pessoa
(quantidade, valores) são DERIVADOS dos processos no serviço, nunca desnormalizados aqui — assim
não há campo para dessincronizar quando os processos mudarem.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampUUIDMixin


class LegalCaseStatus(str, Enum):
    """Status jurídico do processo (fonte: coluna "Status do Processo (Jurídico)" da planilha)."""

    EM_ANDAMENTO = "EM_ANDAMENTO"
    COM_DECISAO = "COM_DECISAO"
    SUSPENSO = "SUSPENSO"
    ACORDO = "ACORDO"
    ACORDO_FINALIZADO = "ACORDO_FINALIZADO"
    ENCERRADO = "ENCERRADO"
    SEM_PROCESSO = "SEM_PROCESSO"


class LegalCaseType(str, Enum):
    """Natureza do contencioso. Fase 1 carrega trabalhista/cível; os demais já são suportados."""

    TRABALHISTA = "TRABALHISTA"
    CIVEL = "CIVEL"
    TRIBUTARIO = "TRIBUTARIO"
    OUTRO = "OUTRO"


class LegalEntityType(str, Enum):
    """Entidade referenciada por um registro de histórico (`LegalChangeLog`)."""

    PERSON = "PERSON"
    CASE = "CASE"
    COMPANY = "COMPANY"
    PROJECT = "PROJECT"


class LegalChangeAction(str, Enum):
    """O que aconteceu com a entidade. Não existe DELETE: registros são DESATIVADOS."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DEACTIVATE = "DEACTIVATE"
    RESTORE = "RESTORE"


class LegalPerson(TimestampUUIDMixin, Base):
    """Ex-colaborador — pessoa que pode estar vinculada a um ou mais processos.

    Cadastro PRÓPRIO do módulo Jurídico, independente de `employees`: a maioria destas pessoas já
    não é colaboradora e nunca esteve no cadastro operacional. Um vínculo opcional com `employees`
    pode ser adicionado depois sem alterar esta tabela.
    """

    __tablename__ = "legal_persons"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cpf: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)

    company: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    client: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)

    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Valores da RESCISÃO (relação de emprego), distintos dos valores do processo.
    severance_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    fgts_balance: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    cases: Mapped[list["LegalCase"]] = relationship(
        back_populates="person",
        order_by="LegalCase.case_number",
        lazy="selectin",
    )


class LegalCase(TimestampUUIDMixin, Base):
    """Processo — entidade principal do módulo."""

    __tablename__ = "legal_cases"

    case_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    jusbrasil_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("legal_persons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[LegalCaseStatus] = mapped_column(
        SAEnum(LegalCaseStatus, name="legal_case_status"),
        nullable=False,
        default=LegalCaseStatus.EM_ANDAMENTO,
        server_default=LegalCaseStatus.EM_ANDAMENTO.value,
        index=True,
    )
    case_type: Mapped[LegalCaseType] = mapped_column(
        SAEnum(LegalCaseType, name="legal_case_type"),
        nullable=False,
        default=LegalCaseType.TRABALHISTA,
        server_default=LegalCaseType.TRABALHISTA.value,
        index=True,
    )
    # Classe processual informada pelo tribunal (ex.: "EXECUÇÃO FISCAL"). Texto livre — é um rótulo
    # da fonte, mais granular que `case_type` e sem valor de domínio fechado.
    nature: Mapped[str | None] = mapped_column(String(120), nullable=True)

    uf: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    court: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)

    company: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    client: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    claimant_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    defendant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # `amount_considered` é o valor da causa SEM duplicidade: quando dois processos repetem o mesmo
    # valor (mesma origem contabilizada duas vezes), o duplicado entra como 0 para não inflar o
    # passivo. É a base padrão dos indicadores — mesma semântica do Painel de Passivo.
    amount_claimed: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_considered: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_agreed: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_paid: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_pending: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Plano de pagamento do acordo em texto livre ("3 X 2.333,34"), como registrado pelo jurídico.
    # `amount_agreed` é o total já somado. Vira tabela de parcelas numa fase futura.
    agreement_terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_movement: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_movement_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    hearing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    distribution_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fase 2: baixa LÓGICA. Não há DELETE físico de processo — um registro importado errado é
    # desativado e some das telas analíticas e dos indicadores, mas o histórico é preservado.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    person: Mapped["LegalPerson | None"] = relationship(back_populates="cases", lazy="joined")


class LegalCompany(TimestampUUIDMixin, Base):
    """Empresa do grupo M&E (parte reclamada).

    VOCABULÁRIO, não chave estrangeira: `legal_cases.company` continua sendo texto. Este cadastro
    alimenta os combos e os filtros (mesmo padrão de Centro de Custo), então registrar uma empresa
    nova não exige migrar dados nem remodelar o processo — e um valor que já existe nos processos
    nunca desaparece dos filtros, mesmo sem estar cadastrado aqui.
    """

    __tablename__ = "legal_companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(24), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class LegalProject(TimestampUUIDMixin, Base):
    """Projeto/contrato e o cliente correspondente. Mesmo papel de vocabulário de `LegalCompany`."""

    __tablename__ = "legal_projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    client: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class LegalImportRun(TimestampUUIDMixin, Base):
    """Trilha de auditoria das importações da planilha — uma linha por carga CONFIRMADA.

    Registra o QUE aconteceu, não o conteúdo: quem executou, quais arquivos, quantas linhas foram
    lidas e o saldo (criados/atualizados/ignorados/erros). A pré-visualização não gera registro —
    ela não altera nada.

    Sem valores monetários de propósito: o histórico é legível por quem administra o módulo sem
    depender de Dados sensíveis. Gravado na MESMA transação da carga, então "importação sem
    registro" é um estado impossível.
    """

    __tablename__ = "legal_import_runs"

    spreadsheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # NULL = importação só com a planilha (o padrão depois da carga inicial).
    panel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    rows_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    people_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    people_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cases_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cases_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ignored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # E-mail redundante ao FK de propósito: a trilha sobrevive à exclusão do usuário.
    executed_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    executed_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class LegalChangeLog(TimestampUUIDMixin, Base):
    """Histórico append-only de alterações MANUAIS no módulo Jurídico.

    Um registro por CAMPO alterado (não um blob por requisição): assim "quais processos mudaram de
    status em agosto" é uma consulta simples, sem varrer JSON. A carga inicial (seed) não gera
    histórico — só o que passa pelas telas de Administração.

    `entity_id` é intencionalmente SEM chave estrangeira: o histórico sobrevive à entidade e serve
    às quatro tabelas do módulo (discriminadas por `entity_type`).
    """

    __tablename__ = "legal_change_logs"

    entity_type: Mapped[LegalEntityType] = mapped_column(
        SAEnum(LegalEntityType, name="legal_entity_type"), nullable=False, index=True
    )
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[LegalChangeAction] = mapped_column(
        SAEnum(LegalChangeAction, name="legal_change_action"), nullable=False, index=True
    )

    # NULL em CREATE/DEACTIVATE/RESTORE (a ação já descreve o evento); preenchidos em UPDATE.
    field: Mapped[str | None] = mapped_column(String(64), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    changed_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
