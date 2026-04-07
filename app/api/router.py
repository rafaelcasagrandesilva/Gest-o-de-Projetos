from __future__ import annotations

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.employees.router import router as employees_router
from app.modules.financial.router import router as financial_router
from app.modules.fleet.router import router as fleet_router
from app.modules.hr.router import router as hr_router
from app.modules.project_structure.router import router as project_structure_router
from app.modules.projects.router import router as projects_router
from app.modules.settings.router import router as settings_router
from app.modules.users.router import router as users_router
from app.modules.alerts.router import router as alerts_router
from app.modules.costs.router import router as costs_router
from app.modules.company_finance.router import router as company_finance_router
from app.modules.receivables.router import invoices_router, payments_router
from app.modules.reports.router import router as reports_router
from app.modules.admin.router import router as admin_router


api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])

protected = APIRouter()
protected.include_router(users_router, prefix="/users", tags=["users"])
protected.include_router(projects_router, prefix="/projects", tags=["projects"])
protected.include_router(project_structure_router, prefix="/projects", tags=["project-structure"])
protected.include_router(settings_router, prefix="/settings", tags=["settings"])
protected.include_router(employees_router, prefix="/employees", tags=["employees"])
protected.include_router(hr_router, prefix="/hr", tags=["hr"])
protected.include_router(fleet_router, prefix="/vehicles", tags=["vehicles"])
protected.include_router(financial_router, prefix="/financial", tags=["financial"])
protected.include_router(costs_router, prefix="/costs", tags=["costs"])
protected.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
protected.include_router(alerts_router, prefix="/alerts", tags=["alerts"])
protected.include_router(company_finance_router, prefix="/company-finance", tags=["company-finance"])
protected.include_router(invoices_router, prefix="/invoices", tags=["accounts-receivable"])
protected.include_router(payments_router, prefix="/payments", tags=["accounts-receivable"])
protected.include_router(reports_router, prefix="/reports")

api_router.include_router(protected)
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
