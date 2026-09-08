"""Adaptador entre o Endividamento e o motor de saldo puro (`debt_accrual`).

É a única camada que conhece as duas pontas: lê o cadastro (item, vigências, eventos e a grade
mensal de pagamentos) e entrega ao núcleo puro, que não conhece ORM nem domínio. Mesmo desenho
do Cronograma Financeiro (`financial_schedule` + adaptador), pelo mesmo motivo: a regra
financeira fica testável sem banco.

**De onde vem cada coisa:**

| Entrada do motor | Origem no cadastro |
|---|---|
| principal | `valor_referencia` (a dívida de origem) |
| competência de origem | `start_date`, senão o 1º mês com lançamento, senão o mês do cadastro |
| vigências de taxa | `company_financial_rates` (vazio = dívida congelada) |
| aportes/abatimentos/encargos | `company_financial_events` |
| pagamentos realizados | a SOMA da grade mensal (`company_financial_payments`) por competência |

O pagamento sai da grade mensal — a MESMA fonte que a tela já usa hoje para "Total pago" e
"Pago no mês". Isso é deliberado: o razão passa a explicar os números que o usuário já vê, em
vez de introduzir um segundo total que brigaria com o cabeçalho. E o caminho da grade para o
Contas a Pagar continua exatamente como está: o motor apenas LÊ, nunca escreve no CAP.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.advance_repasse_ledger import (
    AdvanceRepasseLedgerEntry,
    RepasseLedgerDirection,
)
from app.models.company_finance import (
    CompanyFinancialEvent,
    CompanyFinancialItem,
    CompanyFinancialPayment,
    CompanyFinancialRate,
)
from app.services.settings_service import SettingsService
from app.services.debt_accrual import (
    ABATIMENTO,
    plan_installments,
    APORTE,
    ENCARGO_MANUAL,
    EVENT_KINDS,
    LedgerEvent,
    RateChange,
    add_months,
    build_ledger,
    compute_indicators,
    first_of_month,
    months_between,
)

# Horizonte de projeção padrão da tela (quantos meses à frente mostrar em cinza).
DEFAULT_PROJECTION_MONTHS = 6
MAX_PROJECTION_MONTHS = 36
# Teto de segurança: uma dívida com origem muito antiga não pode gerar um razão infinito.
MAX_LEDGER_MONTHS = 600


class DebtLedgerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Leitura                                                            #
    # ------------------------------------------------------------------ #

    async def _load_item(self, item_id: UUID) -> CompanyFinancialItem | None:
        return (
            await self.db.execute(
                select(CompanyFinancialItem)
                .where(CompanyFinancialItem.id == item_id)
                .options(
                    selectinload(CompanyFinancialItem.payments),
                    selectinload(CompanyFinancialItem.rates),
                    selectinload(CompanyFinancialItem.events),
                )
            )
        ).scalars().first()

    @staticmethod
    def origin_month(it: CompanyFinancialItem) -> date:
        """Competência de origem da dívida — a mais antiga evidência de que ela existia.

        `start_date` é a resposta pretendida, mas ela NÃO pode ser a única: a maioria dos
        cadastros antigos está com ela vazia (é anterior ao ciclo de vida), e um lançamento ou
        um aporte em mês anterior ao início registrado simplesmente sumiria do razão — perda
        silenciosa de dado que o usuário digitou. Por isso a origem é o MENOR entre o início
        registrado, o 1º lançamento e o 1º evento; e, quando não há nenhum deles, o mês do
        cadastro. Assim nada do que foi lançado fica fora da evolução.
        """
        candidatas = [first_of_month(it.start_date)] if it.start_date else []
        candidatas += [first_of_month(p.competencia) for p in (it.payments or []) if p.competencia]
        candidatas += [first_of_month(e.competencia) for e in (it.events or []) if e.competencia]
        if candidatas:
            return min(candidatas)
        return first_of_month(it.created_at.date())

    @staticmethod
    def _payments_by_month(it: CompanyFinancialItem) -> dict[date, Decimal]:
        out: dict[date, Decimal] = {}
        for p in it.payments or []:
            comp = first_of_month(p.competencia)
            out[comp] = out.get(comp, Decimal("0")) + Decimal(str(p.valor or 0))
        return out

    async def _repasse_by_month(self, item_id: UUID) -> dict[date, Decimal]:
        """Retiradas do Repasse que abatem ESTA dívida, somadas por competência.

        Segunda fonte de pagamento, ao lado da grade mensal — e a diferença entre as duas é o
        caixa: a grade vira título no Contas a Pagar (a empresa vai desembolsar), a retirada de
        Repasse NÃO (o dinheiro já estava retido na instituição, dentro do repasse das
        antecipações). Lançar título para ela prometeria um desembolso que nunca vai existir.

        Só lançamentos ATIVOS entram: o Ledger é append-only e um estorno (`reversed_at`)
        devolve o valor ao saldo — então a dívida volta a dever, sozinha, na próxima leitura.
        """
        rows = (
            await self.db.execute(
                select(
                    AdvanceRepasseLedgerEntry.occurred_at, AdvanceRepasseLedgerEntry.amount
                ).where(
                    AdvanceRepasseLedgerEntry.debt_item_id == item_id,
                    AdvanceRepasseLedgerEntry.direction == RepasseLedgerDirection.DEBIT,
                    AdvanceRepasseLedgerEntry.reversed_at.is_(None),
                )
            )
        ).all()
        out: dict[date, Decimal] = {}
        for occurred_at, amount in rows:
            comp = first_of_month(occurred_at)
            out[comp] = out.get(comp, Decimal("0")) + Decimal(str(amount))
        return out

    @staticmethod
    def _rates(it: CompanyFinancialItem) -> list[RateChange]:
        return [
            RateChange(valid_from=first_of_month(r.valid_from), monthly_rate=Decimal(str(r.monthly_rate)))
            for r in (it.rates or [])
        ]

    @staticmethod
    def _events(it: CompanyFinancialItem) -> list[LedgerEvent]:
        return [
            LedgerEvent(
                competencia=first_of_month(e.competencia),
                kind=e.kind,
                amount=Decimal(str(e.amount)),
                description=e.description,
            )
            for e in (it.events or [])
        ]

    def _render(
        self,
        *,
        it: CompanyFinancialItem,
        origem: date,
        principal: Decimal,
        vigencias: list[RateChange],
        usando_padrao: bool,
        eventos: list[LedgerEvent],
        pagamentos: dict[date, Decimal],
        repasses: dict[date, Decimal] | None,
        projection_months: int,
        today: date | None,
        taxas_persistidas: list | None,
        eventos_persistidos: list | None,
    ) -> dict:
        """Monta o contrato de leitura do razão. Compartilhado por `ledger` e `preview_ledger`
        para que o que a tela mostra enquanto se digita seja EXATAMENTE o que ela mostra depois
        de salvar — sem uma segunda montagem que pudesse divergir."""
        hoje = first_of_month(today or date.today())
        proj = max(0, min(int(projection_months or 0), MAX_PROJECTION_MONTHS))

        # O razão vai até o mais tarde entre hoje e o último mês com movimento (uma dívida pode
        # ter lançamento futuro já registrado), mais o horizonte de projeção.
        # A ORIGEM entra nos marcos: uma dívida que só começa no futuro tem origem depois de
        # hoje, e sem ela o intervalo sairia invertido (fim < origem) e o razão levantaria erro.
        rep = repasses or {}
        # O motor recebe a SOMA (grade + repasse): para o saldo, pagamento é pagamento. A
        # separação existe só para a tela saber o que é editável e o que veio do Ledger.
        total_por_mes = dict(pagamentos)
        for comp_rep, valor in rep.items():
            total_por_mes[comp_rep] = total_por_mes.get(comp_rep, Decimal("0")) + valor

        marcos = [hoje, origem, *total_por_mes.keys(), *(e.competencia for e in eventos)]
        ultimo_movimento = max(marcos, default=hoje)
        fim = add_months(ultimo_movimento, proj)
        if months_between(origem, fim) + 1 > MAX_LEDGER_MONTHS:
            fim = add_months(origem, MAX_LEDGER_MONTHS - 1)

        linhas = build_ledger(
            principal=principal,
            origin_month=origem,
            through=fim,
            rates=vigencias,
            events=eventos,
            # Soma das duas fontes: grade mensal + retiradas de Repasse. Para o saldo,
            # pagamento é pagamento — a separação existe só para a tela saber o que é editável.
            payments=total_por_mes,
            # REALIZADO vai só até o mês corrente. Um pagamento lançado para um mês futuro é
            # PLANO, não fato — e passa a ser comum agora que o gerador preenche as parcelas à
            # frente. Contá-lo como pago inflaria "Pago" e derrubaria o "Saldo hoje" para o
            # saldo do fim do plano.
            realized_through=hoje,
        )
        ind = compute_indicators(linhas, principal=principal)

        return {
            "item_id": str(it.id),
            "nome": it.nome,
            "origem": origem,
            "tem_correcao": any(r.monthly_rate != 0 for r in vigencias),
            # True quando a taxa exibida é o padrão do SGC, e não uma vigência desta dívida.
            "usando_taxa_padrao": usando_padrao,
            "linhas": [
                {
                    "competencia": ln.competencia,
                    "saldo_inicial": float(ln.saldo_inicial),
                    "aporte": float(ln.aporte),
                    "abatimento": float(ln.abatimento),
                    "encargo_manual": float(ln.encargo_manual),
                    "taxa": float(ln.taxa),
                    "encargo": float(ln.encargo),
                    "pagamento": float(ln.pagamento),
                    # Quanto do pagamento do mês veio do Repasse (não editável na tela).
                    "pagamento_repasse": float(rep.get(ln.competencia, Decimal("0"))),
                    "juros_pagos": float(ln.juros_pagos),
                    "amortizacao": float(ln.amortizacao),
                    "saldo_final": float(ln.saldo_final),
                    "encargo_acumulado": float(ln.encargo_acumulado),
                    "is_projected": ln.is_projected,
                }
                for ln in linhas
            ],
            "resumo": {
                "principal": float(ind.principal),
                "total_aportes": float(ind.total_aportes),
                "total_abatimentos": float(ind.total_abatimentos),
                "total_contratado": float(ind.total_contratado),
                "total_encargos": float(ind.total_encargos),
                "encargos_pagos": float(ind.encargos_pagos),
                "encargos_capitalizados": float(ind.encargos_capitalizados),
                "total_pago": float(ind.total_pago),
                "total_amortizado": float(ind.total_amortizado),
                "saldo_atual": float(ind.saldo_atual),
                "taxa_vigente": float(ind.taxa_vigente),
                "competencia_final": ind.competencia_final,
                "saldo_projetado": (
                    float(ind.saldo_projetado) if ind.saldo_projetado is not None else None
                ),
                "competencia_projecao": ind.competencia_projecao,
            },
            "taxas": [
                {
                    "id": str(r.id),
                    "valid_from": first_of_month(r.valid_from),
                    "monthly_rate": float(r.monthly_rate),
                    "note": r.note,
                }
                for r in sorted(taxas_persistidas or [], key=lambda r: r.valid_from)
            ],
            "eventos": [
                {
                    "id": str(e.id),
                    "competencia": first_of_month(e.competencia),
                    "kind": e.kind,
                    "amount": float(e.amount),
                    "description": e.description,
                }
                for e in sorted(eventos_persistidos or [], key=lambda e: e.competencia)
            ],
        }

    def _vigencias_com_padrao(
        self, it: CompanyFinancialItem, origem: date, padrao: Decimal
    ) -> tuple[list[RateChange], bool]:
        """Vigências efetivas + se o padrão do SGC está no lugar de uma vigência própria.

        Taxa NÃO definida = herda o padrão do SGC. É decisão de produto: uma dívida que ninguém
        configurou deve mostrar a evolução com correção, não ficar parada no tempo. Para
        CONGELAR, o usuário lança explicitamente uma vigência de 0%.

        O padrão só entra quando NÃO há vigência nenhuma: a partir do momento em que alguém
        define uma, ela manda — inclusive deixando sem correção os meses anteriores a ela.
        """
        vigencias = self._rates(it)
        if vigencias:
            return vigencias, False
        if padrao > 0:
            return [RateChange(valid_from=origem, monthly_rate=padrao)], True
        return [], False

    async def _default_rate(self) -> Decimal:
        settings = await SettingsService(self.db).get_or_create()
        return Decimal(str(getattr(settings, "debt_default_monthly_rate", 0) or 0))

    async def ledger(
        self,
        *,
        item_id: UUID,
        projection_months: int = DEFAULT_PROJECTION_MONTHS,
        today: date | None = None,
    ) -> dict | None:
        """Razão da dívida: uma linha por competência, da origem até hoje + projeção.

        `projection_months` estende o razão para o futuro sem pagamento nenhum — é a resposta a
        "onde essa dívida vai parar se ninguém pagar".
        """
        it = await self._load_item(item_id)
        if it is None or it.tipo != "endividamento":
            return None

        origem = self.origin_month(it)
        vigencias, usando_padrao = self._vigencias_com_padrao(it, origem, await self._default_rate())
        return self._render(
            it=it,
            origem=origem,
            principal=Decimal(str(it.valor_referencia or 0)),
            vigencias=vigencias,
            usando_padrao=usando_padrao,
            eventos=self._events(it),
            pagamentos=self._payments_by_month(it),
            repasses=await self._repasse_by_month(item_id),
            projection_months=projection_months,
            today=today,
            taxas_persistidas=list(it.rates or []),
            eventos_persistidos=list(it.events or []),
        )

    # ------------------------------------------------------------------ #
    # Escrita — vigências de taxa                                        #
    # ------------------------------------------------------------------ #

    async def _assert_debt(self, item_id: UUID) -> CompanyFinancialItem | None:
        it = (
            await self.db.execute(
                select(CompanyFinancialItem).where(CompanyFinancialItem.id == item_id)
            )
        ).scalars().first()
        return it if it is not None and it.tipo == "endividamento" else None

    async def set_rate(
        self, *, item_id: UUID, valid_from: date, monthly_rate: Decimal | float, note: str | None = None
    ) -> CompanyFinancialRate | None:
        """Cria (ou substitui) a vigência de taxa daquela competência.

        Substituir a vigência de um mês é correção de digitação; mudar a taxa de verdade é
        criar uma vigência NOVA num mês posterior, preservando o que valia antes.
        """
        it = await self._assert_debt(item_id)
        if it is None:
            return None
        rate = Decimal(str(monthly_rate))
        if rate < 0:
            raise ValueError("A taxa não pode ser negativa.")
        if rate > 1:
            raise ValueError("Taxa mensal acima de 100% — informe em decimal (0.005 = 0,5% a.m.).")
        comp = first_of_month(valid_from)

        existente = (
            await self.db.execute(
                select(CompanyFinancialRate).where(
                    CompanyFinancialRate.item_id == item_id,
                    CompanyFinancialRate.valid_from == comp,
                )
            )
        ).scalars().first()
        if existente is not None:
            existente.monthly_rate = float(rate)
            existente.note = note
            await self.db.flush()
            return existente

        novo = CompanyFinancialRate(
            item_id=item_id, valid_from=comp, monthly_rate=float(rate), note=note
        )
        self.db.add(novo)
        await self.db.flush()
        return novo

    async def delete_rate(self, *, item_id: UUID, rate_id: UUID) -> bool:
        row = (
            await self.db.execute(
                select(CompanyFinancialRate).where(
                    CompanyFinancialRate.id == rate_id, CompanyFinancialRate.item_id == item_id
                )
            )
        ).scalars().first()
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    # ------------------------------------------------------------------ #
    # Escrita — eventos de saldo                                          #
    # ------------------------------------------------------------------ #

    async def add_event(
        self,
        *,
        item_id: UUID,
        competencia: date,
        kind: str,
        amount: Decimal | float,
        description: str | None = None,
    ) -> CompanyFinancialEvent | None:
        it = await self._assert_debt(item_id)
        if it is None:
            return None
        if kind not in EVENT_KINDS:
            raise ValueError(f"Tipo de evento inválido: {kind!r}.")
        valor = Decimal(str(amount))
        if valor <= 0:
            raise ValueError("O valor do evento deve ser maior que zero (o sinal vem do tipo).")

        ev = CompanyFinancialEvent(
            item_id=item_id,
            competencia=first_of_month(competencia),
            kind=kind,
            amount=float(valor),
            description=description,
        )
        self.db.add(ev)
        await self.db.flush()
        return ev

    async def delete_event(self, *, item_id: UUID, event_id: UUID) -> bool:
        row = (
            await self.db.execute(
                select(CompanyFinancialEvent).where(
                    CompanyFinancialEvent.id == event_id, CompanyFinancialEvent.item_id == item_id
                )
            )
        ).scalars().first()
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    # ------------------------------------------------------------------ #
    # Escrita — o razão inteiro de uma vez (o "Salvar" do modal)          #
    # ------------------------------------------------------------------ #

    async def replace_ledger(
        self,
        *,
        item_id: UUID,
        start_month: date | None = None,
        principal: Decimal | float | None = None,
        linhas: list[dict] | None = None,
    ) -> dict:
        """Substitui parâmetros + vigências + eventos + pagamentos numa transação só.

        É o "Salvar" da tela de evolução, no mesmo espírito do `replace_schedule`: o usuário
        edita a planilha inteira e grava uma vez. Cada linha traz a competência e, opcionalmente,
        `taxa`, `aporte`, `abatimento` e `pagamento` — cada um deles um campo digitável na
        própria linha, como na planilha do financeiro.

        Semântica de cada campo (a mesma da tela):
        - `taxa` preenchida → cria vigência NAQUELE mês (e passa a valer dali para frente).
          Vazia → a linha não define nada e herda o mês anterior. Zero → CONGELA a partir dali.
        - `aporte`/`abatimento` preenchidos → evento naquele mês; vazios → nenhum evento.
        - `pagamento` → delegado ao caminho de sempre (`replace_payments`), que é quem
          sincroniza o Contas a Pagar. O motor NUNCA escreve no CAP por conta própria.

        Vigências e eventos são substituídos por completo a partir das linhas recebidas: o que
        não vier na carga deixa de existir. Pagamento não: ele segue incremental, para nunca
        apagar um lançamento já conciliado que não esteja na janela editada.
        """
        from app.services.company_finance_service import CompanyFinanceService, month_key

        it = await self._assert_debt(item_id)
        if it is None:
            return {}

        if start_month is not None:
            it.start_date = first_of_month(start_month)
        if principal is not None:
            valor = Decimal(str(principal))
            if valor < 0:
                raise ValueError("O valor de origem não pode ser negativo.")
            it.valor_referencia = float(valor)

        rows = linhas or []

        # Vigências e eventos: substituição total a partir das linhas.
        await self.db.execute(
            delete(CompanyFinancialRate).where(CompanyFinancialRate.item_id == item_id)
        )
        await self.db.execute(
            delete(CompanyFinancialEvent).where(CompanyFinancialEvent.item_id == item_id)
        )

        pagamentos: list[dict] = []
        for row in rows:
            comp = first_of_month(row["competencia"])
            taxa = row.get("taxa")
            if taxa is not None:
                rate = Decimal(str(taxa))
                if rate < 0 or rate > 1:
                    raise ValueError(
                        f"Taxa inválida em {month_key(comp)} — informe em decimal (0.005 = 0,5% a.m.)."
                    )
                self.db.add(
                    CompanyFinancialRate(
                        item_id=item_id, valid_from=comp, monthly_rate=float(rate), note=row.get("nota")
                    )
                )
            for campo, kind in (("aporte", APORTE), ("abatimento", ABATIMENTO), ("encargo_manual", ENCARGO_MANUAL)):
                valor_ev = row.get(campo)
                if valor_ev is None:
                    continue
                dec = Decimal(str(valor_ev))
                if dec <= 0:
                    continue
                self.db.add(
                    CompanyFinancialEvent(
                        item_id=item_id,
                        competencia=comp,
                        kind=kind,
                        amount=float(dec),
                        description=row.get("descricao"),
                    )
                )
            if "pagamento" in row:
                pagamentos.append({"mes": month_key(comp), "valor": row.get("pagamento")})

        await self.db.flush()

        aviso = None
        if pagamentos:
            # Caminho de sempre: é ele que materializa/atualiza os títulos no Contas a Pagar.
            svc = CompanyFinanceService(self.db)
            resultado = await svc.replace_payments(
                item_id=item_id, pagamentos=pagamentos, zero_explicito=True
            )
            if resultado is None:
                raise ValueError("Item não encontrado ao gravar os pagamentos.")
            # Mesmo aviso da grade: mês que já tinha pagamento não é reescrito no CAP.
            skipped = (svc.last_payable_sync or {}).get("skipped_paid") or []
            if skipped:
                meses = ", ".join(f"{d:%m/%Y}" for d in sorted(skipped))
                aviso = (
                    f"Existe pagamento registrado em {meses}: o Contas a Pagar não foi ajustado "
                    "automaticamente. Ajuste o lançamento manualmente para preservar o histórico."
                )

        return {"payable_sync_warning": aviso}

    async def preview_ledger(
        self,
        *,
        item_id: UUID,
        start_month: date | None = None,
        principal: Decimal | float | None = None,
        linhas: list[dict] | None = None,
        projection_months: int = DEFAULT_PROJECTION_MONTHS,
        today: date | None = None,
    ) -> dict | None:
        """Recalcula o razão a partir do que está DIGITADO na tela, sem gravar nada.

        É o que permite a planilha responder enquanto o usuário digita sem duplicar uma linha
        de regra financeira no frontend — mesmo padrão do `preview_ranges` do Cronograma.
        """
        it = await self._load_item(item_id)
        if it is None or it.tipo != "endividamento":
            return None

        rows = linhas or []
        origem = first_of_month(start_month) if start_month else self.origin_month(it)
        base = Decimal(str(principal)) if principal is not None else Decimal(str(it.valor_referencia or 0))

        # A carga digitada é a fonte do preview — MAS só quando existe. Um payload vazio (a
        # abertura da tela, ou uma troca de horizonte de projeção) tem que espelhar o que está
        # gravado; tratá-lo como "sem taxa nenhuma" fazia as vigências e os aportes já salvos
        # desaparecerem ao reabrir o modal, e a dívida voltava a exibir o padrão do SGC.
        if not rows:
            vigencias, usando_padrao = self._vigencias_com_padrao(it, origem, await self._default_rate())
        else:
            vigencias = [
                RateChange(valid_from=first_of_month(r["competencia"]), monthly_rate=Decimal(str(r["taxa"])))
                for r in rows
                if r.get("taxa") is not None
            ]
            usando_padrao = False
            if not vigencias:
                padrao = await self._default_rate()
                if padrao > 0:
                    vigencias = [RateChange(valid_from=origem, monthly_rate=padrao)]
                    usando_padrao = True

        eventos: list[LedgerEvent] = [] if rows else self._events(it)
        for r in rows:
            comp = first_of_month(r["competencia"])
            for campo, kind in (("aporte", APORTE), ("abatimento", ABATIMENTO), ("encargo_manual", ENCARGO_MANUAL)):
                valor = r.get(campo)
                if valor is None:
                    continue
                dec = Decimal(str(valor))
                if dec > 0:
                    eventos.append(LedgerEvent(competencia=comp, kind=kind, amount=dec))

        # Pagamento digitado manda; onde a linha não traz o campo, vale o que está gravado.
        pagamentos = self._payments_by_month(it)
        for r in rows:
            if "pagamento" in r:
                comp = first_of_month(r["competencia"])
                valor = r.get("pagamento")
                if valor is None:
                    pagamentos.pop(comp, None)
                else:
                    pagamentos[comp] = Decimal(str(valor))

        return self._render(
            it=it,
            origem=origem,
            principal=base,
            vigencias=vigencias,
            usando_padrao=usando_padrao,
            eventos=eventos,
            pagamentos=pagamentos,
            repasses=await self._repasse_by_month(item_id),
            projection_months=projection_months,
            today=today,
            taxas_persistidas=list(it.rates or []),
            eventos_persistidos=list(it.events or []),
        )

    async def plan_installments_for(
        self,
        *,
        item_id: UUID,
        start_month: date,
        mode: str,
        amount: Decimal | float | None = None,
        count: int | None = None,
        today: date | None = None,
    ) -> dict | None:
        """Calcula as parcelas a partir do SALDO da dívida no mês em que o plano começa.

        O saldo não é informado pelo usuário: é o que o razão mostra no mês anterior ao início
        do plano — assim o parcelamento sempre parte do número real, com juros e aportes dentro.
        """
        it = await self._load_item(item_id)
        if it is None or it.tipo != "endividamento":
            return None

        origem = self.origin_month(it)
        inicio = first_of_month(start_month)
        if inicio < origem:
            raise ValueError("O plano não pode começar antes do início da dívida.")

        vigencias, _padrao = self._vigencias_com_padrao(it, origem, await self._default_rate())

        if inicio == origem:
            saldo = Decimal(str(it.valor_referencia or 0))
        else:
            anterior = build_ledger(
                principal=Decimal(str(it.valor_referencia or 0)),
                origin_month=origem,
                through=add_months(inicio, -1),
                rates=vigencias,
                events=self._events(it),
                payments=self._payments_by_month(it),
            )
            saldo = anterior[-1].saldo_final

        plano = plan_installments(
            saldo=saldo, start_month=inicio, rates=vigencias, mode=mode, amount=amount, count=count
        )
        return {
            "saldo_base": float(saldo),
            "competencia_inicial": inicio,
            "total_pago": float(plano.total_pago),
            "total_juros": float(plano.total_juros),
            "parcelas": [
                {
                    "competencia": x.competencia,
                    "juros": float(x.juros),
                    "amortizacao": float(x.amortizacao),
                    "valor": float(x.valor),
                    "saldo_final": float(x.saldo_final),
                }
                for x in plano.parcelas
            ],
        }
