import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

function Loading() {
  return <div className="screen-center">Загрузка…</div>;
}

/** Страницы кабинета: без входа — на /login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status === "loading") return <Loading />;
  if (state.status === "anonymous") return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/** Вход и регистрация: уже вошедшего — в кабинет. */
export function GuestOnly({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status === "loading") return <Loading />;
  if (state.status === "authenticated") return <Navigate to="/cabinet" replace />;
  return <>{children}</>;
}
