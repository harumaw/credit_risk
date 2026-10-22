import { useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import { acceptOffer, cancelApplication, type ApplicationDetails, type Decision } from "../../api/cabinet";
import { ApiError } from "../../api/client";
import { isCancelled, useApplication } from "../../cabinet/useApplication";
import { ApplicationHead } from "../../components/cabinet/ApplicationHead";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import { applicationTitle } from "../../components/cabinet/StatusChip";
import { SiteFooter } from "../../components/SiteHeader";
import { percent, plural, rub } from "../../lib/format";

const months = (n: number) => `${n} ${plural(n, ["месяц", "месяца", "месяцев"])}`;

interface Copy {
  title: string;
  sub: string;
  reasonsTitle: string;
}

function copyOf(app: ApplicationDetails, d: Decision): Copy {
  if (isCancelled(app))
    return { title: "Заявка отозвана", sub: "Условия больше не действуют. Можно подать новую заявку.", reasonsTitle: "Что было в решении" };
  switch (d.outcome) {
    case "approved":
      return {
        title: d.offers[0] ? `Одобрено: ${rub(d.offers[0].amount)}` : "Одобрено",
        sub: "Всё, что вы просили. Осталось принять условия и подписать договор кодом.",
        reasonsTitle: "Почему одобрили",
      };
    case "counter_offer":
      return {
        title: "Можем дать меньше, чем вы просили",
        sub:
          d.offers.length > 1
            ? "Выберите вариант: платёж почти одинаковый, отличаются сумма и срок."
            : "Посмотрите условия — их можно принять или отказаться.",
        reasonsTitle: "Почему не вся сумма",
      };
    case "manual_review":
      return {
        title: "Решение примет специалист",
        sub: "Автоматическая оценка не дала однозначного ответа — так бывает, это не отказ.",
        reasonsTitle: "Что смотрит специалист",
      };
    default:
      return {
        title: "Эту сумму сейчас дать не можем",
        sub: "Это не отказ навсегда. Ниже — варианты, которые проходят уже сейчас, и что поможет в следующий раз.",
        reasonsTitle: "Почему отказ",
      };
  }
}

/** Варианты кредита: выбор + «Принять» / «Отказаться». */
function Offers({ app, d, onChanged }: { app: ApplicationDetails; d: Decision; onChanged: () => void }) {
  const navigate = useNavigate();
  const [pick, setPick] = useState(0);
  const [declining, setDeclining] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>, after: () => void) {
    setBusy(true);
    setError(null);
    try {
      await action();
      after();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось — попробуйте ещё раз");
      setBusy(false);
    }
  }

  const eyebrow = (i: number) => {
    if (d.outcome === "approved") return "Ваши условия";
    return d.offers[i].termMonths === app.termMonths ? "Тот же срок" : "Сумма больше, срок длиннее";
  };

  return (
    <>
      <div className="offers" role="radiogroup" aria-label="Вариант кредита">
        {d.offers.map((o, i) => (
          <button
            key={i}
            type="button"
            role="radio"
            aria-checked={i === pick}
            className="offer"
            onClick={() => setPick(i)}
            disabled={busy}
          >
            <span className="offer-eyebrow">{eyebrow(i)}</span>
            <span className="offer-amount">{rub(o.amount)}</span>
            <span>
              {months(o.termMonths)} · {percent(o.rate)} годовых
            </span>
            <strong>{rub(o.monthlyPayment)} в месяц</strong>
          </button>
        ))}
      </div>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      {declining ? (
        <div className="app-confirm">
          <p>Отказаться от предложения? Заявка закроется, условия перестанут действовать.</p>
          <div className="btn-row">
            <button
              type="button"
              className="btn btn-dark btn-lg"
              disabled={busy}
              onClick={() => run(() => cancelApplication(app.id), onChanged)}
            >
              {busy ? "Закрываем…" : "Да, отказаться"}
            </button>
            <button type="button" className="btn btn-soft btn-lg" disabled={busy} onClick={() => setDeclining(false)}>
              Нет
            </button>
          </div>
        </div>
      ) : (
        <div className="btn-row">
          <button
            type="button"
            className="btn btn-accent btn-lg"
            disabled={busy}
            onClick={() => run(() => acceptOffer(app.id, pick), () => navigate(`/cabinet/applications/${app.id}/sign`))}
          >
            {busy ? "Принимаем…" : "Принять и перейти к подписанию"}
          </button>
          <button type="button" className="btn btn-soft btn-lg" disabled={busy} onClick={() => setDeclining(true)}>
            Отказаться
          </button>
        </div>
      )}
    </>
  );
}

/** Решение по заявке: одобрено / контрпредложение / отказ с альтернативами / ручной разбор. */
export function ApplicationDecisionPage() {
  const { id = "" } = useParams();
  const data = useApplication(id);
  const app = data.status === "ready" ? data.data : null;
  const d = app?.decision ?? null;
  const base = `/cabinet/applications/${id}`;

  // Условия уже приняты — дальше подписание
  if (app && (app.status === "signing" || app.status === "issued")) return <Navigate to={`${base}/sign`} replace />;

  let body;
  let copy: Copy | null = null;
  if (data.status === "error") body = <SheetStatus error={data.message} onRetry={data.reload} />;
  else if (!app) body = <SheetStatus />;
  else if (!d)
    body = (
      <div className="panel-lg app-empty">
        <h2>{isCancelled(app) ? "Заявка отозвана" : "Решения пока нет"}</h2>
        <p className="muted-lg">
          {isCancelled(app) ? "Решение по ней не принималось." : "Банк ещё оценивает заявку — обычно это пара минут."}
        </p>
        <Link to={base} className="btn btn-dark btn-lg">
          Ход заявки
        </Link>
      </div>
    );
  else {
    copy = copyOf(app, d);
    const canAccept = (app.status === "approved" || app.status === "counter_offer") && d.offers.length > 0;
    const good = d.grade === "A" || d.grade === "B";
    const dot = d.outcome === "approved" ? "good" : d.outcome === "declined" ? "bad" : "info";
    body = (
      <div className="stack">
        {canAccept && <Offers app={app} d={d} onChanged={data.reload} />}

        {d.outcome === "manual_review" && !isCancelled(app) && (
          <div className="app-hero app-hero-dark review-card">
            <span className="app-hero-eyebrow">Обычно до 1 рабочего дня</span>
            <span className="app-hero-title">Заявку смотрит специалист</span>
            <span className="app-hero-text">
              От вас ничего не нужно. Если понадобятся документы, попросим здесь — придёт отметка на главной.
            </span>
          </div>
        )}

        <div className="split-even">
          <div className="panel-lg">
            <div className="reasons-head">
              <h2>{copy.reasonsTitle}</h2>
              <span className={`grade ${good ? "is-good" : ""}`}>Рейтинг {d.grade}</span>
            </div>
            <ul className={`reasons reasons-${dot}`}>
              {d.reasons.map((r) => (
                <li key={r.code}>{r.text}</li>
              ))}
            </ul>
          </div>
          {d.hints.length > 0 && (
            <div className="panel-lg">
              <h2>Что поможет в следующий раз</h2>
              <ul className="hints">
                {d.hints.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {d.alternatives.length > 0 && (
          <div className="stack-sm">
            <div>
              <h2 className="section-title">Что вам скорее одобрят</h2>
              <p className="muted-lg">
                Посчитали на тех же данных: эти варианты проходят по доходу и рейтингу. Повторной проверки кредитной
                истории не будет.
              </p>
            </div>
            <div className="offers">
              {d.alternatives.map((a) => {
                const q = new URLSearchParams({
                  company: app.companyId,
                  product: a.productCode,
                  amount: String(a.amount),
                  term: String(a.termMonths),
                });
                return (
                  <div key={`${a.productCode}-${a.amount}`} className="offer is-alt">
                    <span className="offer-eyebrow">{a.productName}</span>
                    <span className="offer-amount">{rub(a.amount)}</span>
                    <span>
                      {months(a.termMonths)} · {percent(a.rate)} годовых
                    </span>
                    <strong>{rub(a.monthlyPayment)} в месяц</strong>
                    <Link to={`/cabinet/applications/new?${q}`} className="btn btn-dark btn-lg">
                      Подать — анкета заполнится сама
                    </Link>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      <CabinetHeader />
      <ApplicationHead
        back={{ to: base, label: app ? `Заявка № ${app.number} · запросили ${applicationTitle(app)}` : "Заявка" }}
        title={copy?.title ?? "Решение по заявке"}
        sub={copy?.sub}
        app={app}
      />
      <Sheet>{body}</Sheet>
      <SiteFooter />
    </>
  );
}
