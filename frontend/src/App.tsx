import { Navigate, Route, Routes } from "react-router-dom";

import { GuestOnly, RequireAuth } from "./components/RouteGuards";
import { ThemeToggle } from "./components/ThemeToggle";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";

export function App() {
  return (
    <>
      <ThemeToggle />
      <Routes>
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
        <Route path="*" element={<Navigate to="/profile" replace />} />
      </Routes>
    </>
  );
}
