import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { adminLogin, adminMe, readAdminToken, writeAdminToken, type Staff } from "../api/admin";

type State = { status: "loading" } | { status: "anonymous" } | { status: "authenticated"; staff: Staff };

interface Value {
  state: State;
  login: (login: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<Value | null>(null);

/** Вход сотрудника — отдельно от клиентского (свой токен, свой эндпоинт). */
export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(() => (readAdminToken() ? { status: "loading" } : { status: "anonymous" }));

  const logout = useCallback(() => {
    writeAdminToken(null);
    setState({ status: "anonymous" });
  }, []);

  useEffect(() => {
    const token = readAdminToken();
    if (token) {
      adminMe(token).then(
        (staff) => setState({ status: "authenticated", staff }),
        () => logout(),
      );
    }
    // API ответил 401 на любом запросе — токен протух
    window.addEventListener("admin-logout", logout);
    return () => window.removeEventListener("admin-logout", logout);
  }, [logout]);

  const login = useCallback(async (loginName: string, password: string) => {
    const { token, staff } = await adminLogin(loginName, password);
    writeAdminToken(token);
    setState({ status: "authenticated", staff });
  }, []);

  const value = useMemo(() => ({ state, login, logout }), [state, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAdminAuth(): Value {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAdminAuth вне AdminAuthProvider");
  return v;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { state } = useAdminAuth();
  const { pathname, search } = useLocation();
  if (state.status === "loading") return <div className="screen-center">Загрузка…</div>;
  if (state.status === "anonymous")
    return <Navigate to={`/adminuser/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  return <>{children}</>;
}
