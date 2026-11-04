"""Jurídico × Endividamento: o "Valor pago" dos acordos vem da dívida que os paga.

O acordo de um processo (ou o acordo de rescisão de um desligado sem processo) é pago como uma
dívida do Endividamento, cujas parcelas viram títulos no Contas a Pagar. Este serviço liga as duas
pontas SEM casar título por nome:

- o vínculo é explícito, gravado na dívida: `legal_case_id` (o processo) e `legal_person_id` (o
  desligado). O nome só serve para SUGERIR o vínculo — quem confirma é o usuário;
- pago, saldo e "quitado" saem da leitura OFICIAL do Endividamento (`debt_reads`), a mesma da tela
  dele. Nenhuma conta é refeita aqui, então os dois módulos nunca divergem;
- o processo vinculado recebe o pago/saldo em `amount_paid`/`amount_pending` com
  `paid_source = 'ENDIVIDAMENTO'`. Gravar no processo (em vez de só sobrepor na resposta) mantém
  indicadores, ficha do desligado e relatório funcionando sem saber que o valor é derivado.
  `sync_cases` roda a cada leitura do Jurídico e só escreve o que mudou — o valor nunca envelhece,
  seja qual for o caminho por onde o pagamento entrou (CAP, grade, estorno, cronograma).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_finance import CompanyFinancialItem
from app.models.legal import (
    LegalCase,
    LegalCaseStatus,
    LegalChangeAction,
    LegalChangeLog,
    LegalDebtLinkDismissal,
    LegalEntityType,
    LegalPerson,
)

PAID_SOURCE_DEBT = "ENDIVIDAMENTO"

STATUS_SETTLED = "QUITADO"
STATUS_PAYING = "EM_PAGAMENTO"

# Palavras que aparecem no NOME da dívida mas não identificam a pessoa.
_NAME_STOPWORDS = frozenset(
    {
        "DE", "DA", "DO", "DAS", "DOS", "E",
        "ACORDO", "RESCISAO", "RESCISORIO", "TRABALHISTA", "PROCESSO", "DIVIDA", "PARCELA",
        "PARCELAS", "ACERTO", "MUTUOS", "REEMBOLSO", "LTDA", "SA", "ME", "EPP",
    }
)


def name_tokens(value: str | None) -> list[str]:
    """Tokens de nome comparáveis: sem acento, maiúsculos, sem preposição nem rótulo de dívida."""
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    return [t for t in re.split(r"[^A-Z]+", plain) if len(t) > 1 and t not in _NAME_STOPWORDS]


def name_match(debt_name: str | None, person_name: str | None) -> str | None:
    """Confiança de que a dívida é da pessoa: 'ALTA', 'MEDIA' ou None.

    Exige o MESMO primeiro nome e mais um nome em comum — só o primeiro nome junta homônimos
    ("Paulo Sérgio" × "Paulo Afonso"). ALTA quando todo nome da dívida está no da pessoa
    ("CAROLINA DE ABREU - ACORDO RESCISÃO" × "Carolina de Abreu Rodrigues"); MEDIA quando a
    dívida tem um nome que a pessoa não tem ("Pedro Rodrigues Montalvão" × "Pedro dos Santos
    Rodrigues") — pode ser outra pessoa, por isso é só sugestão.
    """
    debt = name_tokens(debt_name)
    person = name_tokens(person_name)
    if len(debt) < 2 or not person or debt[0] != person[0]:
        return None
    others = set(debt[1:]) & set(person[1:])
    if not others:
        return None
    return "ALTA" if set(debt) <= set(person) else "MEDIA"


# "3 X 2.333,34", "2X 1.700,00", "4 PARCELAS DE 8.500,00", "1 X 3250,00" (valor sem milhar).
_INSTALLMENT_RE = re.compile(
    r"(\d{1,3})\s*(?:X|PARCELAS?\s+DE)\s*(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+)",
    re.IGNORECASE,
)
_DUE_DAY_RE = re.compile(r"\bDIA\s+(\d{1,2})\b", re.IGNORECASE)


@dataclass
class AgreementInstallments:
    """Plano de pagamento lido das "Condições do acordo" (texto livre do Jurídico)."""

    groups: list[tuple[int, float]]  # (quantidade, valor da parcela), na ordem do texto
    due_day: int | None  # "vencimento todo dia 30"; None = o dia do início

    @property
    def count(self) -> int:
        return sum(n for n, _ in self.groups)

    @property
    def total(self) -> float:
        return round(sum(n * v for n, v in self.groups), 2)

    def values(self) -> list[float]:
        return [v for n, v in self.groups for _ in range(n)]


def parse_agreement_installments(terms: str | None) -> AgreementInstallments | None:
    """Lê o plano de parcelas do texto do acordo; None quando o texto não descreve parcelas.

    Só SUGERE o cronograma da dívida — quem cria confere (e ajusta no editor de cronograma).
    """
    if not terms:
        return None
    groups: list[tuple[int, float]] = []
    for count, value in _INSTALLMENT_RE.findall(terms):
        n = int(count)
        amount = float(value.replace(".", "").replace(",", "."))
        if n <= 0 or amount <= 0:
            continue
        groups.append((n, round(amount, 2)))
    if not groups:
        return None
    day = _DUE_DAY_RE.search(terms)
    due_day = int(day.group(1)) if day and 1 <= int(day.group(1)) <= 31 else None
    return AgreementInstallments(groups=groups, due_day=due_day)


@dataclass
class DebtPayment:
    """Uma dívida vinculada, como o Endividamento a vê."""

    item_id: UUID
    name: str
    case_id: UUID | None
    person_id: UUID | None
    total: float
    paid: float
    pending: float
    settled: bool
    settled_month: date | None
    is_active: bool


@dataclass
class PaymentSummary:
    """Agregado das dívidas de UM processo ou de UM desligado."""

    debts: list[DebtPayment] = field(default_factory=list)

    @property
    def status(self) -> str | None:
        if not self.debts:
            return None
        return STATUS_SETTLED if all(d.settled for d in self.debts) else STATUS_PAYING

    @property
    def total(self) -> float:
        return round(sum(d.total for d in self.debts), 2)

    @property
    def paid(self) -> float:
        return round(sum(d.paid for d in self.debts), 2)

    @property
    def pending(self) -> float:
        return round(sum(d.pending for d in self.debts), 2)

    @property
    def settled_month(self) -> date | None:
        """Mês em que a ÚLTIMA dívida zerou — só faz sentido quando tudo está quitado."""
        if self.status != STATUS_SETTLED:
            return None
        months = [d.settled_month for d in self.debts if d.settled_month]
        return max(months) if months else None


def _debt_payment(read: dict, item: CompanyFinancialItem) -> DebtPayment:
    """Pago/saldo/quitado na leitura oficial do Endividamento.

    Pago = `total_pago_realizado` quando existe (dívida sem cronograma: sem lançamento futuro),
    senão `total_pago` (cronograma: pago REAL do CAP). Total = `debt_total` (razão: origem + aportes
    + encargos) ou a base da dívida.
    """
    paid = read.get("total_pago_realizado")
    if paid is None:
        paid = read.get("total_pago") or 0.0
    total = read.get("debt_total")
    if total is None:
        total = read.get("debt_base") or 0.0
    return DebtPayment(
        item_id=item.id,
        name=item.nome,
        case_id=item.legal_case_id,
        person_id=item.legal_person_id,
        total=round(float(total), 2),
        paid=round(float(paid), 2),
        pending=round(float(read.get("restante") or 0.0), 2),
        settled=read.get("status") == "quitado",
        settled_month=read.get("quitado_em"),
        is_active=bool(read.get("is_active", True)),
    )


def has_agreement(case: LegalCase) -> bool:
    status = getattr(case.status, "value", case.status)
    return case.amount_agreed is not None or str(status).startswith("ACORDO") or bool(case.agreement_terms)


class LegalDebtLinkError(ValueError):
    pass


class LegalDebtLinkService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # Dívidas lidas pelo último `sync_cases` (o router reaproveita para montar a resposta).
        self.loaded: list[DebtPayment] = []

    # -- leitura ------------------------------------------------------------------------------

    async def _linked_items(self) -> list[CompanyFinancialItem]:
        stmt = select(CompanyFinancialItem).where(
            CompanyFinancialItem.tipo == "endividamento",
            or_(
                CompanyFinancialItem.legal_case_id.isnot(None),
                CompanyFinancialItem.legal_person_id.isnot(None),
            ),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def debt_payments(self) -> list[DebtPayment]:
        from app.services.company_finance_service import CompanyFinanceService

        items = {it.id: it for it in await self._linked_items()}
        reads = await CompanyFinanceService(self.session).debt_reads(list(items))
        return [_debt_payment(r, items[r["id"]]) for r in reads if r["id"] in items]

    @staticmethod
    def by_case(payments: list[DebtPayment]) -> dict[UUID, PaymentSummary]:
        out: dict[UUID, PaymentSummary] = {}
        for p in payments:
            if p.case_id is not None:
                out.setdefault(p.case_id, PaymentSummary()).debts.append(p)
        return out

    @staticmethod
    def by_person(payments: list[DebtPayment]) -> dict[UUID, PaymentSummary]:
        out: dict[UUID, PaymentSummary] = {}
        for p in payments:
            if p.person_id is not None:
                out.setdefault(p.person_id, PaymentSummary()).debts.append(p)
        return out

    async def sync_cases(self) -> list[DebtPayment]:
        """Grava nos processos vinculados o pago/saldo do Endividamento e devolve as dívidas.

        Idempotente e barato quando nada mudou (só compara). Processo que perdeu o vínculo volta
        a ser MANUAL mantendo o último valor — ele era verdadeiro quando foi calculado, e o
        jurídico pode corrigi-lo à mão a partir daí.
        """
        payments = await self.debt_payments()
        summaries = self.by_case(payments)
        condition = LegalCase.paid_source == PAID_SOURCE_DEBT
        if summaries:
            condition = or_(condition, LegalCase.id.in_(list(summaries)))
        stmt = select(LegalCase).where(condition)
        changed = False
        for case in (await self.session.execute(stmt)).scalars().unique().all():
            summary = summaries.get(case.id)
            if summary is None:
                case.paid_source = None
                changed = True
                continue
            paid, pending = summary.paid, summary.pending
            if (
                case.paid_source != PAID_SOURCE_DEBT
                or case.amount_paid is None
                or round(float(case.amount_paid), 2) != paid
                or case.amount_pending is None
                or round(float(case.amount_pending), 2) != pending
            ):
                case.paid_source = PAID_SOURCE_DEBT
                case.amount_paid = paid
                case.amount_pending = pending
                changed = True
        if changed:
            await self.session.commit()
        self.loaded = payments
        return payments

    # -- sugestões -----------------------------------------------------------------------------

    async def suggestions(self) -> list[dict]:
        """Pares dívida × processo/desligado que PARECEM ser o mesmo acordo — nunca aplicados sozinhos.

        - dívida já ligada ao desligado e sem processo → sugere os processos COM ACORDO dele;
        - dívida sem vínculo → casa o nome com os desligados ativos e sugere o processo com acordo
          ou, se ele não tiver, o próprio desligado (acordo de rescisão sem processo).
        Pares descartados não voltam.
        """
        debts = list(
            (
                await self.session.execute(
                    select(CompanyFinancialItem).where(
                        CompanyFinancialItem.tipo == "endividamento",
                        CompanyFinancialItem.legal_case_id.is_(None),
                        CompanyFinancialItem.employee_id.is_(None),
                    )
                )
            ).scalars().all()
        )
        if not debts:
            return []
        persons = list(
            (
                await self.session.execute(select(LegalPerson).where(LegalPerson.is_active.is_(True)))
            ).scalars().unique().all()
        )
        persons_by_id = {p.id: p for p in persons}
        dismissed = {
            (d.item_id, d.case_id, d.person_id)
            for d in (await self.session.execute(select(LegalDebtLinkDismissal))).scalars().all()
        }
        from app.services.company_finance_service import debt_base_amount

        out: list[dict] = []
        for debt in debts:
            if debt.legal_person_id is not None:
                person = persons_by_id.get(debt.legal_person_id)
                candidates = [(person, "VINCULADA")] if person else []
            else:
                candidates = [
                    (p, conf) for p in persons if (conf := name_match(debt.nome, p.full_name))
                ]
            base = debt_base_amount(debt)
            for person, confidence in candidates:
                cases = [c for c in (person.cases or []) if c.is_active and has_agreement(c)]
                targets: list[LegalCase | None] = cases or ([None] if debt.legal_person_id is None else [])
                for case in targets:
                    key = (debt.id, case.id if case else None, person.id)
                    if key in dismissed:
                        continue
                    agreed = float(case.amount_agreed) if case and case.amount_agreed is not None else None
                    out.append(
                        {
                            "item_id": debt.id,
                            "debt_name": debt.nome,
                            "debt_total": round(base, 2),
                            "debt_active": bool(debt.is_active),
                            "person_id": person.id,
                            "person_name": person.full_name,
                            "case_id": case.id if case else None,
                            "case_number": case.case_number if case else None,
                            "case_status": getattr(case.status, "value", case.status) if case else None,
                            "case_agreed": agreed,
                            "confidence": confidence,
                            # Valor da dívida a até 10% do acordo: reforça (não decide) o vínculo.
                            "value_matches": bool(
                                agreed and base and abs(base - agreed) <= 0.10 * agreed
                            ),
                        }
                    )
        rank = {"VINCULADA": 0, "ALTA": 1, "MEDIA": 2}
        out.sort(key=lambda s: (rank.get(s["confidence"], 9), not s["value_matches"], s["person_name"]))
        return out

    # -- vínculo -------------------------------------------------------------------------------

    async def _debt(self, item_id: UUID) -> CompanyFinancialItem:
        item = await self.session.get(CompanyFinancialItem, item_id)
        if item is None or item.tipo != "endividamento":
            raise LookupError("Dívida não encontrada.")
        return item

    def _log(self, *, entity_type: LegalEntityType, entity_id: UUID, actor, old, new) -> None:
        self.session.add(
            LegalChangeLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=LegalChangeAction.UPDATE,
                field="debt_link",
                old_value=old,
                new_value=new,
                changed_by_id=getattr(actor, "id", None),
                changed_by_email=getattr(actor, "email", None),
            )
        )

    async def link(
        self, *, item_id: UUID, case_id: UUID | None, person_id: UUID | None, actor=None
    ) -> None:
        """Liga a dívida ao processo (e ao desligado dele) ou só ao desligado.

        Não renomeia a dívida nem toca em valor nenhum: o vínculo é um ponteiro. O nome do item e
        dos títulos já lançados no CAP continuam os mesmos.
        """
        item = await self._debt(item_id)
        case: LegalCase | None = None
        if case_id is not None:
            case = await self.session.get(LegalCase, case_id)
            if case is None:
                raise LookupError("Processo não encontrado.")
            if person_id is not None and case.person_id not in (None, person_id):
                raise LegalDebtLinkError("O processo é de outro desligado.")
            person_id = case.person_id or person_id
        if person_id is not None and await self.session.get(LegalPerson, person_id) is None:
            raise LookupError("Desligado não encontrado.")
        if case is None and person_id is None:
            raise LegalDebtLinkError("Informe o processo ou o desligado.")
        if person_id is not None and item.employee_id is not None:
            raise LegalDebtLinkError(
                "A dívida está vinculada a um colaborador ativo; troque o tipo no Endividamento antes."
            )
        if case is not None:
            if item.legal_case_id != case.id:
                self._log(
                    entity_type=LegalEntityType.CASE, entity_id=case.id, actor=actor,
                    old=None, new=f"Dívida vinculada: {item.nome}",
                )
            item.legal_case_id = case.id
        if person_id is not None:
            if item.legal_person_id != person_id:
                self._log(
                    entity_type=LegalEntityType.PERSON, entity_id=person_id, actor=actor,
                    old=None, new=f"Dívida vinculada: {item.nome}",
                )
            item.legal_person_id = person_id
        await self.session.commit()
        await self.sync_cases()

    async def unlink(self, *, item_id: UUID, include_person: bool, actor=None) -> None:
        """Desfaz o vínculo com o processo e, se pedido, com o desligado."""
        item = await self._debt(item_id)
        if item.legal_case_id is not None:
            self._log(
                entity_type=LegalEntityType.CASE, entity_id=item.legal_case_id, actor=actor,
                old=f"Dívida vinculada: {item.nome}", new=None,
            )
            item.legal_case_id = None
        if include_person and item.legal_person_id is not None:
            self._log(
                entity_type=LegalEntityType.PERSON, entity_id=item.legal_person_id, actor=actor,
                old=f"Dívida vinculada: {item.nome}", new=None,
            )
            item.legal_person_id = None
        await self.session.commit()
        await self.sync_cases()

    async def dismiss(
        self, *, item_id: UUID, case_id: UUID | None, person_id: UUID | None, actor=None
    ) -> None:
        await self._debt(item_id)
        self.session.add(
            LegalDebtLinkDismissal(
                item_id=item_id, case_id=case_id, person_id=person_id,
                created_by_id=getattr(actor, "id", None),
            )
        )
        await self.session.commit()

    async def finalize_case(self, *, case_id: UUID, actor=None) -> LegalCase:
        """Marca como "Acordo finalizado" o processo cujo acordo o Endividamento já quitou."""
        payments = await self.sync_cases()
        summary = self.by_case(payments).get(case_id)
        if summary is None or summary.status != STATUS_SETTLED:
            raise LegalDebtLinkError("O acordo deste processo ainda não está quitado no Endividamento.")
        from app.services.legal_service import LegalService

        return await LegalService(self.session).update_case(
            case_id, {"status": LegalCaseStatus.ACORDO_FINALIZADO}, actor=actor
        )
