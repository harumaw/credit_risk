import { useState } from "react";

import { cancelApplication, type ApplicationDetails } from "../../api/cabinet";
import { ApiError } from "../../api/client";

interface Props {
  app: ApplicationDetails;
  onDone: () => void;
  /** Текст ссылки, вопрос подтверждения и кнопка «да» */
  label: string;
  question: string;
  confirm: string;
}

/** Ссылка «отозвать / отказаться» с подтверждением → POST /applications/{id}/cancel. */
export function CancelApplication({ app, onDone, label, question, confirm }: Props) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onCancel() {
    setBusy(true);
    setError(null);
    try {
      await cancelApplication(app.id);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось — попробуйте ещё раз");
      setBusy(false);
    }
  }

  if (!asking)
    return (
      <button type="button" className="text-link app-cancel" onClick={() => setAsking(true)}>
        {label}
      </button>
    );
  return (
    <div className="app-confirm" role="group" aria-label={label}>
      <p>{question}</p>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      <div className="btn-row">
        <button type="button" className="btn btn-dark" onClick={onCancel} disabled={busy}>
          {busy ? "Закрываем…" : confirm}
        </button>
        <button type="button" className="btn btn-white" onClick={() => setAsking(false)} disabled={busy}>
          Нет
        </button>
      </div>
    </div>
  );
}
