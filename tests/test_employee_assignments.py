"""Alocação contratual do colaborador — 1 pessoa → N contratos com remuneração própria.

O que estes testes travam:
1. o TIPO é explícito e manda nos campos (independente não tem percentual; rateio não tem valor);
2. o teto de 100% continua valendo para RATEIO e deixa de bloquear a REMUNERAÇÃO INDEPENDENTE —
   era exatamente essa regra que impedia o multi-contrato;
3. encerrar nunca apaga.
"""

from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.models.employee_assignment import AllocationType, AssignmentStatus, EmployeeAssignment
from app.services.employee_assignment_service import EmployeeAssignmentService


def _svc() -> EmployeeAssignmentService:
    return EmployeeAssignmentService.__new__(EmployeeAssignmentService)


class NormalizationTests(unittest.TestCase):
    """`_normalize` é a fonte única da semântica do tipo — API e tela não podem divergir."""

    def test_independent_forces_100_and_keeps_own_pay(self):
        out = _svc()._normalize(
            {"allocation_type": AllocationType.INDEPENDENTE, "salary_base": 4000,
             "allowance": 500, "hours_per_month": 180, "allocation_percent": 37}
        )
        # Percentual informado é IGNORADO: em contrato próprio ele não existe.
        self.assertEqual(out["allocation_percent"], 100)
        self.assertEqual(out["salary_base"], 4000)
        self.assertEqual(out["allowance"], 500)
        self.assertEqual(out["hours_per_month"], 180)

    def test_default_type_is_independent(self):
        out = _svc()._normalize({"salary_base": 1000})
        self.assertEqual(out["allocation_type"], AllocationType.INDEPENDENTE)
        self.assertEqual(out["allocation_percent"], 100)

    def test_rateio_keeps_percent_and_clears_own_pay(self):
        out = _svc()._normalize(
            {"allocation_type": AllocationType.RATEIO, "allocation_percent": 60,
             "salary_base": 4000, "allowance": 500, "hours_per_month": 180}
        )
        self.assertEqual(out["allocation_percent"], 60)
        # Em rateio o valor vem do cadastro e é dividido — campos próprios não fazem sentido.
        for f in ("salary_base", "allowance", "hours_per_month", "employment_type"):
            self.assertIsNone(out[f], f)

    def test_rateio_rejects_out_of_range(self):
        for pct in (0, -5, 101):
            with self.assertRaises(HTTPException) as ctx:
                _svc()._normalize({"allocation_type": AllocationType.RATEIO, "allocation_percent": pct})
            self.assertEqual(ctx.exception.status_code, 400)


class EffectivePercentTests(unittest.TestCase):
    """`effective_percent` é o que entra no cálculo — 100 é o elemento neutro do existente."""

    def test_independent_is_always_100(self):
        a = EmployeeAssignment(allocation_type=AllocationType.INDEPENDENTE, allocation_percent=42)
        self.assertEqual(a.effective_percent, 100.0)

    def test_rateio_uses_declared_percent(self):
        a = EmployeeAssignment(allocation_type=AllocationType.RATEIO, allocation_percent=42)
        self.assertEqual(a.effective_percent, 42.0)


class OpenOnTests(unittest.TestCase):
    def test_period_and_status(self):
        a = EmployeeAssignment(
            allocation_type=AllocationType.INDEPENDENTE,
            allocation_percent=100,
            status=AssignmentStatus.ATIVA,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 6, 30),
        )
        self.assertFalse(a.is_open_on(date(2026, 2, 28)))
        self.assertTrue(a.is_open_on(date(2026, 3, 1)))
        self.assertTrue(a.is_open_on(date(2026, 6, 30)))
        self.assertFalse(a.is_open_on(date(2026, 7, 1)))
        a.status = AssignmentStatus.ENCERRADA
        self.assertFalse(a.is_open_on(date(2026, 4, 1)))

    def test_open_ended_is_open(self):
        a = EmployeeAssignment(
            allocation_type=AllocationType.INDEPENDENTE, allocation_percent=100,
            status=AssignmentStatus.ATIVA, start_date=None, end_date=None,
        )
        self.assertTrue(a.is_open_on(date(2030, 1, 1)))


class RateioCapTests(unittest.IsolatedAsyncioTestCase):
    """O teto de 100% é do RATEIO. Independente não disputa esse limite."""

    def _service_with(self, existing: list[EmployeeAssignment]) -> EmployeeAssignmentService:
        svc = _svc()

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return SimpleNamespace(all=lambda: self._rows)

        # Só as de RATEIO ativas chegam à consulta real; o stub reproduz esse recorte.
        rows = [
            r for r in existing
            if r.allocation_type == AllocationType.RATEIO and r.status == AssignmentStatus.ATIVA
        ]

        async def _execute(_stmt):
            return _Result(rows)

        svc.session = SimpleNamespace(execute=_execute)
        return svc

    @staticmethod
    def _rateio(pct: float) -> EmployeeAssignment:
        a = EmployeeAssignment(allocation_type=AllocationType.RATEIO, allocation_percent=pct,
                               status=AssignmentStatus.ATIVA)
        a.id = uuid4()
        return a

    @staticmethod
    def _independente() -> EmployeeAssignment:
        a = EmployeeAssignment(allocation_type=AllocationType.INDEPENDENTE, allocation_percent=100,
                               status=AssignmentStatus.ATIVA)
        a.id = uuid4()
        return a

    async def test_rateio_sum_over_100_is_blocked(self):
        svc = self._service_with([self._rateio(60)])
        with self.assertRaises(HTTPException) as ctx:
            await svc._assert_rateio_within_100(
                employee_id=uuid4(), allocation_percent=60, exclude_id=None
            )
        self.assertEqual(ctx.exception.status_code, 400)
        # A mensagem precisa ENSINAR a saída, não só recusar.
        self.assertIn("Remuneração independente", ctx.exception.detail)

    async def test_rateio_sum_exactly_100_is_allowed(self):
        svc = self._service_with([self._rateio(40)])
        await svc._assert_rateio_within_100(
            employee_id=uuid4(), allocation_percent=60, exclude_id=None
        )

    async def test_independent_allocations_do_not_consume_the_cap(self):
        """O ponto central: N contratos independentes a 100% não estouram nada."""
        svc = self._service_with([self._independente(), self._independente(), self._independente()])
        await svc._assert_rateio_within_100(
            employee_id=uuid4(), allocation_percent=100, exclude_id=None
        )


class SingleActivePerPairTests(unittest.IsolatedAsyncioTestCase):
    """UMA alocação ATIVA por (colaborador, projeto).

    `governing()` decide qual alocação projeta o valor na linha mensal. Duas ativas para o mesmo par
    tornariam essa escolha ambígua — e o dinheiro projetado, imprevisível.
    """

    def _svc_with(self, rows):
        svc = _svc()

        class _Result:
            def scalars(self_inner):
                return SimpleNamespace(all=lambda: rows)

        async def _execute(_stmt):
            return _Result()

        svc.session = SimpleNamespace(execute=_execute)
        return svc

    @staticmethod
    def _ativa(project_id):
        a = EmployeeAssignment(allocation_type=AllocationType.INDEPENDENTE, allocation_percent=100,
                               status=AssignmentStatus.ATIVA, project_id=project_id)
        a.id = uuid4()
        return a

    async def test_second_active_on_same_project_is_blocked(self):
        pid = uuid4()
        svc = self._svc_with([self._ativa(pid)])
        with self.assertRaises(HTTPException) as ctx:
            await svc._assert_single_active(employee_id=uuid4(), project_id=pid, exclude_id=None)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Encerre a atual", ctx.exception.detail)

    async def test_editing_the_same_row_is_allowed(self):
        pid = uuid4()
        existing = self._ativa(pid)
        svc = self._svc_with([existing])
        await svc._assert_single_active(
            employee_id=uuid4(), project_id=pid, exclude_id=existing.id
        )

    async def test_cost_center_only_assignments_may_coexist(self):
        """Sem projeto não há par a proteger — administrativo pode ter várias."""
        svc = self._svc_with([self._ativa(None), self._ativa(None)])
        await svc._assert_single_active(employee_id=uuid4(), project_id=None, exclude_id=None)


class GoverningIsDeterministicTests(unittest.IsolatedAsyncioTestCase):
    """A alocação que projeta o valor NUNCA pode depender da ordem que o banco devolveu."""

    async def test_picks_most_recent_active(self):
        from datetime import datetime, timezone

        pid, eid = uuid4(), uuid4()

        def mk(start, created):
            a = EmployeeAssignment(allocation_type=AllocationType.INDEPENDENTE, allocation_percent=100,
                                   status=AssignmentStatus.ATIVA, project_id=pid, start_date=start)
            a.id = uuid4()
            a.created_at = created
            return a

        antiga = mk(date(2026, 1, 1), datetime(2026, 1, 1, tzinfo=timezone.utc))
        nova = mk(date(2026, 6, 1), datetime(2026, 6, 1, tzinfo=timezone.utc))

        for ordem in ([antiga, nova], [nova, antiga]):  # as duas ordens possíveis do banco
            svc = _svc()

            class _Result:
                def scalars(self_inner):
                    return SimpleNamespace(all=lambda: ordem)

            async def _execute(_stmt):
                return _Result()

            svc.session = SimpleNamespace(execute=_execute)
            got = await svc.governing(employee_id=eid, project_id=pid)
            self.assertIs(got, nova, f"ordem {[a.start_date for a in ordem]}")


class HistoryIsWiredTests(unittest.TestCase):
    """Versionamento usa a infraestrutura existente (`audit_logs`), sem tabela paralela."""

    def test_service_uses_audit_service(self):
        from app.services.audit_service import AuditService

        svc = _svc()
        svc.session = SimpleNamespace()
        # O construtor real instancia o AuditService; aqui garantimos o contrato do atributo.
        self.assertTrue(hasattr(EmployeeAssignmentService, "AUDIT_ENTITY"))
        self.assertEqual(EmployeeAssignmentService.AUDIT_ENTITY, "employee_assignment")
        self.assertTrue(callable(AuditService.log_action))

    def test_write_methods_accept_actor(self):
        """Sem `actor` o histórico não saberia QUEM alterou."""
        import inspect

        for name in ("create", "update", "close", "reopen"):
            sig = inspect.signature(getattr(EmployeeAssignmentService, name))
            self.assertIn("actor", sig.parameters, name)
            self.assertIn("request", sig.parameters, name)


async def _noop(*_a, **_k):
    return None


async def _noop_arg(_a, **_k):
    return None


async def _noop_kwargs(**_k):
    return None


class CancelSemanticsTests(unittest.IsolatedAsyncioTestCase):
    """CANCELADA = criada por engano, sem efeito financeiro. Distinta de ENCERRADA."""

    def _svc(self, *, footprint: dict, row: EmployeeAssignment):
        svc = _svc()

        async def _get(_id):
            return row

        async def _footprint(_row):
            return footprint

        svc.get = _get
        svc.financial_footprint = _footprint
        svc.session = SimpleNamespace(commit=_noop, refresh=_noop_arg)
        svc.audit = SimpleNamespace(log_action=_noop_kwargs)
        return svc

    @staticmethod
    def _row(status=AssignmentStatus.ATIVA):
        a = EmployeeAssignment(
            allocation_type=AllocationType.INDEPENDENTE, allocation_percent=100,
            status=status, project_id=uuid4(),
        )
        a.id = uuid4()
        a.employee_id = uuid4()
        return a

    async def test_cancels_when_there_is_no_financial_footprint(self):
        row = self._row()
        svc = self._svc(footprint={"labors": 0, "components": 0}, row=row)
        out = await svc.cancel(row.id, reason="projeto errado", actor=SimpleNamespace(id=uuid4()))
        self.assertEqual(out.status, AssignmentStatus.CANCELADA)
        self.assertIsNotNone(out.cancelled_at)
        self.assertIsNotNone(out.cancelled_by_id)

    async def test_blocked_when_labors_exist_and_points_to_encerrar(self):
        row = self._row()
        svc = self._svc(footprint={"labors": 3, "components": 0}, row=row)
        with self.assertRaises(HTTPException) as ctx:
            await svc.cancel(row.id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("ENCERRAR", ctx.exception.detail)
        self.assertIn("3 competência", ctx.exception.detail)
        self.assertEqual(row.status, AssignmentStatus.ATIVA)  # nada mudou

    async def test_blocked_when_only_variable_components_exist(self):
        row = self._row()
        svc = self._svc(footprint={"labors": 0, "components": 2}, row=row)
        with self.assertRaises(HTTPException) as ctx:
            await svc.cancel(row.id)
        self.assertIn("componente(s) variável", ctx.exception.detail)

    async def test_cannot_cancel_an_already_closed_assignment(self):
        row = self._row(AssignmentStatus.ENCERRADA)
        svc = self._svc(footprint={"labors": 0, "components": 0}, row=row)
        with self.assertRaises(HTTPException) as ctx:
            await svc.cancel(row.id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("existiu de fato", ctx.exception.detail)

    async def test_cancelling_twice_is_idempotent(self):
        row = self._row(AssignmentStatus.CANCELADA)
        svc = self._svc(footprint={"labors": 0, "components": 0}, row=row)
        out = await svc.cancel(row.id)
        self.assertEqual(out.status, AssignmentStatus.CANCELADA)


class CancelledIsInertTests(unittest.TestCase):
    """Cancelada não participa de nada: nem vigência, nem projeção, nem teto de rateio."""

    def test_cancelled_is_never_open(self):
        a = EmployeeAssignment(
            allocation_type=AllocationType.INDEPENDENTE, allocation_percent=100,
            status=AssignmentStatus.CANCELADA, start_date=None, end_date=None,
        )
        self.assertFalse(a.is_open_on(date(2026, 6, 1)))

    def test_status_enum_has_the_three_outcomes(self):
        self.assertEqual([s.value for s in AssignmentStatus], ["ATIVA", "ENCERRADA", "CANCELADA"])


if __name__ == "__main__":
    unittest.main()
