import { useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { Field } from "../components/Field";
import { useAdminAuth } from "./AdminAuth";

export function AdminLoginPage() {
  const { state, login } = useAdminAuth();
  const [params] = useSearchParams();
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const next = params.get("next");
  if (state.status === "authenticated") return <Navigate to={next?.startsWith("/adminuser") ? next : "/adminuser"} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!loginName.trim() || !password) {
      setError("Введите логин и пароль");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await login(loginName.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось войти");
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-main adm-login">
      <div className="auth-card">
        <div className="brand adm-login-brand">
          <span className="brand-mark" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round">
              <path d="M4 18 12 6l8 12" />
            </svg>
          </span>
          Вход для сотрудников
        </div>
        <p className="auth-sub">Только учётные записи сотрудников. Клиентский вход здесь не работает.</p>
        <form onSubmit={onSubmit} noValidate>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <div className="fields">
            <Field label="Логин" required autoComplete="username" value={loginName} onChange={setLoginName} />
            <Field label="Пароль" required type="password" autoComplete="current-password" value={password} onChange={setPassword} />
          </div>
          <button type="submit" className="btn btn-accent btn-lg btn-block" style={{ marginTop: 28 }} disabled={submitting}>
            {submitting ? "Входим…" : "Войти"}
          </button>
        </form>
        <p className="auth-foot">5 неверных попыток за минуту — пауза. Входы пишутся в audit_log.</p>
      </div>
    </main>
  );
}
