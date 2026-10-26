"""Integração com o Medição: chave, rateio de veículos por condutor e folha paga por colaborador (puro)."""

from __future__ import annotations

import hashlib
import unittest
import uuid
from datetime import date
from types import SimpleNamespace

from app.services.medicao_integration import allocate_vehicles, allowed_projects, key_matches, labor_paid_by_employee

SET = date(2026, 9, 1)
FULANO, BELTRANO = uuid.uuid4(), uuid.uuid4()


def vehicle(plate, cost, driver=None, cost_center="Fiscalização AT", **kw):
    base = dict(plate=plate, monthly_cost=cost, driver_employee_id=driver, cost_center=cost_center, is_active=True,
                start_date=None, end_date=None, deleted_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def titulo(ref_id, valor, pago, origin="PAYROLL", name="Fulano — Salário Base PJ"):
    return SimpleNamespace(ref_id=ref_id, origin=origin, name=name, amount_final=valor, amount_paid=pago)


class ChaveTests(unittest.TestCase):
    def test_compara_pelo_sha256(self) -> None:
        h = hashlib.sha256(b"segredo-forte").hexdigest()
        self.assertTrue(key_matches("segredo-forte", h))
        self.assertTrue(key_matches(" segredo-forte ", h.upper()))
        self.assertFalse(key_matches("outra", h))

    def test_sem_configuracao_ou_sem_chave_fica_fechado(self) -> None:
        self.assertFalse(key_matches("qualquer", ""))
        self.assertFalse(key_matches(None, hashlib.sha256(b"x").hexdigest()))
        self.assertFalse(key_matches("", hashlib.sha256(b"").hexdigest()))

    def test_projetos_liberados(self) -> None:
        pid = uuid.uuid4()
        self.assertIn(str(pid).lower(), allowed_projects(f" {str(pid).upper()} , outro"))
        self.assertEqual(allowed_projects(""), set())


class VeiculosTests(unittest.TestCase):
    def test_rateio_pelo_custo_mensal_de_cada_carro(self) -> None:
        frota = [vehicle("AAA", 2000, FULANO), vehicle("BBB", 2000, BELTRANO), vehicle("CCC", 4000),
                 vehicle("DDD", 9999, FULANO, cost_center="Subterrâneo")]
        por, sem = allocate_vehicles(frota, comp=SET, project_cost_center="fiscalização at", total=10_000.0)
        self.assertAlmostEqual(por[FULANO]["amount"], 2500.0)
        self.assertEqual(por[FULANO]["plates"], ["AAA"])
        self.assertAlmostEqual(por[BELTRANO]["amount"], 2500.0)
        self.assertAlmostEqual(sem, 5000.0)          # carro sem condutor fica separado

    def test_carro_devolvido_antes_do_mes_nao_entra(self) -> None:
        frota = [vehicle("AAA", 2000, FULANO), vehicle("BBB", 2000, BELTRANO, end_date=date(2026, 8, 20), is_active=False)]
        por, _ = allocate_vehicles(frota, comp=SET, project_cost_center="fiscalização at", total=3000.0)
        self.assertAlmostEqual(por[FULANO]["amount"], 3000.0)
        self.assertNotIn(BELTRANO, por)

    def test_sem_frota_o_custo_fica_sem_condutor(self) -> None:
        por, sem = allocate_vehicles([], comp=SET, project_cost_center="fiscalização at", total=1500.0)
        self.assertEqual(por, {})
        self.assertAlmostEqual(sem, 1500.0)


class FolhaPagaTests(unittest.TestCase):
    def test_soma_por_colaborador_inclusive_componente_variavel(self) -> None:
        componente = uuid.uuid4()
        rows = [titulo(FULANO, 6000, 6000), titulo(componente, 500, 0, origin="VARIABLE", name="Premiação"),
                titulo(BELTRANO, 4000, 4000)]
        out = labor_paid_by_employee(rows, {componente: FULANO})
        self.assertAlmostEqual(out[FULANO]["amount_final"], 6500.0)
        self.assertAlmostEqual(out[FULANO]["amount_paid"], 6000.0)
        self.assertEqual([c["name"] for c in out[FULANO]["components"]], ["Salário Base PJ", "Pagamento do mês"])

    def test_componente_sem_colaborador_e_ignorado(self) -> None:
        out = labor_paid_by_employee([titulo(uuid.uuid4(), 100, 100, origin="VARIABLE")], {})
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
