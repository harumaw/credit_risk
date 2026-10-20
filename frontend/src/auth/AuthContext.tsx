import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { fetchMe, login as loginRequest, type UserProfile } from "../api/auth";

const TOKEN_KEY = "credit_token";

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // приватный режим / запрет хранилища — сессия просто не переживёт перезагрузку
  }
}

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; token: string; user: UserProfile };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => (readToken() ? { status: "loading" } : { status: "anonymous" }));

  const logout = useCallback(() => {
    writeToken(null);
    setState({ status: "anonymous" });
  }, []);

  // Восстановление сессии по сохранённому токену
  useEffect(() => {
    const token = readToken();
    if (!token) return;
    let cancelled = false;
    fetchMe(token)
      .then((user) => !cancelled && setState({ status: "authenticated", token, user }))
      // Токен протух, пользователя нет или сервер недоступен — показываем вход, а не вечную загрузку
      .catch(() => !cancelled && logout());
    return () => {
      cancelled = true;
    };
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const token = await loginRequest(email, password);
    const user = await fetchMe(token);
    writeToken(token);
    setState({ status: "authenticated", token, user });
  }, []);

  const value = useMemo(() => ({ state, login, logout }), [state, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth вне AuthProvider");
  return ctx;
}
