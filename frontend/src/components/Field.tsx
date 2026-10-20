import { useId, type InputHTMLAttributes, type ReactNode } from "react";

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
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required && <span className="req-dot" aria-label="обязательное поле" role="img" />}
        {!required && optionalNote && <span className="optional">{optionalNote}</span>}
      </label>
      <input
        id={id}
        aria-required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        onChange={(e) => onChange(e.target.value)}
        {...input}
      />
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
