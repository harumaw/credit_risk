import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthLayout } from "../components/AuthLayout";
import { Field } from "../components/Field";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Введите email и пароль");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      // GuestOnly сам переведёт в кабинет, когда состояние станет authenticated
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось войти");
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      footer={
        <>
          Нет аккаунта? <Link to="/register">Зарегистрируйтесь</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <Field label="Email" type="email" autoComplete="username" value={email} onChange={setEmail} />
        <Field
          label="Пароль"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
        />
        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? "Входим…" : "Войти"}
        </button>
      </form>
    </AuthLayout>
  );
}
