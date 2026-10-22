import { useEffect } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { CompanyProvider } from "./cabinet/CompanyContext";
import { GuestOnly, RequireAuth } from "./components/RouteGuards";
import { AddCompanyPage } from "./pages/cabinet/AddCompanyPage";
import { ApplicationFormPage } from "./pages/cabinet/ApplicationFormPage";
import { ApplicationPage } from "./pages/cabinet/ApplicationPage";
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
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
