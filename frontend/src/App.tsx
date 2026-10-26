import { useEffect } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { AdminAnalysisPage } from "./admin/AdminAnalysisPage";
import { AdminApplicationPage } from "./admin/AdminApplicationPage";
import { AdminApplicationsPage } from "./admin/AdminApplicationsPage";
import { AdminAuthProvider, RequireAdmin } from "./admin/AdminAuth";
import { AdminCompaniesPage } from "./admin/AdminCompaniesPage";
import { AdminCompanyPage } from "./admin/AdminCompanyPage";
import { AdminLoginPage } from "./admin/AdminLoginPage";
import { AdminModelsPage } from "./admin/AdminModelsPage";
import { CompanyProvider } from "./cabinet/CompanyContext";
import { GuestOnly, RequireAuth } from "./components/RouteGuards";
import { AddCompanyPage } from "./pages/cabinet/AddCompanyPage";
import { ApplicationDecisionPage } from "./pages/cabinet/ApplicationDecisionPage";
import { ApplicationFormPage } from "./pages/cabinet/ApplicationFormPage";
import { ApplicationPage } from "./pages/cabinet/ApplicationPage";
import { ApplicationSignPage } from "./pages/cabinet/ApplicationSignPage";
import { ApplicationsPage } from "./pages/cabinet/ApplicationsPage";
import { CabinetHomePage } from "./pages/cabinet/CabinetHomePage";
import { CompaniesSummaryPage } from "./pages/cabinet/CompaniesSummaryPage";
import { CompanyPage } from "./pages/cabinet/CompanyPage";
import { CalculatorPage } from "./pages/CalculatorPage";
import { CreditsPage } from "./pages/CreditsPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";

/** Переход на /#how прокручивает к секции; на новую страницу — наверх. */
function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
    else window.scrollTo(0, 0);
  }, [pathname, hash]);
  return null;
}

export function App() {
  return (
    <>
      <ScrollManager />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/credits" element={<CreditsPage />} />
        <Route path="/calculator" element={<CalculatorPage />} />
        <Route
          path="/login"
          element={
            <GuestOnly>
              <LoginPage />
            </GuestOnly>
          }
        />
        <Route
          path="/register"
          element={
            <GuestOnly>
              <RegisterPage />
            </GuestOnly>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <ProfilePage />
            </RequireAuth>
          }
        />
        <Route
          path="/cabinet"
          element={
            <RequireAuth>
              <CompanyProvider>
                <Outlet />
              </CompanyProvider>
            </RequireAuth>
          }
        >
          <Route index element={<CabinetHomePage />} />
          <Route path="companies" element={<CompaniesSummaryPage />} />
          <Route path="companies/new" element={<AddCompanyPage />} />
          <Route path="companies/:id" element={<CompanyPage />} />
          <Route path="applications" element={<ApplicationsPage />} />
          <Route path="applications/new" element={<ApplicationFormPage />} />
          <Route path="applications/:id" element={<ApplicationPage />} />
          <Route path="applications/:id/decision" element={<ApplicationDecisionPage />} />
          <Route path="applications/:id/sign" element={<ApplicationSignPage />} />
        </Route>
        <Route
          path="/adminuser"
          element={
            <AdminAuthProvider>
              <Outlet />
            </AdminAuthProvider>
          }
        >
          <Route path="login" element={<AdminLoginPage />} />
          <Route
            element={
              <RequireAdmin>
                <Outlet />
              </RequireAdmin>
            }
          >
            <Route index element={<AdminCompaniesPage />} />
            <Route path="companies/:id" element={<AdminCompanyPage />} />
            <Route path="applications" element={<AdminApplicationsPage />} />
            <Route path="applications/:id" element={<AdminApplicationPage />} />
            <Route path="models" element={<AdminModelsPage />} />
            <Route path="analysis" element={<AdminAnalysisPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
