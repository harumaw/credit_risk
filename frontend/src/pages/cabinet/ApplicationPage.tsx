import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { cancelApplication, type ApplicationDetails } from "../../api/cabinet";
import { ApiError } from "../../api/client";
import { isCancelled, useApplication } from "../../cabinet/useApplication";
import { ApplicationHead } from "../../components/cabinet/ApplicationHead";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import { StatusChip, applicationTitle } from "../../components/cabinet/StatusChip";
import { CheckIcon } from "../../components/Icons";
import { SiteFooter } from "../../components/SiteHeader";
import { dayMonthNum, rub, timeHm } from "../../lib/format";

/** Что ещё будет, пока банк оценивает заявку (серым под пройденными шагами). */
const PLANNED = ["Собрали данные", "Проверили ограничения", "Оцениваем заявку", "Решение готово"];
/** Отправка + шаги из PLANNED */
const PLANNED_TOTAL = PLANNED.length + 1;

const CANCELLABLE = new Set(["submitted", "checking", "counter_offer", "approved", "signing"]);

type Tone = "dark" | "offer" | "ok" | "muted";

interface Hero {
  tone: Tone;
  eyebrow: string;
  title: string;
  text: string;
  action?: { to: string; label: string };
}

const termsText = (amount: number, months: number) => `${rub(amount)} на ${months} мес`;

function heroOf(app: ApplicationDetails): Hero {
  const d = app.decision;
  const base = `/cabinet/applications/${app.id}`;
  if (isCancelled(app))
    return {
      tone: "muted",
      eyebrow: "Заявка закрыта",
      title: "Заявка отозвана",
      text: "Можно подать новую — данные компании подставим сами.",
      action: { to: "/cabinet/applications/new", label: "Новая заявка" },
    };
  if (app.status === "rejected")
    return {
      tone: "muted",
      eyebrow: "Решение готово",
      title: "Эту сумму сейчас дать не можем",
      text: "Это не отказ навсегда — покажем, что одобрят уже сейчас и что поможет в следующий раз.",
      action: { to: `${base}/decision`, label: "Почему и что вместо" },
    };
  if (app.status === "issued")
    return {
      tone: "ok",
      eyebrow: "Кредит выдан",
      title: d?.amount ? `${rub(d.amount)} на счёте` : "Деньги на счёте",
      text: d?.monthlyPayment ? `Платёж ${rub(d.monthlyPayment)} в месяц. Напомним о платеже на главной.` : "Напомним о платеже на главной.",
      action: { to: `/cabinet/companies/${app.companyId}`, label: "К компании" },
    };
  if (app.status === "signing")
    return {
      tone: "offer",
      eyebrow: "Условия приняты",
      title: "Осталось подписать договор",
      text:
        d?.amount && d.termMonths
          ? `${termsText(d.amount, d.termMonths)}${d.monthlyPayment ? `, платёж ${rub(d.monthlyPayment)} в месяц` : ""}. Подпись — кодом, прямо здесь.`
          : "Подпись — кодом, прямо здесь.",
      action: { to: `${base}/sign`, label: "Подписать договор" },
    };
  if ((app.status === "approved" || app.status === "counter_offer") && d?.offers.length) {
    const [first, second] = d.offers;
    return {
      tone: "offer",
      eyebrow: "Решение готово",
      title:
        app.status === "approved"
          ? `Одобрено: ${termsText(first.amount, first.termMonths)}`
          : `Есть решение: можем дать ${termsText(first.amount, first.termMonths)}`,
      text: second
        ? `Или ${termsText(second.amount, second.termMonths)}. Выберите вариант на странице решения.`
        : "Посмотрите условия и примите их — дальше подписание кодом.",
      action: { to: `${base}/decision`, label: "Посмотреть решение" },
    };
  }
  if (d?.outcome === "manual_review")
    return {
      tone: "dark",
      eyebrow: "Обычно до 1 рабочего дня",
      title: "Заявку смотрит специалист",
      text: "От вас ничего не нужно. Если понадобятся документы, попросим здесь.",
      action: { to: `${base}/decision`, label: "Что смотрит специалист" },
    };
  return {
    tone: "dark",
    eyebrow: "Обычно занимает пару минут",
    title: "Оцениваем заявку",
    text: "От вас ничего не нужно. Страницу можно закрыть — статус обновится здесь и на главной.",
  };
}

/** Ход заявки: пройденные события + серые шаги, которые ещё впереди. */
function Events({ app }: { app: ApplicationDetails }) {
  const inProgress = (app.status === "submitted" || app.status === "checking") && !app.decision;
  const missing = inProgress ? Math.max(0, PLANNED_TOTAL - app.history.length) : 0;
  const pending = PLANNED.slice(PLANNED.length - missing);
  const last = app.history.length - 1;
  const live = inProgress || app.decision?.outcome === "manual_review";

  return (
    <ol className="app-events">
      {app.history.map((e, i) => {
        const now = live && i === last;
        return (
          <li key={`${e.at}-${i}`} className={now ? "is-now" : "is-done"}>
            <span className="app-event-dot" aria-hidden="true">
              {!now && <CheckIcon size={14} strokeWidth={3} />}
            </span>
            <span className="app-event-text">
              <strong>{e.label}</strong>
              {e.comment && <span>{e.comment}</span>}
            </span>
            <time dateTime={e.at}>{timeHm(e.at)}</time>
          </li>
        );
      })}
      {pending.map((label) => (
        <li key={label} className="is-wait">
          <span className="app-event-dot" aria-hidden="true" />
          <span className="app-event-text">
            <strong>{label}</strong>
            <span>Ещё не началось</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function CancelLink({ app, onDone }: { app: ApplicationDetails; onDone: () => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!CANCELLABLE.has(app.status)) return null;

  async function onCancel() {
    setBusy(true);
    setError(null);
    try {
      await cancelApplication(app.id);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отозвать заявку");
      setBusy(false);
    }
  }

  if (!asking)
    return (
      <button type="button" className="text-link app-cancel" onClick={() => setAsking(true)}>
        Отозвать заявку
      </button>
    );
  return (
    <div className="app-confirm" role="group" aria-label="Отозвать заявку">
      <p>Отозвать заявку № {app.number}? Условия перестанут действовать, вернуть заявку будет нельзя.</p>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      <div className="btn-row">
        <button type="button" className="btn btn-dark" onClick={onCancel} disabled={busy}>
          {busy ? "Отзываем…" : "Да, отозвать"}
        </button>
        <button type="button" className="btn btn-white" onClick={() => setAsking(false)} disabled={busy}>
          Нет
        </button>
      </div>
    </div>
  );
}

/** Экран заявки: живой ход рассмотрения, анкета, отзыв. */
export function ApplicationPage() {
  const { id = "" } = useParams();
  const data = useApplication(id);
  const app = data.status === "ready" ? data.data : null;

  let body;
  if (data.status === "error") body = <SheetStatus error={data.message} onRetry={data.reload} />;
  else if (!app) body = <SheetStatus />;
  else {
    const hero = heroOf(app);
    body = (
      <div className="app-layout">
        <div className="stack">
          <div className={`app-hero app-hero-${hero.tone}`} aria-live="polite">
            <span className="app-hero-eyebrow">{hero.eyebrow}</span>
            <span className="app-hero-title">{hero.title}</span>
            <span className="app-hero-text">{hero.text}</span>
            {hero.action && (
              <Link to={hero.action.to} className={`btn btn-lg ${hero.tone === "dark" ? "btn-white" : "btn-dark"}`}>
                {hero.action.label}
              </Link>
            )}
          </div>
          <div className="panel-lg">
            <h2>Что происходит с заявкой</h2>
            <Events app={app} />
          </div>
        </div>

        <div className="panel-lg">
          <h2>Анкета</h2>
          <dl className="facts">
            <dt>Компания</dt>
            <dd>{app.companyName}</dd>
            <dt>Кредит</dt>
            <dd>{app.product}</dd>
            <dt>Сумма</dt>
            <dd>{app.amount !== null ? rub(app.amount) : "—"}</dd>
            <dt>Срок</dt>
            <dd>{app.termMonths !== null ? `${app.termMonths} мес` : "—"}</dd>
            <dt>Цель</dt>
            <dd>{app.purpose ?? "—"}</dd>
          </dl>
          <CancelLink app={app} onDone={data.reload} />
        </div>
      </div>
    );
  }

  const sent = app?.history[0];
  return (
    <>
      <CabinetHeader />
      <ApplicationHead
        back={{ to: "/cabinet/applications", label: "Все заявки" }}
        title={app ? `Заявка № ${app.number}` : "Заявка"}
        sub={
          app &&
          `${app.product} · ${applicationTitle(app)}${sent ? ` · отправлена ${dayMonthNum(sent.at)} в ${timeHm(sent.at)}` : ""}`
        }
        aside={app && <StatusChip status={app.status} label={isCancelled(app) ? "Отозвана" : undefined} />}
        app={app}
      />
      <Sheet>{body}</Sheet>
      <SiteFooter />
    </>
  );
}
