from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scenario import DEFAULT_SCENARIO, Scenario, coerce_scenario, scenario_pg_rhs
from app.models.costs import ProjectCost, ProjectFixedCost
from app.models.financial import Revenue
from app.models.project_operational import ProjectLabor, ProjectOperationalFixed, ProjectSystemCost, ProjectVehicle
from app.services.anticipation_rate import SOURCE_PARCIAL, AnticipationRate, AnticipationRateResolver
from app.services.invoice_billing import billed_totals_by_competencia
from app.services.employee_cost_service import project_labor_full_monthly_cost
from app.utils.date_utils import normalize_competencia

logger = logging.getLogger(__name__)

_legacy_project_costs_warning_done = False


def custo_percentual_receita(cost: float, receita: float) -> float:
    """Percentual do custo sobre a receita (0–100), 1 casa decimal; receita ≤ 0 → 0."""
    if receita <= 0:
        return 0.0
    return round((float(cost) / float(receita)) * 100.0, 1)


class FinancialService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._anticipation: AnticipationRateResolver | None = None

    async def taxa_antecipacao(
        self, *, settings, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> AnticipationRate:
        """Taxa de antecipação da competência (fixa ou automática pelos borderôs).

        Sempre aplicada sobre a receita — no total e em cada projeto —, o que reparte o custo real
        do mês entre os projetos proporcionalmente à receita. Regra em `anticipation_rate.py`.
        """
        if self._anticipation is None:
            self._anticipation = AnticipationRateResolver(
                self.session,
                lambda m: self.calcular_receita_total(project_id=None, competencia=m, scenario=Scenario.REALIZADO),
            )
        return await self._anticipation.resolve(settings=settings, competencia=competencia, scenario=scenario)

    async def warn_if_legacy_project_costs_exist(self) -> None:
        """Avisa uma vez por processo se ainda houver linhas em project_costs (ignoradas nos cálculos)."""
        global _legacy_project_costs_warning_done
        if _legacy_project_costs_warning_done:
            return
        stmt = select(func.count()).select_from(ProjectCost)
        n = int((await self.session.execute(stmt)).scalar_one())
        if n > 0:
            logger.warning(
                "Existem %d registro(s) na tabela legada project_costs (/expenses); "
                "eles não entram mais em custos, dashboard ou margem.",
                n,
            )
        _legacy_project_costs_warning_done = True

    async def _revenue_rows_efetivos(
        self, *, project_id: UUID | None, competencia: date, scenario: str | Scenario
    ) -> list[tuple[float, bool]]:
        """Lançamentos da competência como (valor efetivo, has_retention).

        "Efetivo" = o valor manual, ou a soma das NFs faturadas do mês quando o lançamento
        está marcado com `use_nf_amount` (migration 0124). O manual nunca é sobrescrito no
        banco — a troca acontece só aqui, no cálculo, então desmarcar devolve o original.

        Fonte única de receita E de retenção: as duas saem desta mesma lista, para que a
        retenção não possa incidir sobre uma base diferente da receita.
        """
        sc = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = select(Revenue).where(
            Revenue.competencia == comp,
            Revenue.scenario == scenario_pg_rhs(sc),
        )
        if project_id is not None:
            stmt = stmt.where(Revenue.project_id == project_id)
        rows = list((await self.session.execute(stmt)).scalars())
        if not rows:
            return []

        # A soma faturada só é consultada quando alguma linha realmente pede por ela.
        billed: dict[tuple[UUID, date], float] = {}
        if any(r.use_nf_amount for r in rows):
            billed = await billed_totals_by_competencia(
                self.session,
                project_ids=list({r.project_id for r in rows if r.use_nf_amount}),
                competencias=[comp],
            )

        out: list[tuple[float, bool]] = []
        for r in rows:
            if r.use_nf_amount:
                # Sem NF faturada no mês o valor efetivo é zero, e não o manual: a marcação é
                # uma escolha explícita do gestor por "usar o que foi faturado", e cair de
                # volta no manual esconderia dele que não há nota nenhuma naquela competência.
                amount = billed.get((r.project_id, comp), 0.0)
            else:
                amount = float(r.amount or 0)
            out.append((amount, bool(r.has_retention)))
        return out

    async def calcular_receita_total(
        self, *, project_id: UUID | None, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> float:
        rows = await self._revenue_rows_efetivos(
            project_id=project_id, competencia=competencia, scenario=scenario
        )
        return round(float(sum(amount for amount, _ in rows)), 2)

    async def calcular_total_retencao(
        self, *, project_id: UUID | None, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> float:
        """Soma 10% do valor efetivo por lançamento com has_retention (alinhado a revenue_retention_value)."""
        rows = await self._revenue_rows_efetivos(
            project_id=project_id, competencia=competencia, scenario=scenario
        )
        return round(float(sum(amount * 0.10 for amount, has_ret in rows if has_ret)), 2)

    async def calcular_lucro(
        self, *, project_id: UUID | None, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> float:
        sc = coerce_scenario(scenario)
        if project_id is not None:
            cons = await self.calcular_consolidado_projeto(
                project_id=project_id, competencia=competencia, scenario=sc
            )
        else:
            cons = await self.calcular_consolidado_global(competencia=competencia, scenario=sc)
        return float(cons["profit"])

    async def calcular_margem(
        self, *, project_id: UUID | None, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> float:
        sc = coerce_scenario(scenario)
        if project_id is not None:
            cons = await self.calcular_consolidado_projeto(
                project_id=project_id, competencia=competencia, scenario=sc
            )
        else:
            cons = await self.calcular_consolidado_global(competencia=competencia, scenario=sc)
        return float(cons["margin"])

    async def get_settings_row(self):
        from app.services.settings_service import SettingsService

        return await SettingsService(self.session).get_or_create()

    async def _sum_operational_column(
        self, model, column, *, project_id: UUID | None, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> float:
        sc = coerce_scenario(scenario)
        stmt = select(func.coalesce(func.sum(column), 0)).where(
            model.competencia == competencia,
            model.scenario == scenario_pg_rhs(sc),
        )
        if project_id is not None:
            stmt = stmt.where(model.project_id == project_id)
        res = await self.session.execute(stmt)
        return float(res.scalar_one())

    async def _sum_project_fixed_costs_legacy(
        self, *, project_id: UUID | None, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> float:
        sc = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = select(func.coalesce(func.sum(ProjectFixedCost.amount_real), 0)).where(
            ProjectFixedCost.competencia == comp,
            ProjectFixedCost.scenario == scenario_pg_rhs(sc),
        )
        if project_id is not None:
            stmt = stmt.where(ProjectFixedCost.project_id == project_id)
        res = await self.session.execute(stmt)
        return float(res.scalar_one())

    async def _sum_labor_costs_derived(
        self, *, project_id: UUID | None, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> float:
        sc = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        stmt = (
            select(ProjectLabor)
            .options(selectinload(ProjectLabor.employee))
            .where(ProjectLabor.competencia == comp, ProjectLabor.scenario == scenario_pg_rhs(sc))
        )
        if project_id is not None:
            stmt = stmt.where(ProjectLabor.project_id == project_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        settings = await self.get_settings_row()
        total = 0.0
        for row in rows:
            emp = row.employee
            if not emp:
                continue
            full = project_labor_full_monthly_cost(emp, settings, comp, row)
            factor = float(row.allocation_percentage) / 100.0
            total += full * factor
        # Avulsos (Componentes Variáveis) do colaborador no projeto — custo REAL, somado por
        # valor de face (sem rateio, igual ao CAP). Mesma fonte do resumo por colaborador;
        # não duplica com o CAP (a margem deriva do custo de labor, não do CAP).
        from app.services.payment_variable_component_service import PaymentVariableComponentService

        var_by_labor = await PaymentVariableComponentService(self.session).sum_amount_by_project_labor(
            [r.id for r in rows]
        )
        total += sum(var_by_labor.values())
        return total

    async def _payroll_paid_by_project(self, *, competencia: date) -> dict[UUID, float] | None:
        """Folha REAL (paga) do mês trabalhado, por projeto, pelo Contas a Pagar.

        A folha do mês M é paga no CAP de M+1 (títulos de Colaborador com projeto, inclusive os
        componentes variáveis). Só vale para mês FECHADO: o mês do pagamento já terminou — aí o que
        conta é o valor efetivamente PAGO. Mês ainda aberto ou sem títulos de folha no CAP → None
        (o chamador usa a estimativa pelo cadastro).
        """
        from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
        from app.utils.date_utils import next_competencia

        comp = normalize_competencia(competencia)
        pay_month = next_competencia(comp)
        if pay_month >= date.today().replace(day=1):
            return None
        cache = self.__dict__.setdefault("_payroll_cache", {})
        if comp not in cache:
            rows = (
                await self.session.execute(
                    select(PayableSnapshot.project_id, func.coalesce(func.sum(PayableSnapshot.amount_paid), 0))
                    .where(
                        PayableSnapshot.month == pay_month,
                        PayableSnapshot.type == PayableSnapshotType.COLLABORATOR,
                        PayableSnapshot.project_id.is_not(None),
                        PayableSnapshot.is_obsolete.is_(False),
                        PayableSnapshot.include_in_dashboard.is_(True),
                    )
                    .group_by(PayableSnapshot.project_id)
                )
            ).all()
            cache[comp] = {pid: float(total or 0) for pid, total in rows} if rows else None
        return cache[comp]

    async def _labor_cost(
        self, *, project_id: UUID | None, competencia: date, scenario: Scenario
    ) -> tuple[float, bool]:
        """(custo de mão de obra, veio da folha real do CAP?).

        REALIZADO em mês fechado com lançamentos na aba Realizado → folha PAGA no CAP (salário e
        VR/VT reais; encargos recolhidos em guia ficam nos custos indiretos). Demais casos →
        estimativa pelo cadastro (salário + encargos configurados).
        """
        estimate = await self._sum_labor_costs_derived(project_id=project_id, competencia=competencia, scenario=scenario)
        if scenario != Scenario.REALIZADO or estimate <= 0:
            return estimate, False
        paid = await self._payroll_paid_by_project(competencia=competencia)
        if paid is None:
            return estimate, False
        if project_id is not None:
            return paid.get(project_id, 0.0), True
        return sum(paid.values()), True

    async def calcular_operacional_estruturado(
        self, *, project_id: UUID | None, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> dict:
        sc = coerce_scenario(scenario)
        labor, labor_from_payables = await self._labor_cost(
            project_id=project_id, competencia=competencia, scenario=sc
        )
        vehicle = await self._sum_operational_column(
            ProjectVehicle,
            ProjectVehicle.monthly_cost,
            project_id=project_id,
            competencia=competencia,
            scenario=sc,
        )
        system = await self._sum_operational_column(
            ProjectSystemCost,
            ProjectSystemCost.value,
            project_id=project_id,
            competencia=competencia,
            scenario=sc,
        )
        fixed_op = await self._sum_operational_column(
            ProjectOperationalFixed,
            ProjectOperationalFixed.value,
            project_id=project_id,
            competencia=competencia,
            scenario=sc,
        )
        fixed_legacy = await self._sum_project_fixed_costs_legacy(
            project_id=project_id, competencia=competencia, scenario=sc
        )
        fixed = fixed_op + fixed_legacy
        groups, fleet_share, fleet_available = await self._project_cost_groups(
            project_id=project_id, competencia=competencia
        )
        # Frota (REALIZADO): parte do projeto na fatura de locação do CAP (valor devido) ou, sem
        # fatura, no custo mensal dos veículos ativos do cadastro — mais o custo adicional da frota
        # (seguro). Substitui o custo lançado pelos gestores; no PREVISTO fica o lançamento.
        vehicle_real = sc == Scenario.REALIZADO and fleet_available
        if vehicle_real:
            vehicle = fleet_share
        # Itens dos Custos Indiretos com o projeto como centro de custo somam na ORIGEM RAIZ indicada
        # no cadastro do item (combustível → veículos, plano de saúde → mão de obra, …).
        from app.services.company_costs import (
            PROJECT_GROUP_FIXED,
            PROJECT_GROUP_LABOR,
            PROJECT_GROUP_SYSTEMS,
            PROJECT_GROUP_VEHICLES,
        )

        labor += groups.get(PROJECT_GROUP_LABOR, 0.0)
        vehicle += groups.get(PROJECT_GROUP_VEHICLES, 0.0)
        system += groups.get(PROJECT_GROUP_SYSTEMS, 0.0)
        fixed += groups.get(PROJECT_GROUP_FIXED, 0.0)
        operational = labor + vehicle + system + fixed
        return {
            "labor_cost": labor,
            "vehicle_cost": vehicle,
            "system_cost": system,
            "fixed_operational_cost": fixed,
            "operational_cost": operational,
            "labor_real": labor_from_payables,
            "vehicle_real": vehicle_real,
        }

    async def _project_cost_groups(
        self, *, project_id: UUID | None, competencia: date
    ) -> tuple[dict[str, float], float, bool]:
        """(itens do projeto por custo raiz, parte do projeto na frota rateada, há base de frota?).

        Há base de frota quando existe cadastro de veículos ativos no mês (com ou sem fatura no CAP):
        aí a parte do projeto substitui o custo lançado pelos gestores.
        """
        from app.services.company_costs import project_group_of

        _, _, by_project = await self.company_costs_for_month(competencia)
        fleet_month = self.__dict__["_company_costs_cache"][normalize_competencia(competencia)][3]
        if project_id is None:
            lines = [line for project_lines in by_project.values() for line in project_lines]
        else:
            lines = by_project.get(project_id, [])
        groups: dict[str, float] = {}
        fleet = 0.0
        for line in lines:
            if line.fleet:
                fleet += line.amount
            else:
                group = project_group_of(line)
                groups[group] = groups.get(group, 0.0) + line.amount
        return groups, fleet, bool(fleet_month.shares)

    async def company_costs_for_month(self, competencia: date):
        """(custos da empresa do mês trabalhado, linhas indiretas, linhas diretas por projeto) — com cache.

        Regra única: o faturamento do mês M paga as contas do mês M+1. Por isso as contas da
        empresa (custos indiretos, dívidas, fatura da frota, itens do projeto) do mês trabalhado M
        vêm do Contas a Pagar de M+1 — como a folha paga e a antecipação. A frota do cadastro de
        Veículos é a ativa no próprio mês trabalhado.

        Fonte única para o Dashboard Operacional e o Resultado da Empresa (`company_costs`).
        """
        from app.services.company_costs import load_company_costs, load_fleet, split_month
        from app.utils.date_utils import next_competencia

        comp = normalize_competencia(competencia)
        cache = self.__dict__.setdefault("_company_costs_cache", {})
        if comp not in cache:
            settings = await self.get_settings_row()
            pay_month = next_competencia(comp)
            month = (await load_company_costs(self.session, [pay_month], settings=settings))[pay_month]
            fleet = (await load_fleet(self.session, [comp]))[comp]
            indirect, by_project = split_month(month, fleet)
            cache[comp] = (month, indirect, by_project, fleet)
        return cache[comp][:3]

    async def _tax_periods(self) -> list[tuple[date, str]]:
        cache = self.__dict__.get("_tax_periods_cache")
        if cache is None:
            from app.models.tax_regime import TaxRegimePeriod

            rows = (await self.session.execute(select(TaxRegimePeriod.start_date, TaxRegimePeriod.regime))).all()
            cache = [(start, regime) for start, regime in rows]
            self.__dict__["_tax_periods_cache"] = cache
        return cache

    async def impostos_receita(self, *, receita: float, competencia: date, scenario: Scenario):
        """Tributos sobre a receita pelo regime vigente na competência (`tax_calc`)."""
        from app.services.tax_calc import LUCRO_PRESUMIDO, regime_for_competencia, revenue_taxes

        settings = await self.get_settings_row()
        regime = regime_for_competencia(await self._tax_periods(), competencia)
        company_revenue = receita
        if regime == LUCRO_PRESUMIDO:
            # O adicional de IRPJ olha a receita da EMPRESA no mês; o projeto leva a parte dele.
            company_revenue = await self.calcular_receita_total(
                project_id=None, competencia=competencia, scenario=scenario
            )
        return revenue_taxes(regime=regime, settings=settings, revenue=receita, company_revenue=company_revenue)

    async def calcular_consolidado_projeto(
        self, *, project_id: UUID, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> dict:
        sc = coerce_scenario(scenario)
        settings = await self.get_settings_row()
        receita = await self.calcular_receita_total(
            project_id=project_id, competencia=competencia, scenario=sc
        )
        total_retention = await self.calcular_total_retencao(
            project_id=project_id, competencia=competencia, scenario=sc
        )
        parts = await self.calcular_operacional_estruturado(
            project_id=project_id, competencia=competencia, scenario=sc
        )
        impostos = await self.impostos_receita(receita=receita, competencia=competencia, scenario=sc)
        tax = impostos.total
        overhead = receita * float(settings.overhead_rate)
        antecipacao = await self.taxa_antecipacao(settings=settings, competencia=competencia, scenario=sc)
        anticipation = receita * antecipacao.rate
        total_cost = parts["operational_cost"] + tax + overhead + anticipation
        operational_profit = receita - total_cost
        net_profit = operational_profit - total_retention
        margin_operational = 0.0 if receita == 0 else float(operational_profit / receita)
        margin_net = 0.0 if receita == 0 else float(net_profit / receita)
        ebitda = receita - parts["operational_cost"] - overhead
        ebitda_margin = 0.0 if receita == 0 else float(ebitda / receita)
        p = custo_percentual_receita
        return {
            "revenue_total": receita,
            "total_revenue": receita,
            **parts,
            "tax_amount": tax,
            "tax_regime": impostos.regime,
            "tax_pis": impostos.pis,
            "tax_cofins": impostos.cofins,
            "tax_iss": impostos.iss,
            "tax_irpj": impostos.irpj,
            "tax_csll": impostos.csll,
            "overhead_amount": overhead,
            "anticipation_amount": anticipation,
            "anticipation_rate_used": antecipacao.rate,
            "anticipation_source": antecipacao.source,
            "anticipation_partial": antecipacao.source == SOURCE_PARCIAL,
            # Custo da antecipação por instituição (Lepta, Daycoval…): mesma divisão do custo usado.
            "anticipation_by_institution": {name: anticipation * share for name, share in antecipacao.split},
            "total_cost": total_cost,
            "total_retention": total_retention,
            "operational_profit": operational_profit,
            "net_profit": net_profit,
            "margin_operational": margin_operational,
            "margin_net": margin_net,
            "ebitda": ebitda,
            "ebitda_margin": ebitda_margin,
            "profit": operational_profit,
            "margin": margin_operational,
            "labor_cost_pct": p(parts["labor_cost"], receita),
            "vehicle_cost_pct": p(parts["vehicle_cost"], receita),
            "system_cost_pct": p(parts["system_cost"], receita),
            "fixed_operational_cost_pct": p(parts["fixed_operational_cost"], receita),
            "operational_cost_pct": p(parts["operational_cost"], receita),
            "tax_amount_pct": p(tax, receita),
            "overhead_amount_pct": p(overhead, receita),
            "anticipation_amount_pct": p(anticipation, receita),
        }

    async def calcular_consolidado_global(
        self, *, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> dict:
        sc = coerce_scenario(scenario)
        settings = await self.get_settings_row()
        receita = await self.calcular_receita_total(
            project_id=None, competencia=competencia, scenario=sc
        )
        total_retention = await self.calcular_total_retencao(
            project_id=None, competencia=competencia, scenario=sc
        )
        parts = await self.calcular_operacional_estruturado(
            project_id=None, competencia=competencia, scenario=sc
        )
        impostos = await self.impostos_receita(receita=receita, competencia=competencia, scenario=sc)
        tax = impostos.total
        overhead = receita * float(settings.overhead_rate)
        antecipacao = await self.taxa_antecipacao(settings=settings, competencia=competencia, scenario=sc)
        anticipation = receita * antecipacao.rate
        total_cost = parts["operational_cost"] + tax + overhead + anticipation
        operational_profit = receita - total_cost
        net_profit = operational_profit - total_retention
        margin_operational = 0.0 if receita == 0 else float(operational_profit / receita)
        margin_net = 0.0 if receita == 0 else float(net_profit / receita)
        ebitda = receita - parts["operational_cost"] - overhead
        ebitda_margin = 0.0 if receita == 0 else float(ebitda / receita)
        p = custo_percentual_receita
        return {
            "revenue_total": receita,
            "total_revenue": receita,
            **parts,
            "tax_amount": tax,
            "tax_regime": impostos.regime,
            "tax_pis": impostos.pis,
            "tax_cofins": impostos.cofins,
            "tax_iss": impostos.iss,
            "tax_irpj": impostos.irpj,
            "tax_csll": impostos.csll,
            "overhead_amount": overhead,
            "anticipation_amount": anticipation,
            "anticipation_rate_used": antecipacao.rate,
            "anticipation_source": antecipacao.source,
            "anticipation_partial": antecipacao.source == SOURCE_PARCIAL,
            # Custo da antecipação por instituição (Lepta, Daycoval…): mesma divisão do custo usado.
            "anticipation_by_institution": {name: anticipation * share for name, share in antecipacao.split},
            "total_cost": total_cost,
            "total_retention": total_retention,
            "operational_profit": operational_profit,
            "net_profit": net_profit,
            "margin_operational": margin_operational,
            "margin_net": margin_net,
            "ebitda": ebitda,
            "ebitda_margin": ebitda_margin,
            "profit": operational_profit,
            "margin": margin_operational,
            "labor_cost_pct": p(parts["labor_cost"], receita),
            "vehicle_cost_pct": p(parts["vehicle_cost"], receita),
            "system_cost_pct": p(parts["system_cost"], receita),
            "fixed_operational_cost_pct": p(parts["fixed_operational_cost"], receita),
            "operational_cost_pct": p(parts["operational_cost"], receita),
            "tax_amount_pct": p(tax, receita),
            "overhead_amount_pct": p(overhead, receita),
            "anticipation_amount_pct": p(anticipation, receita),
        }
