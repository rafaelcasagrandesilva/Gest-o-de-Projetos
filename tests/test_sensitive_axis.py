"""Eixo de dados sensíveis: o backend OMITE os campos financeiros de quem não tem `<recurso>.sensitive`.

Testa o helper `redact` (omissão real no payload) e a autorização: `<r>.read` sozinho NÃO concede
`<r>.sensitive`; o legado `<r>.view` concede (compatibilidade).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.api.deps import user_has_permission
from app.api.sensitive import EMPLOYEE_SENSITIVE_FIELDS, VEHICLE_SENSITIVE_FIELDS, redact
from app.core import permission_codes as pc
from app.schemas.employees import EmployeeRead
from app.schemas.fleet import VehicleRead


def _user(*perms: str) -> SimpleNamespace:
    ups = [SimpleNamespace(permission=SimpleNamespace(name=p), granted=True) for p in perms]
    return SimpleNamespace(email="s@example.com", user_permissions=ups, roles=[], is_active=True)


class SensitiveOmissionTests(unittest.TestCase):
    def _emp(self) -> EmployeeRead:
        from datetime import date, datetime

        return EmployeeRead(
            id="00000000-0000-0000-0000-000000000001",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            full_name="Fulano",
            employment_type="CLT",
            salary_base=5000.0,
            additional_costs=100.0,
            total_cost=6000.0,
            is_active=True,
            start_date=date(2026, 1, 1),
        )

    def test_redact_omits_when_excluded(self):
        r = redact(self._emp(), EMPLOYEE_SENSITIVE_FIELDS, include=False)
        self.assertIsNone(r.salary_base)
        self.assertIsNone(r.additional_costs)
        self.assertIsNone(r.total_cost)
        self.assertEqual(r.full_name, "Fulano")  # campo não-sensível preservado

    def test_redact_keeps_when_included(self):
        r = redact(self._emp(), EMPLOYEE_SENSITIVE_FIELDS, include=True)
        self.assertEqual(r.salary_base, 5000.0)
        self.assertEqual(r.total_cost, 6000.0)

    def test_vehicle_monthly_cost_omitted(self):
        from datetime import datetime

        v = VehicleRead(
            id="00000000-0000-0000-0000-000000000002",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            plate="ABC1D23",
            vehicle_type="LIGHT",
            monthly_cost=1200.0,
            is_active=True,
        )
        self.assertIsNone(redact(v, VEHICLE_SENSITIVE_FIELDS, include=False).monthly_cost)
        self.assertEqual(redact(v, VEHICLE_SENSITIVE_FIELDS, include=True).monthly_cost, 1200.0)

    def test_read_does_not_grant_sensitive_but_view_does(self):
        # Quem só LÊ não recebe sensível; o legado view concede (compatibilidade).
        self.assertFalse(user_has_permission(_user(pc.EMPLOYEES_LIST, pc.EMPLOYEES_READ), pc.EMPLOYEES_SENSITIVE))
        self.assertTrue(user_has_permission(_user(pc.EMPLOYEES_VIEW), pc.EMPLOYEES_SENSITIVE))
        self.assertFalse(user_has_permission(_user(pc.VEHICLES_READ), pc.VEHICLES_SENSITIVE))
        self.assertTrue(user_has_permission(_user(pc.VEHICLES_VIEW), pc.VEHICLES_SENSITIVE))


if __name__ == "__main__":
    unittest.main()
