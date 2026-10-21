import { useId, useState, type InputHTMLAttributes, type ReactNode } from "react";

import { EyeIcon, EyeOffIcon } from "./Icons";

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "required"> {
  label: string;
  /** Обязательное поле: красная точка у подписи */
  required?: boolean;
  /** Подпись для необязательного поля: «если есть», «необязательно» */
  optionalNote?: string;
  hint?: ReactNode;
  error?: string;
  onChange: (value: string) => void;
}

export function Field({ label, required, optionalNote, hint, error, onChange, ...input }: FieldProps) {
  const id = useId();
  const [shown, setShown] = useState(false);
  const isPassword = input.type === "password";
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  const control = (
    <input
      id={id}
      aria-required={required || undefined}
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy}
      onChange={(e) => onChange(e.target.value)}
      {...input}
      type={isPassword && shown ? "text" : input.type}
    />
  );
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required && <span className="req-dot" aria-label="обязательное поле" role="img" />}
        {!required && optionalNote && <span className="optional">{optionalNote}</span>}
      </label>
      {isPassword ? (
        // Пароль можно показать: так проще проверить, что введено, особенно с телефона
        <div className="password-wrap">
          {control}
          <button
            type="button"
            className="password-toggle"
            aria-label={shown ? "Скрыть пароль" : "Показать пароль"}
            aria-pressed={shown}
            aria-controls={id}
            onClick={() => setShown((v) => !v)}
          >
            {shown ? <EyeOffIcon size={20} /> : <EyeIcon size={20} />}
          </button>
        </div>
      ) : (
        control
      )}
      {error ? (
        <div className="error" id={`${id}-error`}>
          {error}
        </div>
      ) : (
        hint && (
          <div className="hint" id={`${id}-hint`}>
            {hint}
          </div>
        )
      )}
    </div>
  );
}
