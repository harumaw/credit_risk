import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { register, type RegisterPayload } from "../api/auth";
import { ApiError, type FieldErrors } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthLayout } from "../components/AuthLayout";
import { Field } from "../components/Field";
import { validateRegistration } from "../lib/validation";

interface FormState {
  last_name: string;
  first_name: string;
  middle_name: string;
  inn_fl: string;
  phone: string;
  email: string;
  password: string;
}

const EMPTY: FormState = {
  last_name: "",
  first_name: "",
  middle_name: "",
  inn_fl: "",
  phone: "",
  email: "",
  password: "",
};

function toPayload(form: FormState): RegisterPayload {
  return {
    last_name: form.last_name.trim(),
    first_name: form.first_name.trim(),
    middle_name: form.middle_name.trim() || null,
    inn_fl: form.inn_fl.trim(),
    phone: form.phone.trim() || null,
    email: form.email.trim(),
    password: form.password,
  };
}

export function RegisterPage() {
  const { login } = useAuth();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const set = (key: keyof FormState) => (value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => ({ ...prev, [key]: "" }));
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const payload = toPayload(form);
    const errors = validateRegistration(payload);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      setError(null);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await register(payload);
      await login(payload.email, payload.password);
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        setError(Object.keys(err.fieldErrors).length > 0 ? null : err.message);
      } else {
        setError("Не удалось зарегистрироваться");
      }
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      wide
      title="Регистрация"
      subtitle="Ваши ИП и компании найдём по ИНН"
      footer={
        <>
          <p className="required-legend">
            <span className="req-dot" aria-hidden="true" />— обязательное поле
          </p>
          <p className="auth-foot">
            Уже есть аккаунт? <Link to="/login">Войдите</Link>
          </p>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <div className="fields">
          <div className="field-row">
            <Field
              label="Фамилия"
              required
              autoComplete="family-name"
              maxLength={100}
              value={form.last_name}
              onChange={set("last_name")}
              error={fieldErrors.last_name}
            />
            <Field
              label="Имя"
              required
              autoComplete="given-name"
              maxLength={100}
              value={form.first_name}
              onChange={set("first_name")}
              error={fieldErrors.first_name}
            />
          </div>
          <Field
            label="Отчество"
            optionalNote="если есть"
            autoComplete="additional-name"
            maxLength={100}
            value={form.middle_name}
            onChange={set("middle_name")}
            error={fieldErrors.middle_name}
          />
          <Field
            label="ИНН физлица"
            required
            inputMode="numeric"
            placeholder="12 цифр"
            maxLength={12}
            value={form.inn_fl}
            onChange={(v) => set("inn_fl")(v.replace(/\D/g, ""))}
            hint="По ИНН мы найдём ваши ИП и компании"
            error={fieldErrors.inn_fl}
          />
          <Field
            label="Телефон"
            optionalNote="необязательно"
            type="tel"
            autoComplete="tel"
            placeholder="+7 900 123-45-67"
            value={form.phone}
            onChange={set("phone")}
            error={fieldErrors.phone}
          />
          <Field
            label="Email"
            required
            type="email"
            autoComplete="email"
            value={form.email}
            onChange={set("email")}
            error={fieldErrors.email}
          />
          <Field
            label="Пароль"
            required
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={set("password")}
            hint="Минимум 8 символов"
            error={fieldErrors.password}
          />
        </div>
        <button type="submit" className="btn btn-accent btn-lg btn-block" style={{ marginTop: 28 }} disabled={submitting}>
          {submitting ? "Создаём аккаунт…" : "Создать аккаунт"}
        </button>
      </form>
    </AuthLayout>
  );
}
