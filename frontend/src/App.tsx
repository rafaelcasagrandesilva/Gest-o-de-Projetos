import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Dashboard } from "@/pages/Dashboard";
import { Employees } from "@/pages/Employees";
import { Vehicles } from "@/pages/Vehicles";
import { Login } from "@/pages/Login";
import { ProjectDetail } from "@/pages/ProjectDetail";
import { Projects } from "@/pages/Projects";
import { Settings } from "@/pages/Settings";
import { Invoices } from "@/pages/Invoices";
import { CompanyDebt } from "@/pages/CompanyDebt";
import { CompanyFixedCosts } from "@/pages/CompanyFixedCosts";
import { RevenuePage } from "@/pages/Revenue";
import { Reports } from "@/pages/Reports";
import { Users } from "@/pages/Users";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
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
            <Route index element={<Dashboard />} />
            <Route path="projects" element={<Projects />} />
            <Route path="projects/:projectId" element={<ProjectDetail />} />
            <Route path="reports" element={<Reports />} />
            <Route path="settings" element={<Settings />} />
            <Route path="users" element={<Users />} />
            <Route path="employees" element={<Employees />} />
            <Route path="vehicles" element={<Vehicles />} />
            <Route path="revenue" element={<RevenuePage />} />
            <Route path="invoices" element={<Invoices />} />
            <Route path="company-debt" element={<CompanyDebt />} />
            <Route path="company-fixed-costs" element={<CompanyFixedCosts />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
