import type { ReactNode } from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

function Loading() {
  return <div className="screen-center">Загрузка…</div>;
}

/** Куда вернуть после входа: только путь внутри сайта, иначе null. */
export function safeNext(next: string | null): string | null {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

/** Ссылка на вход/регистрацию с тем же ?next=, что у текущей страницы. */
export function useAuthLink(path: "/login" | "/register"): string {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  return next ? `${path}?next=${encodeURIComponent(next)}` : path;
}

/** Страницы кабинета: без входа — на /login, после входа — обратно сюда. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const { pathname, search } = useLocation();
  if (state.status === "loading") return <Loading />;
  if (state.status === "anonymous")
    return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  return <>{children}</>;
}

/** Вход и регистрация: уже вошедшего — на ?next= или в кабинет. */
export function GuestOnly({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const [params] = useSearchParams();
  if (state.status === "loading") return <Loading />;
  if (state.status === "authenticated") return <Navigate to={safeNext(params.get("next")) ?? "/cabinet"} replace />;
  return <>{children}</>;
}
