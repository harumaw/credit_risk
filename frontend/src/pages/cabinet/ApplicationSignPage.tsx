import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { requestSignCode, signApplication, type ApplicationDetails, type SignCode } from "../../api/cabinet";
import { ApiError } from "../../api/client";
import { useApplication } from "../../cabinet/useApplication";
import { ApplicationHead } from "../../components/cabinet/ApplicationHead";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { CancelApplication } from "../../components/cabinet/CancelApplication";
import { Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import { SiteFooter } from "../../components/SiteHeader";
import { dayMonthNum, percent, plural, rub, timeHm } from "../../lib/format";

/** Через сколько можно запросить новый код */
const RESEND_MS = 60_000;

const mmss = (ms: number) => {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

function useNow(active: boolean): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function Terms({ app, children }: { app: ApplicationDetails; children?: ReactNode }) {
  const d = app.decision;
  if (!d?.amount || !d.termMonths) return null;
  const overpay = d.monthlyPayment ? d.monthlyPayment * d.termMonths - d.amount : null;
  return (
    <div className="panel-lg">
      <h2>Условия</h2>
      <dl className="facts">
        <dt>Компания</dt>
        <dd>{app.companyName}</dd>
        <dt>Кредит</dt>
        <dd>{app.product}</dd>
        <dt>Сумма</dt>
        <dd>{rub(d.amount)}</dd>
        <dt>Срок</dt>
        <dd>
          {d.termMonths} {plural(d.termMonths, ["месяц", "месяца", "месяцев"])}
        </dd>
        {d.rate !== null && (
          <>
            <dt>Ставка</dt>
            <dd>{percent(d.rate)} годовых</dd>
          </>
        )}
        {d.monthlyPayment !== null && (
          <>
            <dt>Платёж</dt>
            <dd>{rub(d.monthlyPayment)} в месяц</dd>
          </>
        )}
        {overpay !== null && overpay > 0 && (
          <>
            <dt>Переплата</dt>
            <dd>{rub(overpay)}</dd>
          </>
        )}
      </dl>
      {children}
    </div>
  );
}

function SignBox({ app, onSigned }: { app: ApplicationDetails; onSigned: () => void }) {
  const inputId = useId();
  const [code, setCode] = useState<SignCode | null>(null);
  const [requestedAt, setRequestedAt] = useState(0);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const now = useNow(code !== null);
  const expired = code !== null && Date.parse(code.expiresAt) <= now;
  const resendIn = requestedAt + RESEND_MS - now;

  async function getCode() {
    setBusy(true);
    setError(null);
    try {
      setCode(await requestSignCode(app.id));
      setRequestedAt(Date.now());
      setValue("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось получить код");
    } finally {
      setBusy(false);
    }
  }

  async function onSign(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{6}$/.test(value)) {
      setError("Код — 6 цифр");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signApplication(app.id, value);
      onSigned();
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors.code ?? err.message) : "Не удалось подписать");
      setBusy(false);
    }
  }

  if (!code)
    return (
      <div className="app-hero app-hero-dark">
        <span className="app-hero-title">Подпишите договор кодом</span>
        <span className="app-hero-text">Код действует 5 минут. Подпись кодом равна подписи на бумаге.</span>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <button type="button" className="btn btn-accent btn-lg" onClick={getCode} disabled={busy}>
          {busy ? "Отправляем код…" : "Получить код"}
        </button>
      </div>
    );

  return (
    <form className="app-hero app-hero-dark" onSubmit={onSign} noValidate>
      <span className="app-hero-title">Введите код</span>
      <div className="demo-code">
        <span>Демо: в банке код придёт по SMS</span>
        <strong>{code.code}</strong>
      </div>
      <label htmlFor={inputId} className="app-hero-text">
        Код из 6 цифр · действует до {timeHm(code.expiresAt)}
      </label>
      <input
        id={inputId}
        className="code-input"
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${inputId}-err` : undefined}
        onChange={(e) => {
          setValue(e.target.value.replace(/\D/g, "").slice(0, 6));
          setError(null);
        }}
      />
      {error && (
        <div id={`${inputId}-err`} className="code-error" role="alert">
          {error}
        </div>
      )}
      {expired && !error && <div className="code-error">Код истёк — запросите новый</div>}
      <div className="btn-row app-sign-actions">
        <button type="submit" className="btn btn-accent btn-lg" disabled={busy || expired}>
          {busy ? "Подписываем…" : "Подписать"}
        </button>
        {resendIn > 0 && !expired ? (
          <span className="muted-dark">Новый код — через {mmss(resendIn)}</span>
        ) : (
          <button type="button" className="btn btn-white btn-lg" onClick={getCode} disabled={busy}>
            Получить новый код
          </button>
        )}
      </div>
    </form>
  );
}

function Issued({ app }: { app: ApplicationDetails }) {
  const d = app.decision;
  const signed = [...app.history].reverse().find((e) => e.status === "issued") ?? app.history[app.history.length - 1];
  return (
    <div className="app-hero app-hero-ok" aria-live="polite">
      {signed && (
        <span className="app-hero-eyebrow">
          Договор подписан {dayMonthNum(signed.at)} в {timeHm(signed.at)}
        </span>
      )}
      <span className="app-hero-title app-hero-big">{d?.amount ? `${rub(d.amount)} на счёте` : "Деньги на счёте"}</span>
      <span className="app-hero-text">
        {d?.monthlyPayment ? `Первый платёж ${rub(d.monthlyPayment)} — через месяц. ` : ""}Напомним о платеже на главной.
      </span>
      <div className="btn-row">
        <Link to={`/cabinet/companies/${app.companyId}`} className="btn btn-dark btn-lg">
          К компании
        </Link>
        <Link to="/cabinet/applications" className="btn btn-white btn-lg">
          Все заявки
        </Link>
      </div>
    </div>
  );
}

/** Подписание договора кодом → «Кредит выдан». */
export function ApplicationSignPage() {
  const { id = "" } = useParams();
  const data = useApplication(id);
  const app = data.status === "ready" ? data.data : null;
  const base = `/cabinet/applications/${id}`;

  if (app && app.status !== "signing" && app.status !== "issued") {
    // Ещё не приняты условия — на решение; ещё нет решения — на ход заявки
    const decided = app.status === "approved" || app.status === "counter_offer" || app.status === "rejected";
    return <Navigate to={decided ? `${base}/decision` : base} replace />;
  }

  let body;
  if (data.status === "error") body = <SheetStatus error={data.message} onRetry={data.reload} />;
  else if (!app) body = <SheetStatus />;
  else
    body = (
      <div className="app-layout">
        <Terms app={app}>
          {app.status === "signing" && (
            <CancelApplication
              app={app}
              onDone={data.reload}
              label="Отказаться от кредита"
              question="Отказаться от кредита? Заявка закроется, условия перестанут действовать — вернуть её будет нельзя."
              confirm="Да, отказаться"
            />
          )}
        </Terms>
        {app.status === "issued" ? <Issued app={app} /> : <SignBox app={app} onSigned={data.reload} />}
      </div>
    );

  return (
    <>
      <CabinetHeader />
      <ApplicationHead
        back={{ to: base, label: app ? `Заявка № ${app.number}` : "Заявка" }}
        title={app?.status === "issued" ? "Кредит выдан" : "Подписание договора"}
        app={app}
      />
      <Sheet>{body}</Sheet>
      <SiteFooter />
    </>
  );
}
