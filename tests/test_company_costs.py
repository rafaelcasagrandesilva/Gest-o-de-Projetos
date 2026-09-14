"""Custos da empresa: rateio da frota e itens com o projeto como centro de custo (puro)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date
from types import SimpleNamespace

from app.services.company_costs import (
    FLEET_ADDITIONAL,
    FLEET_RENTAL,
    CompanyCostMonth,
    CostLine,
    FleetMonth,
    fleet_for_month,
    split_month,
)

AGO = date(2026, 8, 1)
FISC = uuid.uuid4()
SUB = uuid.uuid4()
PROJECTS = {"fiscalização at": FISC, "subterrâneo": SUB}
# Frota de agosto: Fiscalização AT 20 mil, Subterrâneo 5 mil, Diretoria 15 mil (total 40 mil).
FLEET = FleetMonth(shares={FISC: 0.5, SUB: 0.125, None: 0.375}, registry_total=40_000.0)


def vehicle(cost_center, cost, **kw):
    base = dict(cost_center=cost_center, monthly_cost=cost, is_active=True, start_date=None, end_date=None, deleted_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def total(indirect, projects):
    return sum(line.amount for line in indirect) + sum(l.amount for lines in projects.values() for l in lines)


class FleetRegistryTests(unittest.TestCase):
    def test_frota_ativa_pela_aquisicao_e_devolucao(self) -> None:
        fleet = fleet_for_month(
            [
                vehicle("Fiscalização AT", 20_000),
                vehicle("Subterrâneo", 5_000),
                vehicle("Diretoria", 15_000),
                vehicle("Fiscalização AT", 9_999, deleted_at=date(2026, 1, 1)),  # excluído
                vehicle("Subterrâneo", 9_999, end_date=date(2026, 7, 31), is_active=False),  # devolvido em julho
                vehicle("Diretoria", 9_999, start_date=date(2026, 9, 1)),  # adquirido em setembro
                vehicle(None, 9_999, is_active=False, end_date=date(2026, 8, 3)),  # sem centro de custo
                vehicle("  ", 9_999),  # centro de custo em branco
            ],
            comp=AGO,
            project_by_cost_center=PROJECTS,
        )
        self.assertAlmostEqual(fleet.registry_total, 40_000)
        self.assertAlmostEqual(fleet.shares[FISC], 0.5)
        self.assertAlmostEqual(fleet.shares[SUB], 0.125)
        self.assertAlmostEqual(fleet.shares[None], 0.375)  # Diretoria/Administrativo = indireto

    def test_sem_veiculo_nao_ha_rateio(self) -> None:
        fleet = fleet_for_month([], comp=AGO, project_by_cost_center=PROJECTS)
        self.assertEqual((fleet.shares, fleet.registry_total), ({}, 0))


class SplitMonthTests(unittest.TestCase):
    def test_com_fatura_de_locacao_vale_o_valor_devido(self) -> None:
        month = CompanyCostMonth(
            paid_basis=True,
            indirect=[
                # Movida em aberto: pago 0, devido 37.377 → a frota custa o devido
                CostLine(uuid.uuid4(), "Movida - Locação Frota", "Custos diversos", False, 0.0, 37_377.0, fleet=FLEET_RENTAL),
                CostLine(uuid.uuid4(), "Aluguel", "Custos diversos", False, 2_300.0),
            ],
        )
        indirect, projects = split_month(month, FLEET)
        self.assertAlmostEqual(sum(l.amount for l in projects[FISC]), 37_377.0 * 0.5)
        movida = next(l for l in indirect if l.fleet == FLEET_RENTAL)
        self.assertAlmostEqual((movida.amount, movida.open_amount), (37_377.0 * 0.375, 0.0))
        self.assertAlmostEqual(total(indirect, projects), 37_377.0 + 2_300.0)

    def test_sem_fatura_vale_o_custo_dos_veiculos_ativos(self) -> None:
        indirect, projects = split_month(CompanyCostMonth(paid_basis=True), FLEET)
        self.assertAlmostEqual(sum(l.amount for l in projects[FISC]), 20_000.0)
        self.assertAlmostEqual(sum(l.amount for l in projects[SUB]), 5_000.0)
        self.assertAlmostEqual(sum(l.amount for l in indirect), 15_000.0)  # carros da Diretoria

    def test_mes_projetado_ignora_a_projecao_da_fatura_e_usa_o_cadastro(self) -> None:
        month = CompanyCostMonth(
            projected=True,
            indirect=[CostLine(uuid.uuid4(), "Movida", "C", False, 37_377.0, fleet=FLEET_RENTAL)],
        )
        indirect, projects = split_month(month, FLEET)
        self.assertAlmostEqual(total(indirect, projects), 40_000.0)

    def test_custo_adicional_soma_e_itens_do_projeto_viram_diretos(self) -> None:
        month = CompanyCostMonth(
            indirect=[
                CostLine(uuid.uuid4(), "Movida", "C", False, 40_000.0, fleet=FLEET_RENTAL),
                CostLine(uuid.uuid4(), "Seguro Frota", "C", False, 4_000.0, fleet=FLEET_ADDITIONAL),
                CostLine(uuid.uuid4(), "TICKET - FISCALIZAÇÃO AT", "Combustível", False, 6_000.0, project_id=FISC),
            ]
        )
        indirect, projects = split_month(month, FLEET)
        fleet_fisc = sum(l.amount for l in projects[FISC] if l.fleet)
        self.assertAlmostEqual(fleet_fisc, 20_000.0 + 2_000.0)  # locação + seguro
        self.assertAlmostEqual(sum(l.amount for l in projects[FISC] if not l.fleet), 6_000.0)
        self.assertAlmostEqual(total(indirect, projects), 50_000.0)  # nada some nem duplica

    def test_resultado_realizado_conta_so_a_fatura_paga_e_nada_sem_fatura(self) -> None:
        month = CompanyCostMonth(
            paid_basis=True,
            indirect=[CostLine(uuid.uuid4(), "Movida", "C", False, 10_000.0, 30_000.0, fleet=FLEET_RENTAL)],
        )
        indirect, projects = split_month(month, FLEET, rental_due=False, registry_fallback=False)
        self.assertAlmostEqual(total(indirect, projects), 10_000.0)  # só o pago
        open_total = sum(l.open_amount for l in indirect) + sum(l.open_amount for ls in projects.values() for l in ls)
        self.assertAlmostEqual(open_total, 30_000.0)  # o resto fica "a pagar"
        indirect, projects = split_month(CompanyCostMonth(paid_basis=True), FLEET, rental_due=False, registry_fallback=False)
        self.assertEqual((indirect, dict(projects)), ([], {}))

    def test_frota_sem_cadastro_de_veiculos_fica_toda_indireta(self) -> None:
        month = CompanyCostMonth(indirect=[CostLine(None, "Movida", "C", False, 40_000.0, fleet=FLEET_RENTAL)])
        indirect, projects = split_month(month, FleetMonth(shares={}, registry_total=0.0))
        self.assertEqual((len(indirect), dict(projects)), (1, {}))


if __name__ == "__main__":
    unittest.main()
