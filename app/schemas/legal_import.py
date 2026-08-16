"""Schemas da importação da planilha do Jurídico.

A pré-visualização e o relatório final usam o MESMO schema (`LegalImportReport`), distinguidos
apenas por `applied`: o que o usuário confere antes de confirmar é literalmente o que a
importação vai fazer, calculado pelo mesmo código.

Nenhum VALOR monetário trafega aqui — as alterações são descritas por NOME de campo
("Valor considerado"), nunca pelo conteúdo. Assim o relatório não precisa de redação por
Dados sensíveis e não vaza número para quem não tem `legal_cases.sensitive`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

IssueLevel = Literal["ERROR", "WARNING"]


class LegalImportIssue(BaseModel):
    """Ocorrência da leitura do arquivo. `ERROR` descarta a linha; `WARNING` só informa."""

    level: IssueLevel
    message: str
    # Linha da planilha como o usuário a vê no Excel (cabeçalho = 1).
    row: int | None = None
    # Nome da pessoa ou número do processo, para o usuário localizar o registro.
    identifier: str | None = None


class LegalImportEntry(BaseModel):
    """Um registro que será criado ou atualizado."""

    label: str
    detail: str | None = None
    # Rótulos pt-BR dos campos que mudam (vazio em criação).
    changes: list[str] = Field(default_factory=list)


class LegalImportSummary(BaseModel):
    rows_read: int = 0
    people_new: int = 0
    people_updated: int = 0
    people_unchanged: int = 0
    cases_new: int = 0
    cases_updated: int = 0
    cases_unchanged: int = 0
    duplicates: int = 0
    errors: int = 0
    warnings: int = 0
    ignored: int = 0
    # Entradas do Painel de Passivo lidas e efetivamente vinculadas a um processo.
    panel_rows: int = 0
    panel_matched: int = 0


class LegalImportReport(BaseModel):
    """Pré-visualização (`applied=False`) ou relatório da importação concluída (`applied=True`)."""

    applied: bool = False
    spreadsheet: str
    sheet: str
    panel: str | None = None
    summary: LegalImportSummary
    new_people: list[LegalImportEntry] = Field(default_factory=list)
    updated_people: list[LegalImportEntry] = Field(default_factory=list)
    new_cases: list[LegalImportEntry] = Field(default_factory=list)
    updated_cases: list[LegalImportEntry] = Field(default_factory=list)
    duplicates: list[LegalImportIssue] = Field(default_factory=list)
    issues: list[LegalImportIssue] = Field(default_factory=list)
    ignored: list[LegalImportIssue] = Field(default_factory=list)
    # True quando alguma lista foi cortada por tamanho (os CONTADORES seguem completos).
    truncated: bool = False


class LegalImportRunRead(ORMModel):
    """Uma linha do histórico de importações (trilha de auditoria)."""

    id: UUID
    created_at: datetime
    spreadsheet_name: str
    panel_name: str | None = None
    rows_read: int
    people_new: int
    people_updated: int
    cases_new: int
    cases_updated: int
    unchanged: int
    ignored: int
    duplicates: int
    errors: int
    warnings: int
    duration_ms: int
    executed_by_email: str | None = None


__all__ = [
    "LegalImportEntry",
    "LegalImportIssue",
    "LegalImportReport",
    "LegalImportRunRead",
    "LegalImportSummary",
]
