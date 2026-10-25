import type { ReactNode } from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

function Loading() {
  return <div className="screen-center">Загрузка…</div>;
}

/** Куда вернуть после входа: только путь внутри сайта, иначе null.
 *  Разбираем как браузер: он меняет «\» на «/» и выкидывает TAB/LF, так «/\evil.com» — уже чужой сайт. */
export function safeNext(next: string | null): string | null {
  if (!next?.startsWith("/")) return null;
  try {
    const url = new URL(next, window.location.origin);
    // «/.//evil.com» после разбора — путь «//evil.com», а это уже чужой сайт
    const ours = url.origin === window.location.origin && !url.pathname.startsWith("//");
    return ours ? url.pathname + url.search + url.hash : null;
  } catch {
    return null;
  }
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
