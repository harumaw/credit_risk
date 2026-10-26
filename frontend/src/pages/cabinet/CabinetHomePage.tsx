import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { getGroupSummary, listApplications, type Company } from "../../api/cabinet";
import { useAuth } from "../../auth/AuthContext";
import { useCompanies } from "../../cabinet/CompanyContext";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { EmptyCabinet, Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import { STATUS, StageBar, applicationSummary, sortByUrgency } from "../../components/cabinet/StatusChip";
import { PlusIcon } from "../../components/Icons";
import { SiteFooter } from "../../components/SiteHeader";
import { dayMonth, monthPrepositional, percentDelta, plural, rub, rubShort, withoutCompanies } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";

const CATEGORY = { micro: "микро", small: "малое", medium: "среднее" } as const;

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  return (
    <div className="spark" aria-hidden="true">
      {values.map((v, i) => (
        <span
          key={i}
          className={i === values.length - 1 ? "last" : undefined}
          style={{ height: `${Math.max(Math.round((v / max) * 100), 4)}%` }}
        />
      ))}
    </div>
  );
}

function CompanyCard({ company, current }: { company: Company; current: boolean }) {
  const meta = [
    `ИНН ${company.inn}`,
    company.category ? CATEGORY[company.category] : "не МСП",
    company.taxRegime,
    company.employees ? `${company.employees} ${plural(company.employees, ["человек", "человека", "человек"])}` : null,
    company.isBankClient ? "клиент банка" : "обороты в другом банке",
  ].filter(Boolean);
  const inflow = company.inflowTrend[company.inflowTrend.length - 1];

  return (
    <Link to={`/cabinet/companies/${company.id}`} className={`company-card ${current ? "is-current" : ""}`}>
      <div className="company-card-head">
        <strong>{company.name}</strong>
        {current && <span className="chip chip-act">выбрана</span>}
      </div>
      <span className="company-card-meta">{meta.join(" · ")}</span>
      <dl className="company-card-stats">
        <div>
          <dt>Обороты, мес</dt>
          <dd>{inflow !== undefined ? rubShort(inflow).replace(" ₽", "") : "—"}</dd>
        </div>
        <div>
          <dt>Долг</dt>
          <dd>{company.debt ? rubShort(company.debt).replace(" ₽", "") : "0"}</dd>
        </div>
        <div>
          <dt>Лимит</dt>
          <dd>{company.limit !== null ? rubShort(company.limit).replace(" ₽", "") : "—"}</dd>
        </div>
      </dl>
      {!company.hasStatement && <span className="company-card-need">Загрузите выписку, чтобы узнать лимит</span>}
    </Link>
  );
}

export function CabinetHomePage() {
  const { state } = useAuth();
  const { companies, selected, reload } = useCompanies();
  const data = useAsync(() => Promise.all([getGroupSummary(), listApplications()]), []);
  const firstName = state.status === "authenticated" ? state.user.first_name : "";

  let body: ReactNode;
  if (companies.status === "loading" || data.status === "loading") {
    body = <Sheet><SheetStatus /></Sheet>;
  } else if (companies.status === "error") {
    body = <Sheet><SheetStatus error={companies.message} onRetry={reload} /></Sheet>;
  } else if (data.status === "error") {
    body = <Sheet><SheetStatus error={data.message} onRetry={data.reload} /></Sheet>;
  } else if (!companies.data.length) {
    body = (
      <>
        <div className="container">
          <h1 className="cab-hello">Здравствуйте, {firstName}</h1>
        </div>
        <Sheet>
          <EmptyCabinet />
        </Sheet>
      </>
    );
  } else {
    const list = companies.data;
    const [summary, allApps] = data.data;

    // Плитки показывают выбранную компанию или всю группу
    const limit = selected ? selected.limit : summary.limit;
    const limitNote = selected ? selected.limitNote : summary.limitNote;
    const needsStatement = selected ? !selected.hasStatement : summary.companiesWithoutStatement > 0;
    const trend = selected ? selected.inflowTrend : summary.inflowTrend;
    const nextPayment = selected ? selected.nextPayment : summary.nextPayment;
    const debt = selected ? selected.debt : summary.debt;
    const loansCount = selected ? selected.loansCount : summary.loansCount;
    const checksOk = selected ? selected.checksOk : summary.checksOk;
    const checksTotal = selected ? selected.checksTotal : summary.checksTotal;
    const apps = sortByUrgency(
      allApps.filter((a) => STATUS[a.status].active && (!selected || a.companyId === selected.id)),
    );
    const [topApp, ...otherApps] = apps;
    const appCompany = topApp && list.find((c) => c.id === topApp.companyId);

    const last = trend.length ? trend[trend.length - 1] : undefined;
    const prev = trend.length > 1 ? trend[trend.length - 2] : undefined;
    const delta = last !== undefined && prev !== undefined ? percentDelta(last, prev) : null;

    body = (
      <>
        <section className="container">
          <h1 className="cab-hello">Здравствуйте, {firstName}</h1>
          <div className="home-bento">
            <div className="htile htile-limit">
              {limit !== null ? (
                <>
                  <span className="htile-kicker">Предварительный лимит</span>
                  <span className="htile-big">{rub(limit)}</span>
                  <span>
                    {selected
                      ? `по оборотам счёта ${selected.name}`
                      : `с учётом долгов ${list.length} ${plural(list.length, ["компании", "компаний", "компаний"])}`}
                  </span>
                  <div className="htile-actions">
                    <Link to="/cabinet/applications/new" className="btn btn-accent btn-lg">
                      Оформить
                    </Link>
                    <Link to="/calculator" className="btn btn-white btn-lg">
                      Рассчитать платёж
                    </Link>
                  </div>
                </>
              ) : !needsStatement ? (
                <>
                  <span className="htile-kicker">Лимит пока не можем посчитать</span>
                  <span className="htile-mid">{limitNote ?? "Не хватает данных о компании"}</span>
                </>
              ) : (
                <>
                  <span className="htile-kicker">Лимит пока не можем посчитать</span>
                  <span className="htile-mid">Загрузите выписку из другого банка за 12 месяцев</span>
                  <span>Посчитаем обороты и покажем лимит здесь же. Обычно 1–2 минуты.</span>
                  <div className="htile-actions">
                    <Link
                      to={`/cabinet/companies/${selected?.id ?? (list.find((c) => !c.hasStatement) ?? list[0]).id}`}
                      className="btn btn-accent btn-lg"
                    >
                      Загрузить выписку
                    </Link>
                  </div>
                </>
              )}
            </div>

            {topApp ? (
              <Link to="/cabinet/applications" className="htile htile-app">
                <span className="htile-small">
                  {!selected && appCompany ? `${appCompany.name} · ` : ""}Заявка № {topApp.number}
                </span>
                <span className="htile-title">{STATUS[topApp.status].label}</span>
                <span className="htile-small">{applicationSummary(topApp)}</span>
                <StageBar status={topApp.status} />
                <span className="htile-note">{topApp.note}</span>
                {otherApps.length > 0 && (
                  <span className="htile-more">
                    Ещё {otherApps.length} {plural(otherApps.length, ["заявка", "заявки", "заявок"])}
                  </span>
                )}
              </Link>
            ) : (
              <Link to="/cabinet/applications/new" className="htile htile-app">
                <span className="htile-small">Заявки</span>
                <span className="htile-title">Активных заявок нет</span>
                <span className="htile-small">Подайте заявку — данные компании подставим сами</span>
                <span className="htile-more">Новая заявка</span>
              </Link>
            )}

            <Link to={selected ? `/cabinet/companies/${selected.id}#loans` : "/cabinet/companies"} className="htile htile-pay">
              {nextPayment ? (
                <>
                  <span className="htile-small">Ближайший платёж</span>
                  <span className="htile-num">{rub(nextPayment.amount)}</span>
                  <span className="htile-small">
                    {dayMonth(nextPayment.date)} · {nextPayment.product}
                  </span>
                </>
              ) : (
                <>
                  <span className="htile-small">Ближайший платёж</span>
                  <span className="htile-num">Нет</span>
                  <span className="htile-small">кредитов сейчас нет</span>
                </>
              )}
              <span className="htile-foot">
                {debt
                  ? `Всего долг: ${rubShort(debt)} по ${loansCount} ${plural(loansCount, ["кредиту", "кредитам", "кредитам"])}`
                  : "Долгов по кредитам нет"}
              </span>
            </Link>

            <div className="htile htile-flow">
              {last !== undefined ? (
                <>
                  <div className="htile-flow-text">
                    <span className="htile-small">Поступления {summary.lastMonth ? `в ${monthPrepositional(summary.lastMonth)}` : "за месяц"}</span>
                    <span className="htile-num">{rubShort(last)}</span>
                    {delta && <span className="htile-delta">{delta} к прошлому месяцу</span>}
                    {!selected && summary.companiesWithoutStatement > 0 && (
                      <span className="htile-warn">
                        {withoutCompanies(list.filter((c) => !c.hasStatement).map((c) => c.name))} — нет выписки
                      </span>
                    )}
                  </div>
                  <Sparkline values={trend} />
                </>
              ) : (
                <div className="htile-flow-text">
                  <span className="htile-small">Поступления</span>
                  <span className="htile-num">—</span>
                  <span className="htile-small">появятся после выписки</span>
                </div>
              )}
            </div>

            <div className="htile htile-checks">
              <span className="htile-small">{selected ? "Проверки компании" : "Проверки компаний"}</span>
              <span className="htile-num">
                {checksOk} из {checksTotal}
              </span>
              <span className="htile-small">
                {checksOk === checksTotal
                  ? "без налогового долга, ФССП и банкротств"
                  : `есть замечания: ${checksTotal - checksOk}`}
              </span>
            </div>

            <Link to="/cabinet/companies/new" className="htile htile-add">
              <span className="htile-title">Найти ещё компании по ИНН</span>
              <span className="htile-plus">
                <PlusIcon size={22} color="#EF3B2D" strokeWidth={2.4} />
              </span>
            </Link>
          </div>
        </section>

        <section className="sheet">
          <div className="container">
            <div className="sheet-head">
              <h2>Мои компании</h2>
              <div className="group-stats">
                <span>
                  Долг по группе: <strong>{rubShort(summary.debt)}</strong>
                </span>
                <span>
                  Платежи в месяц: <strong>{rub(summary.monthlyPayments)}</strong>
                </span>
                <span>
                  Лимит с учётом группы: <strong>{summary.limit !== null ? rubShort(summary.limit) : "—"}</strong>
                </span>
              </div>
            </div>
            <div className="company-cards">
              {list.map((c) => (
                <CompanyCard key={c.id} company={c} current={selected?.id === c.id} />
              ))}
            </div>
          </div>
        </section>
      </>
    );
  }

  return (
    <>
      <CabinetHeader />
      {body}
      <SiteFooter />
    </>
  );
}
