import { useEffect } from "react";
import { Link } from "react-router-dom";

import { getGroupSummary, listApplications, type Application, type Company } from "../../api/cabinet";
import { useAuth } from "../../auth/AuthContext";
import { useCompanies } from "../../cabinet/CompanyContext";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { EmptyCabinet, Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import {
  STATUS,
  StatusChip,
  applicationHref,
  applicationTitle,
  sortByUrgency,
} from "../../components/cabinet/StatusChip";
import { SiteFooter } from "../../components/SiteHeader";
import { dayMonth, monthPrepositional, plural, rub, rubShort, withoutCompanies } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";

const CATEGORY = { micro: "микро", small: "малое", medium: "среднее" } as const;

/** Что нужно от клиента по компании: выписка, документы по заявке или ничего. */
function NeedCell({ company, apps }: { company: Company; apps: Application[] }) {
  if (!company.hasStatement) {
    return (
      <Link to={`/cabinet/companies/${company.id}`} className="need-link">
        загрузить выписку
      </Link>
    );
  }
  const waiting = apps.find((a) => STATUS[a.status].tone === "act" || STATUS[a.status].tone === "offer");
  if (waiting) {
    return (
      <Link to={applicationHref(waiting)} className="need-link">
        {STATUS[waiting.status].label.toLowerCase()} · № {waiting.number}
      </Link>
    );
  }
  return <span className="is-good">ничего</span>;
}

export function CompaniesSummaryPage() {
  const { state } = useAuth();
  const { companies, selection, select, reload } = useCompanies();
  const data = useAsync(() => Promise.all([getGroupSummary(), listApplications()]), []);

  useEffect(() => {
    if (selection !== "all") select("all");
  }, [selection, select]);

  const user = state.status === "authenticated" ? state.user : null;
  const list = companies.status === "ready" ? companies.data : [];

  let body;
  if (companies.status === "error") body = <SheetStatus error={companies.message} onRetry={reload} />;
  else if (data.status === "error") body = <SheetStatus error={data.message} onRetry={data.reload} />;
  else if (companies.status === "loading" || data.status === "loading") body = <SheetStatus />;
  else if (!list.length) body = <EmptyCabinet />;
  else {
    const [summary, allApps] = data.data;
    const active = sortByUrgency(allApps.filter((a) => STATUS[a.status].active));
    const lastInflow = summary.inflowTrend[summary.inflowTrend.length - 1] ?? 0;
    const missing = summary.companiesWithoutStatement;

    body = (
      <div className="stack">
        <div className="stats">
          <div className="stat stat-dark">
            <div className="stat-label">Лимит по группе</div>
            <div className="stat-value">{summary.limit !== null ? rub(summary.limit) : "—"}</div>
            <div className="stat-note">
              {summary.limit !== null
                ? "сколько всего можно взять сейчас"
                : (summary.limitNote ?? "нужна выписка хотя бы по одной компании")}
            </div>
          </div>
          <div className="stat">
            <div className="stat-label">Долг всех компаний</div>
            <div className="stat-value">{rubShort(summary.debt)}</div>
            <div className="stat-note">
              {summary.loansCount
                ? `${summary.loansCount} ${plural(summary.loansCount, ["кредит", "кредита", "кредитов"])}`
                : "кредитов нет"}
            </div>
          </div>
          <div className="stat">
            <div className="stat-label">Платежи в месяц</div>
            <div className="stat-value">{rub(summary.monthlyPayments)}</div>
            {summary.nextPayment && <div className="stat-note">ближайший {dayMonth(summary.nextPayment.date)}</div>}
          </div>
          <div className="stat">
            <div className="stat-label">
              Поступления {summary.lastMonth ? `в ${monthPrepositional(summary.lastMonth)}` : "за месяц"}
            </div>
            <div className="stat-value">{lastInflow ? rubShort(lastInflow) : "—"}</div>
            {missing > 0 && (
              <div className="stat-note is-bad">
                {withoutCompanies(list.filter((c) => !c.hasStatement).map((c) => c.name))} — нет выписки
              </div>
            )}
          </div>
        </div>

        <div className="panel-lg panel-scroll">
          <h2>Компании</h2>
          <table className="table table-wide">
            <thead>
              <tr>
                <th>Компания</th>
                <th>Обороты, мес</th>
                <th>Долг</th>
                <th>Платёж, мес</th>
                <th>Заявки</th>
                <th>Что нужно</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => {
                const apps = sortByUrgency(allApps.filter((a) => a.companyId === c.id && STATUS[a.status].active));
                const inflow = c.inflowTrend[c.inflowTrend.length - 1];
                return (
                  <tr key={c.id}>
                    <td>
                      <Link to={`/cabinet/companies/${c.id}`} className="table-company" onClick={() => select(c.id)}>
                        {c.name}
                      </Link>
                      <div className="table-sub">
                        ИНН {c.inn} · {c.category ? CATEGORY[c.category] : "не МСП"}
                      </div>
                    </td>
                    <td>{inflow !== undefined ? rubShort(inflow) : "нет данных"}</td>
                    <td>{c.debt ? rubShort(c.debt) : "0"}</td>
                    <td>{c.monthlyPayment ? rub(c.monthlyPayment) : "0"}</td>
                    <td>
                      {apps.length
                        ? `№ ${apps[0].number} · ${STATUS[apps[0].status].label.toLowerCase()}${apps.length > 1 ? ` +${apps.length - 1}` : ""}`
                        : "нет"}
                    </td>
                    <td>
                      <NeedCell company={c} apps={apps} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="split-even">
          <div className="panel-lg">
            <h2>Как считаем лимит группы</h2>
            <p className="muted-lg">
              Складываем доход и платежи по кредитам всех ваших компаний. Новый платёж должен помещаться так, чтобы
              доход был выше всех платежей хотя бы в 1,25 раза.
            </p>
            {missing > 0 && (
              <p className="muted-lg">
                Доход {missing === 1 ? list.find((c) => !c.hasStatement)?.name : `${missing} компаний`} пока не учтён — нет выписки. После
                выписки лимит может вырасти.
              </p>
            )}
          </div>
          <div className="panel-lg">
            <h2>Заявки по всем компаниям</h2>
            {active.length ? (
              <div className="mini-apps">
                {active.map((a) => (
                  <Link key={a.id} to={applicationHref(a)} className="mini-app">
                    <span>
                      <strong>
                        № {a.number} · {applicationTitle(a)}
                      </strong>
                      <span>{list.find((c) => c.id === a.companyId)?.name}</span>
                    </span>
                    <StatusChip status={a.status} />
                  </Link>
                ))}
              </div>
            ) : (
              <p className="muted-lg">Активных заявок нет.</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <CabinetHeader />
      <section className="container page-head">
        <div>
          {user && (
            <p className="page-head-meta">
              {user.first_name} {user.last_name}
              {list.length ? ` · ${list.length} ${plural(list.length, ["компания", "компании", "компаний"])}` : ""}
            </p>
          )}
          <h1>Все компании</h1>
        </div>
        {list.length > 0 && (
          <div className="page-head-actions">
            <Link to="/cabinet/companies/new" className="btn btn-dark btn-lg">
              Добавить компанию
            </Link>
            <Link to="/cabinet/applications/new" className="btn btn-accent btn-lg">
              Новая заявка
            </Link>
          </div>
        )}
      </section>
      <Sheet>{body}</Sheet>
      <SiteFooter />
    </>
  );
}
