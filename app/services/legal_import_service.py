"""Importação da planilha do Jurídico — pré-visualização e aplicação.

Serviço ÚNICO de carga do módulo: a tela de Administração → Importações, o seed de
desenvolvimento (`python manage.py seed_legal`) e qualquer script chamam este mesmo código. A
transformação das fontes fica em `legal_import_parser`; aqui trata-se só de comparar com o
banco e persistir.

## As quatro regras que definem o comportamento

1. **A planilha inclui e atualiza — nunca exclui.** Registro que sumiu do arquivo permanece no
   sistema; a exclusão (baixa lógica) continua sendo uma decisão manual do Workspace. Pelo mesmo
   motivo `is_active` NÃO é tocado numa atualização: reimportar não ressuscita o que o
   administrador desativou de propósito.
2. **Campo vazio não apaga campo preenchido.** Na atualização, só valores presentes na fonte são
   gravados — o que preserva também o que foi ajustado na tela em colunas que a planilha não
   preenche.
3. **O Painel de Passivo é fonte HISTÓRICA, não dependência.** Depois da carga inicial, os campos
   que só ele enriquece (`PANEL_ENRICHED_FIELDS`) pertencem ao BANCO: numa importação sem painel
   eles não são reescritos de forma alguma. Não é só "vazio não apaga" — é "a planilha não
   empobrece o banco", inclusive quando ela tem um substituto pior (o caso de `defendant_name`).
   Numa CRIAÇÃO não há o que preservar, então o que a planilha oferecer é aproveitado.
4. **Idempotência por chave natural:** CPF (ou nome, quando não há CPF) para a pessoa e número do
   processo para o processo. Reimportar o mesmo arquivo não cria nada e não altera nada.

`preview()` e `apply()` compartilham `_resolve()`: o que o usuário confere antes de confirmar é
exatamente o que será executado.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import (
    LegalCase,
    LegalCaseStatus,
    LegalCaseType,
    LegalImportRun,
    LegalPerson,
)
from app.models.user import User
from app.schemas.legal_import import (
    LegalImportEntry,
    LegalImportIssue,
    LegalImportReport,
    LegalImportSummary,
)
from app.services.audit_service import AuditService
from app.services.legal_import_parser import (
    PANEL_ENRICHED_FIELDS,
    ParsedSources,
    SourceIssue,
    is_group_company,
    norm_name,
)

logger = logging.getLogger(__name__)

# Tamanho máximo de cada lista do relatório. Os CONTADORES nunca são cortados — só o detalhamento,
# para que uma planilha muito grande não gere uma resposta impraticável na tela.
LIST_LIMIT = 500

PERSON_FIELDS: tuple[str, ...] = (
    "full_name",
    "cpf",
    "company",
    "project",
    "client",
    "role",
    "admission_date",
    "termination_date",
    "severance_amount",
    "fgts_balance",
    "notes",
)

CASE_FIELDS: tuple[str, ...] = (
    "case_number",
    "jusbrasil_url",
    "nature",
    "uf",
    "court",
    "city",
    "company",
    "project",
    "client",
    "claimant_name",
    "defendant_name",
    "amount_claimed",
    "amount_considered",
    "amount_agreed",
    "amount_paid",
    "amount_pending",
    "agreement_terms",
    "last_movement",
    "last_movement_date",
    "hearing_date",
    "distribution_date",
    "notes",
)

DATE_FIELDS = frozenset(
    {
        "admission_date",
        "termination_date",
        "last_movement_date",
        "hearing_date",
        "distribution_date",
    }
)

MONEY_FIELDS = frozenset(
    {
        "severance_amount",
        "fgts_balance",
        "amount_claimed",
        "amount_considered",
        "amount_agreed",
        "amount_paid",
        "amount_pending",
    }
)

# Rótulos pt-BR exibidos no relatório (o relatório mostra QUAL campo mudou, nunca o valor).
FIELD_LABELS: dict[str, str] = {
    "full_name": "Nome",
    "cpf": "CPF",
    "company": "Empresa",
    "project": "Contrato/Projeto",
    "client": "Cliente",
    "role": "Cargo",
    "admission_date": "Admissão",
    "termination_date": "Desligamento",
    "severance_amount": "Rescisão",
    "fgts_balance": "Saldo FGTS",
    "notes": "Observações",
    "case_number": "Número do processo",
    "jusbrasil_url": "Link JusBrasil",
    "nature": "Natureza",
    "uf": "UF",
    "court": "Foro",
    "city": "Cidade",
    "claimant_name": "Reclamante",
    "defendant_name": "Reclamado",
    "amount_claimed": "Valor da causa",
    "amount_considered": "Valor considerado",
    "amount_agreed": "Valor do acordo",
    "amount_paid": "Valor pago",
    "amount_pending": "Valor em aberto",
    "agreement_terms": "Condições do acordo",
    "last_movement": "Última movimentação",
    "last_movement_date": "Data da movimentação",
    "hearing_date": "Audiência",
    "distribution_date": "Distribuição",
    "status": "Status",
    "case_type": "Tipo",
    "person": "Desligado vinculado",
}


def _label(field_name: str) -> str:
    return FIELD_LABELS.get(field_name, field_name)


def _coerce(field_name: str, value: Any) -> Any:
    """Converte o valor da fonte (JSON) para o tipo da coluna."""
    if value is None:
        return None
    if field_name in DATE_FIELDS and isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


def _comparable(field_name: str, value: Any) -> Any:
    """Forma canônica para comparar fonte × banco (Decimal × float, date × str)."""
    if value is None:
        return None
    if field_name in MONEY_FIELDS:
        return round(float(value), 2)
    if field_name in DATE_FIELDS:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return value
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        return value.strip()
    return value


@dataclass
class _Change:
    """Uma escrita pendente: o objeto alvo e os campos a gravar."""

    target: Any
    values: dict[str, Any]
    created: bool
    label: str
    detail: str | None = None
    changed: list[str] = field(default_factory=list)


@dataclass
class _Resolution:
    people: list[_Change] = field(default_factory=list)
    cases: list[_Change] = field(default_factory=list)
    people_unchanged: int = 0
    cases_unchanged: int = 0
    conflicts: list[SourceIssue] = field(default_factory=list)
    # payload key da pessoa → objeto (novo ou existente), para vincular os processos.
    person_by_key: dict[str, LegalPerson] = field(default_factory=dict)


class LegalImportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.audit = AuditService(session)

    # -- API ------------------------------------------------------------------------------

    async def preview(self, parsed: ParsedSources) -> LegalImportReport:
        """Calcula o que a importação faria. NÃO escreve — a sessão é descartada pelo router."""
        resolution = await self._resolve(parsed)
        return self._report(parsed, resolution, applied=False)

    async def apply(
        self,
        parsed: ParsedSources,
        *,
        actor: User | None = None,
        request: Request | None = None,
    ) -> LegalImportReport:
        """Executa a importação e devolve o relatório do que foi feito."""
        started = time.perf_counter()
        resolution = await self._resolve(parsed)

        for change in resolution.people:
            self._write(change)
        # Materializa os IDs das pessoas antes de vincular os processos.
        await self.session.flush()
        for change in resolution.cases:
            self._write(change)

        report = self._report(parsed, resolution, applied=True)
        # O registro do histórico vai na MESMA transação da carga: uma importação que aconteceu
        # sem deixar linha na trilha seria um estado impossível de auditar depois.
        self.session.add(
            _run_row(report, actor=actor, elapsed_ms=parsed.elapsed_ms + _ms_since(started))
        )
        # A CARGA é confirmada antes da auditoria, de propósito. `log_action` engole a própria
        # exceção, mas um INSERT que falha deixa a sessão em estado de rollback pendente — se o
        # registro do evento viesse na mesma transação, um problema no log derrubaria uma
        # importação inteira já concluída. O evento é rastro; o dado é o produto.
        await self.session.commit()

        try:
            await self.audit.log_action(
                user=actor,
                action="import",
                entity="legal_import",
                entity_id=uuid4(),
                before=None,
                after=None,
                force_log=True,
                request=request,
                context={
                    "planilha": report.spreadsheet,
                    "painel": report.panel,
                    **report.summary.model_dump(),
                },
            )
            await self.session.commit()
        except Exception:  # pragma: no cover - o dado já está salvo; só o rastro se perde
            logger.exception("Auditoria da importação falhou (a carga foi concluída).")
            await self.session.rollback()

        return report

    # -- Núcleo ---------------------------------------------------------------------------

    async def _resolve(self, parsed: ParsedSources) -> _Resolution:
        payload = parsed.payload
        resolution = _Resolution()

        existing_people = (await self.session.execute(select(LegalPerson))).scalars().all()
        by_cpf = {p.cpf: p for p in existing_people if p.cpf}
        by_name: dict[str, list[LegalPerson]] = {}
        for person in existing_people:
            by_name.setdefault(norm_name(person.full_name), []).append(person)

        claimed: set[int] = set()  # id() das linhas já casadas nesta importação

        for entry in payload.get("people", []):
            cpf = entry.get("cpf")
            name_key = norm_name(entry.get("full_name"))
            row = by_cpf.get(cpf) if cpf else None
            if row is None:
                # Sem CPF (ou CPF novo): casa pelo nome. Só quando NÃO é ambíguo — dois homônimos
                # no banco viram um conflito relatado, nunca uma atualização no registro errado.
                candidates = [p for p in by_name.get(name_key, []) if id(p) not in claimed]
                if cpf:
                    candidates = [p for p in candidates if not p.cpf]
                if len(candidates) == 1:
                    row = candidates[0]
                elif len(candidates) > 1:
                    resolution.conflicts.append(
                        SourceIssue(
                            level="WARNING",
                            identifier=entry.get("full_name"),
                            message=(
                                "Existem vários cadastros com este nome e a planilha não traz CPF "
                                "para desempatar — nenhum foi alterado."
                            ),
                        )
                    )
                    resolution.people_unchanged += 1
                    continue

            values = {f: _coerce(f, entry.get(f)) for f in PERSON_FIELDS}
            if row is None:
                new_person = LegalPerson()
                resolution.person_by_key[entry["key"]] = new_person
                resolution.people.append(
                    _Change(
                        target=new_person,
                        values={**values, "is_active": True},
                        created=True,
                        label=str(entry.get("full_name") or "(sem nome)"),
                        detail=entry.get("cpf"),
                    )
                )
                continue

            claimed.add(id(row))
            resolution.person_by_key[entry["key"]] = row
            changed = self._diff(row, values)
            if not changed:
                resolution.people_unchanged += 1
                continue
            resolution.people.append(
                _Change(
                    target=row,
                    values={f: values[f] for f in changed},
                    created=False,
                    label=row.full_name,
                    detail=row.cpf,
                    changed=[_label(f) for f in changed],
                )
            )

        # --- processos: chave natural = número do processo ---------------------------------
        existing_cases = (await self.session.execute(select(LegalCase))).scalars().all()
        by_number = {c.case_number: c for c in existing_cases}

        for entry in payload.get("cases", []):
            number = entry["case_number"]
            row = by_number.get(number)
            values = {f: _coerce(f, entry.get(f)) for f in CASE_FIELDS}
            if entry.get("case_type"):
                values["case_type"] = LegalCaseType(entry["case_type"])
            person = (
                resolution.person_by_key.get(entry["person_key"]) if entry.get("person_key") else None
            )

            if row is None:
                # Status ausente na fonte só assume o padrão na CRIAÇÃO.
                values["status"] = (
                    LegalCaseStatus(entry["status"])
                    if entry.get("status")
                    else LegalCaseStatus.EM_ANDAMENTO
                )
                values["is_active"] = True
                if person is not None:
                    values["person"] = person
                resolution.cases.append(
                    _Change(
                        target=LegalCase(),
                        values=values,
                        created=True,
                        label=number,
                        detail=entry.get("claimant_name"),
                    )
                )
                continue

            if entry.get("status"):
                values["status"] = LegalCaseStatus(entry["status"])
            # Sem o painel, o que ele enriqueceu na carga inicial fica intocado: o banco é a
            # fonte oficial desses campos daqui em diante.
            if not parsed.panel_present:
                for field_name in PANEL_ENRICHED_FIELDS:
                    values.pop(field_name, None)
                # `company` é coluna da planilha e continua atualizável — MENOS quando isso
                # trocaria a entidade do grupo M&E (que só o painel identifica, em 2 processos)
                # pela concessionária tomadora do serviço, empobrecendo o filtro "Empresa".
                if is_group_company(row.company) and not is_group_company(values.get("company")):
                    values.pop("company", None)
            changed = self._diff(row, values)
            # Vínculo com o desligado: liga quando a fonte identifica a pessoa; NUNCA desvincula.
            if person is not None and row.person_id != getattr(person, "id", None):
                changed.append("person")
                values["person"] = person
            if not changed:
                resolution.cases_unchanged += 1
                continue
            resolution.cases.append(
                _Change(
                    target=row,
                    values={f: values[f] for f in changed},
                    created=False,
                    label=number,
                    detail=row.claimant_name,
                    changed=[_label(f) for f in changed],
                )
            )

        return resolution

    def _diff(self, row: Any, values: dict[str, Any]) -> list[str]:
        """Campos que realmente mudam. Valor ausente na fonte (None) nunca apaga o que existe."""
        changed: list[str] = []
        for field_name, incoming in values.items():
            if incoming is None:
                continue
            current = getattr(row, field_name, None)
            if _comparable(field_name, current) != _comparable(field_name, incoming):
                changed.append(field_name)
        return changed

    def _write(self, change: _Change) -> None:
        for field_name, value in change.values.items():
            setattr(change.target, field_name, value)
        if change.created:
            self.session.add(change.target)

    # -- Relatório ------------------------------------------------------------------------

    def _report(
        self, parsed: ParsedSources, resolution: _Resolution, *, applied: bool
    ) -> LegalImportReport:
        source = parsed.payload.get("source", {})
        new_people = [c for c in resolution.people if c.created]
        upd_people = [c for c in resolution.people if not c.created]
        new_cases = [c for c in resolution.cases if c.created]
        upd_cases = [c for c in resolution.cases if not c.created]

        duplicates = parsed.duplicates + resolution.conflicts
        errors = [i for i in parsed.issues if i.level == "ERROR"]
        warnings = [i for i in parsed.issues if i.level == "WARNING"]
        ignored = parsed.skipped

        summary = LegalImportSummary(
            rows_read=parsed.rows_read,
            people_new=len(new_people),
            people_updated=len(upd_people),
            people_unchanged=resolution.people_unchanged,
            cases_new=len(new_cases),
            cases_updated=len(upd_cases),
            cases_unchanged=resolution.cases_unchanged,
            duplicates=len(duplicates),
            errors=len(errors),
            warnings=len(warnings),
            # "Ignorados" = LINHAS lidas e não carregadas. Registros sem alteração são contados
            # em `*_unchanged` — misturar os dois números confundiria a conferência.
            ignored=len(ignored),
            panel_rows=parsed.panel_rows,
            panel_matched=parsed.panel_matched,
        )

        lists = (new_people, upd_people, new_cases, upd_cases, duplicates, errors + warnings, ignored)
        return LegalImportReport(
            applied=applied,
            spreadsheet=source.get("spreadsheet") or "",
            sheet=source.get("sheet") or "",
            panel=source.get("panel"),
            summary=summary,
            new_people=_entries(new_people),
            updated_people=_entries(upd_people),
            new_cases=_entries(new_cases),
            updated_cases=_entries(upd_cases),
            duplicates=_issues(duplicates),
            issues=_issues(errors + warnings),
            ignored=_issues(ignored),
            truncated=any(len(items) > LIST_LIMIT for items in lists),
        )


def _ms_since(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _run_row(report: LegalImportReport, *, actor: User | None, elapsed_ms: int) -> LegalImportRun:
    """Traduz o relatório na linha do histórico. Só contadores — nenhum valor de registro."""
    s = report.summary
    return LegalImportRun(
        spreadsheet_name=report.spreadsheet,
        panel_name=report.panel,
        rows_read=s.rows_read,
        people_new=s.people_new,
        people_updated=s.people_updated,
        cases_new=s.cases_new,
        cases_updated=s.cases_updated,
        unchanged=s.people_unchanged + s.cases_unchanged,
        ignored=s.ignored,
        duplicates=s.duplicates,
        errors=s.errors,
        warnings=s.warnings,
        duration_ms=elapsed_ms,
        executed_by_id=getattr(actor, "id", None),
        executed_by_email=getattr(actor, "email", None),
    )


def _entries(changes: list[_Change]) -> list[LegalImportEntry]:
    return [
        LegalImportEntry(label=c.label, detail=c.detail, changes=c.changed)
        for c in changes[:LIST_LIMIT]
    ]


def _issues(issues: list[SourceIssue]) -> list[LegalImportIssue]:
    return [
        LegalImportIssue(level=i.level, message=i.message, row=i.row, identifier=i.identifier)
        for i in issues[:LIST_LIMIT]
    ]


__all__ = ["LegalImportService", "LIST_LIMIT"]
