import { Link, useParams } from "react-router-dom";

import { getApplication } from "../../api/cabinet";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import { StageBar, StatusChip, applicationTitle } from "../../components/cabinet/StatusChip";
import { ChevronLeft } from "../../components/Icons";
import { SiteFooter } from "../../components/SiteHeader";
import { dayMonth, rub } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });

/** Экран заявки: что отправили и что с ней происходит. */
export function ApplicationPage() {
  const { id = "" } = useParams();
  const data = useAsync(() => getApplication(id), [id]);
  const app = data.status === "ready" ? data.data : null;

  let body;
  if (data.status === "error") body = <SheetStatus error={data.message} onRetry={data.reload} />;
  else if (!app) body = <SheetStatus />;
  else
    body = (
      <div className="stack">
        <div className="panel-lg">
          <div className="stub-app">
            <strong>{applicationTitle(app)}</strong>
            <StatusChip status={app.status} />
          </div>
          <StageBar status={app.status} labels />
          <p className="muted-lg">{app.note}</p>
        </div>

        <div className="split-even">
          <div className="panel-lg">
            <h2>Анкета</h2>
            <dl className="details">
              <div>
                <dt>Компания</dt>
                <dd>{app.companyName}</dd>
              </div>
              <div>
                <dt>Кредит</dt>
                <dd>{app.product}</dd>
              </div>
              <div>
                <dt>Сумма</dt>
                <dd>{app.amount !== null ? rub(app.amount) : "—"}</dd>
              </div>
              <div>
                <dt>Срок</dt>
                <dd>{app.termMonths !== null ? `${app.termMonths} мес` : "—"}</dd>
              </div>
              <div>
                <dt>Цель</dt>
                <dd>{app.purpose ?? "—"}</dd>
              </div>
            </dl>
          </div>

          <div className="panel-lg">
            <h2>История</h2>
            <ol className="timeline">
              {app.history.map((e, i) => (
                <li key={i}>
                  <strong>{e.label}</strong>
                  <span className="muted">
                    {dayMonth(e.at)}, {time(e.at)}
                  </span>
                  {e.comment && <span className="timeline-comment">{e.comment}</span>}
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="btn-row">
          <Link to="/cabinet/applications" className="btn btn-dark btn-lg">
            Все заявки
          </Link>
          <Link to={`/cabinet/companies/${app.companyId}`} className="btn btn-white btn-lg">
            К компании
          </Link>
        </div>
      </div>
    );

  return (
    <>
      <CabinetHeader />
      <section className="container page-head page-head-col">
        <Link to="/cabinet/applications" className="back-link">
          <ChevronLeft size={14} strokeWidth={2.4} />
          Заявки
        </Link>
        <h1>{app ? `Заявка № ${app.number}` : "Заявка"}</h1>
        {app && <p className="page-head-sub">от {dayMonth(app.createdAt)}</p>}
      </section>
      <Sheet>{body}</Sheet>
      <SiteFooter />
    </>
  );
}
