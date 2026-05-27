import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { useAuth } from "@/context/AuthContext";
import { WorkspaceProvider, useWorkspace } from "@/context/WorkspaceContext";
import { Layout } from "@/components/Layout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { hasPermission } from "@/permissions";
import { Dashboard } from "@/pages/Dashboard";
import { Employees } from "@/pages/Employees";
import { Vehicles } from "@/pages/Vehicles";
import { Login } from "@/pages/Login";
import { ProjectDetail } from "@/pages/ProjectDetail";
import { Projects } from "@/pages/Projects";
import { Settings } from "@/pages/Settings";
import { Invoices } from "@/pages/Invoices";
import { AdvanceBatches } from "@/pages/AdvanceBatches";
import { CompanyDebt } from "@/pages/CompanyDebt";
import { CompanyFixedCosts } from "@/pages/CompanyFixedCosts";
import { FinancialDashboard } from "@/pages/FinancialDashboard";
import { Payables } from "@/pages/Payables";
import { Receivables } from "@/pages/Receivables";
import { RevenuePage } from "@/pages/Revenue";
import { Reports } from "@/pages/Reports";
import { Users } from "@/pages/Users";
import { Assets } from "@/pages/Assets";
import { AssetsDashboard } from "@/pages/AssetsDashboard";
import { AssetDetailPage } from "@/pages/AssetDetail";
import { Epis } from "@/pages/Epis";

function LegacyProjectDetailRedirect() {
  const { projectId } = useParams();
  return <Navigate to={`/projects/list/${projectId ?? ""}`} replace />;
}

function WorkspaceNotFoundRedirect() {
  const { workspace } = useWorkspace();
  const target =
    workspace === "projects"
      ? "/projects/dashboard"
      : workspace === "assets"
        ? "/assets/dashboard"
        : "/finance/dashboard";
  return <Navigate to={target} replace />;
}

function WorkspaceSessionSync() {
  const { user } = useAuth();
  const { workspace, setWorkspace } = useWorkspace();

  useEffect(() => {
    if (!user) return;

    const fallback = user.default_workspace ?? user.current_workspace ?? "projects";
    const canCurrentWorkspace = hasPermission(user.permission_names, `workspace.${workspace}.access`);

    if (!canCurrentWorkspace && workspace !== fallback) {
      setWorkspace(fallback);
    }
  }, [setWorkspace, user, workspace]);

  return null;
}

export default function App() {
  return (
    <AuthProvider>
      <WorkspaceProvider>
        <BrowserRouter>
          <WorkspaceSessionSync />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              {/* Rotas novas (workspaces) */}
              <Route path="projects/dashboard" element={<Dashboard />} />
              <Route path="projects/reports" element={<Reports />} />
              <Route path="projects/list" element={<Projects />} />
              <Route path="projects/list/:projectId" element={<ProjectDetail />} />
              <Route path="projects/users" element={<Users />} />
              <Route path="projects/employees" element={<Employees />} />
              <Route path="projects/vehicles" element={<Vehicles />} />
              <Route path="projects/revenue" element={<RevenuePage />} />

              <Route path="finance/dashboard" element={<FinancialDashboard />} />
              <Route path="finance/payables" element={<Payables />} />
              <Route path="finance/receivables" element={<Receivables />} />
              <Route path="finance/invoices" element={<Invoices />} />
              <Route path="finance/advance-batches" element={<AdvanceBatches />} />
              <Route path="finance/debt" element={<CompanyDebt />} />
              <Route path="finance/fixed-costs" element={<CompanyFixedCosts />} />
              <Route path="finance/reports" element={<Reports />} />

              <Route path="assets/dashboard" element={<AssetsDashboard />} />
              <Route path="assets" element={<Assets />} />
              <Route path="assets/:assetId" element={<AssetDetailPage />} />
              <Route path="epis" element={<Epis />} />
              <Route path="epis/:assetId" element={<AssetDetailPage />} />

              {/* Compat: rotas antigas (mantidas via redirect) */}
              <Route index element={<WorkspaceNotFoundRedirect />} />
              <Route path="projects" element={<Navigate to="/projects/list" replace />} />
              <Route path="projects/:projectId" element={<LegacyProjectDetailRedirect />} />
              <Route path="reports" element={<Navigate to="/projects/reports" replace />} />
              <Route path="users" element={<Navigate to="/projects/users" replace />} />
              <Route path="employees" element={<Navigate to="/projects/employees" replace />} />
              <Route path="vehicles" element={<Navigate to="/projects/vehicles" replace />} />
              <Route path="revenue" element={<Navigate to="/projects/revenue" replace />} />
              <Route path="invoices" element={<Navigate to="/finance/invoices" replace />} />
              <Route path="company-debt" element={<Navigate to="/finance/debt" replace />} />
              <Route path="company-fixed-costs" element={<Navigate to="/finance/fixed-costs" replace />} />

              {/* Sem workspace (mantém como estava) */}
              <Route path="settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<WorkspaceNotFoundRedirect />} />
          </Routes>
        </BrowserRouter>
      </WorkspaceProvider>
    </AuthProvider>
  );
}
