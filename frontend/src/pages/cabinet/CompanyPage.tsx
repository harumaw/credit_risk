import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { getCompany, listApplications, type Application, type CompanyDetails, type MonthFlow } from "../../api/cabinet";
import { useCompanies } from "../../cabinet/CompanyContext";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import { FlowChart, GhostChart, type FlowBar } from "../../components/cabinet/FlowChart";
import { STATUS, StageBar, applicationTitle, sortByUrgency } from "../../components/cabinet/StatusChip";
import { UploadIcon } from "../../components/Icons";
import { SiteFooter } from "../../components/SiteHeader";
import { dayMonthNum, monthShort, percentDelta, plural, rub, rubShort } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";

const CATEGORY = { micro: "Микропредприятие", small: "Малое предприятие", medium: "Среднее предприятие" } as const;

type Period = 3 | 6 | 12;
type Granularity = "month" | "quarter";
type Accounts = "all" | "our" | "other";

const PERIODS: [Period, string][] = [
  [3, "3 мес"],
  [6, "6 мес"],
  [12, "12 мес"],
];
const GRANULARITY: [Granularity, string][] = [
  ["month", "По месяцам"],
  ["quarter", "По кварталам"],
];
const ACCOUNTS: [Accounts, string][] = [
  ["all", "Все счета"],
  ["our", "Наш банк"],
  ["other", "Другие банки"],
];

function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: [T, string][];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="segmented segmented-sm" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={String(v)} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  );
}

const sum = (xs: number[]) => xs.reduce((s, x) => s + x, 0);

/** Месяцы → столбики графика; кварталы — по 3 месяца с конца периода, остаток и долг на конец квартала. */
function toBars(flows: MonthFlow[], forecast: MonthFlow[], gran: Granularity, pick: (v: MonthFlow["inflow"]) => number) {
  const one = (fs: MonthFlow[], isForecast: boolean): FlowBar => ({
    label: fs.length > 1 ? `${monthShort(fs[0].month)}–${monthShort(fs[fs.length - 1].month)}` : monthShort(fs[0].month),
    inflow: sum(fs.map((f) => pick(f.inflow))),
    balance: pick(fs[fs.length - 1].balance),
    payments: sum(fs.map((f) => f.payments)),
    debt: fs[fs.length - 1].debt,
    forecast: isForecast,
  });
  if (gran === "month") {
    return [...flows.map((f) => one([f], false)), ...forecast.map((f) => one([f], true))];
  }
  const chunks: MonthFlow[][] = [];
  for (let end = flows.length; end > 0; end -= 3) chunks.unshift(flows.slice(Math.max(end - 3, 0), end));
  return [...chunks.map((c) => one(c, false)), ...(forecast.length ? [one(forecast, true)] : [])];
}

function Stat({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: "good" | "muted" }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone === "muted" ? "is-muted" : ""}`}>{value}</div>
      {note && <div className={`stat-note ${tone === "good" ? "is-good" : ""}`}>{note}</div>}
    </div>
  );
}

function Flows({ company }: { company: CompanyDetails }) {
  const [period, setPeriod] = useState<Period>(12);
  const [gran, setGran] = useState<Granularity>("month");
  const [accounts, setAccounts] = useState<Accounts>("all");

  const pick = (v: MonthFlow["inflow"]) => (accounts === "all" ? v.our + v.other : v[accounts]);
  const hist = company.flows.slice(-period);
  const prevHist = company.flows.slice(-2 * period, -period);
  const inflow = sum(hist.map((f) => pick(f.inflow)));
  const prevInflow = sum(prevHist.map((f) => pick(f.inflow)));
  const avgBalance = hist.length ? sum(hist.map((f) => pick(f.balance))) / hist.length : 0;
  const delta = prevHist.length === hist.length ? percentDelta(inflow, prevInflow) : null;
  const bars = toBars(hist, company.forecast, gran, pick);

  return (
    <>
      <div className="filters">
        <Segmented label="Период" options={PERIODS} value={period} onChange={setPeriod} />
        <Segmented label="Гранулярность" options={GRANULARITY} value={gran} onChange={setGran} />
        <Segmented label="Счета" options={ACCOUNTS} value={accounts} onChange={setAccounts} />
      </div>

      <div className="stats">
        <Stat
          label={`Поступления за ${period} мес`}
          value={rubShort(inflow)}
          note={delta ? `${delta} к прошлому периоду` : undefined}
          tone="good"
        />
        <Stat label="Средний остаток" value={rubShort(avgBalance)} note="на конец месяца" />
        <Stat
          label="Долговая нагрузка"
          value={company.dscr !== null ? company.dscr.toLocaleString("ru-RU") : "—"}
          note="доход / платежи, норма от 1,25"
        />
        <div className="stat stat-dark">
          <div className="stat-label">Предварительный лимит</div>
          <div className="stat-value">{company.limit !== null ? rub(company.limit) : "—"}</div>
          {company.limit !== null ? (
            <Link to="/cabinet/applications/new" className="stat-link">
              Оформить в 2 клика
            </Link>
          ) : (
            company.limitNote && <div className="stat-note">{company.limitNote}</div>
          )}
        </div>
      </div>

      <div className="split">
        <div className="panel-lg">
          <h2>Обороты и остатки</h2>
          {bars.length ? <FlowChart bars={bars} /> : <p className="muted">Нет данных за период</p>}
        </div>
        <Checks company={company} />
      </div>
    </>
  );
}

function NoStatement({ company }: { company: CompanyDetails }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    setFileName(e.target.files?.[0]?.name ?? null);
  }

  return (
    <>
      <div className="statement-banner">
        <div>
          <span className="htile-kicker">Лимит пока не можем посчитать</span>
          <span className="statement-title">
            Счёт {company.kind === "ip" ? "ИП" : "компании"} открыт в другом банке — загрузите выписку за 12 месяцев
          </span>
          <span>PDF или 1С-файл. Посчитаем обороты и остатки, покажем лимит здесь же. Обычно 1–2 минуты.</span>
          {fileName && (
            <span className="statement-file" role="status">
              Файл «{fileName}» получен. Разбор выписки подключим вместе с бэкендом — пока лимит не пересчитан.
            </span>
          )}
        </div>
        <button type="button" className="btn btn-accent btn-lg" onClick={() => inputRef.current?.click()}>
          <UploadIcon size={18} strokeWidth={2.4} />
          Загрузить выписку
        </button>
        <input ref={inputRef} type="file" accept=".pdf,.txt" hidden onChange={onFile} />
      </div>

      <div className="stats">
        <Stat label="Поступления за 12 мес" value="—" note="появятся после выписки" tone="muted" />
        <Stat label="Средний остаток" value="—" note="появится после выписки" tone="muted" />
        <Stat
          label={company.kind === "ip" ? "Кредиты ИП" : "Кредиты компании"}
          value={rub(company.debt)}
          note={company.debt ? undefined : "по данным БКИ долгов нет"}
          tone="good"
        />
        <Stat label="Налоговый режим" value={company.taxRegime ?? "—"} note={company.taxRegimeNote ?? undefined} />
      </div>

      <div className="split">
        <div className="panel-lg">
          <h2>Обороты и остатки</h2>
          <GhostChart />
          <p className="muted">Здесь будет график по месяцам с прогнозом — после выписки.</p>
        </div>
        <Checks company={company} />
      </div>
    </>
  );
}

function Checks({ company }: { company: CompanyDetails }) {
  return (
    <div className="panel-lg">
      <h2>{company.kind === "ip" ? "Проверки ИП" : "Проверки компании"}</h2>
      <dl className="check-list">
        {company.checks.map((c) => (
          <div key={c.label}>
            <dt>{c.label}</dt>
            <dd className={c.ok ? undefined : "is-bad"}>{c.value}</dd>
          </div>
        ))}
      </dl>
      {company.okved.length > 0 && (
        <>
          <div className="okved-title">ОКВЭД</div>
          <ul className="okved">
            {company.okved.map((o) => (
              <li key={o.code} className={o.main ? "is-main" : undefined} title={o.title}>
                {o.code}
                {o.main ? " · основной" : ""}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function Loans({ company }: { company: CompanyDetails }) {
  return (
    <div className="panel-lg panel-scroll" id="loans">
      <h2>Кредиты и выплаты</h2>
      {company.loans.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>Кредитор</th>
              <th>Остаток</th>
              <th>Платёж в месяц</th>
              <th>Ближайший</th>
              <th>Просрочка</th>
            </tr>
          </thead>
          <tbody>
            {company.loans.map((l) => (
              <tr key={l.id}>
                <td className="strong">
                  {l.lender} · {l.product}
                </td>
                <td>{rub(l.balance)}</td>
                <td>{rub(l.monthlyPayment)}</td>
                <td>{l.nextPaymentDate ? dayMonthNum(l.nextPaymentDate) : "—"}</td>
                <td className={l.overdue ? "is-bad" : "is-good"}>{l.overdue ? "есть" : "нет"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">Кредитов нет — по данным БКИ долгов нет.</p>
      )}
    </div>
  );
}

function CurrentApplication({ apps }: { apps: Application[] }) {
  const active = sortByUrgency(apps.filter((a) => STATUS[a.status].active));
  const app = active[0];
  if (!app) {
    return (
      <div className="app-card">
        <div className="app-card-meta">Заявки</div>
        <div className="app-card-title">По компании заявок нет</div>
        <p>Подайте заявку — данные компании подставим сами.</p>
        <Link to="/cabinet/applications/new" className="btn btn-accent">
          Новая заявка
        </Link>
      </div>
    );
  }
  return (
    <div className="app-card">
      <div className="app-card-meta">
        Заявка № {app.number} · {applicationTitle(app)}
      </div>
      <div className="app-card-title">{STATUS[app.status].label}</div>
      <StageBar status={app.status} labels />
      <p>{app.note}</p>
      {active.length > 1 && (
        <Link to="/cabinet/applications" className="app-card-link">
          Все заявки по компании: {active.length}
        </Link>
      )}
    </div>
  );
}

export function CompanyPage() {
  const { id = "" } = useParams();
  const { hash } = useLocation();
  const { companies, selection, select } = useCompanies();
  const data = useAsync(() => Promise.all([getCompany(id), listApplications()]), [id]);
  const companiesCount = companies.status === "ready" ? companies.data.length : 0;

  // Открыли компанию по ссылке — она становится выбранной в шапке
  useEffect(() => {
    if (companies.status === "ready" && companies.data.some((c) => c.id === id) && selection !== id) select(id);
  }, [id, companies, selection, select]);

  // Якорь (#loans) появляется только после загрузки — прокручиваем сами
  useEffect(() => {
    if (data.status === "ready" && hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
  }, [data.status, hash]);

  if (data.status !== "ready") {
    return (
      <>
        <CabinetHeader />
        <Sheet>
          {data.status === "loading" ? (
            <SheetStatus />
          ) : (
            <>
              <SheetStatus error={data.message} onRetry={data.reload} />
              <Link to="/cabinet" className="text-link">
                На главную кабинета
              </Link>
            </>
          )}
        </Sheet>
        <SiteFooter />
      </>
    );
  }

  const [company, allApps] = data.data;
  const apps = allApps.filter((a) => a.companyId === company.id);

  return (
    <>
      <CabinetHeader />
      <section className="container page-head">
        <div>
          <p className="page-head-meta">
            {[
              `ИНН ${company.inn}`,
              company.registeredYear && `Действует с ${company.registeredYear} года`,
              company.category ? CATEGORY[company.category] : "Не субъект МСП",
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <h1>{company.name}</h1>
        </div>
        <div className="page-head-actions">
          {companiesCount > 1 && (
            <Link to="/cabinet/companies" className="btn btn-dark btn-lg" onClick={() => select("all")}>
              Сводка по {companiesCount} {plural(companiesCount, ["компании", "компаниям", "компаниям"])}
            </Link>
          )}
          <Link to="/cabinet/applications/new" className="btn btn-accent btn-lg">
            Новая заявка
          </Link>
        </div>
      </section>

      <section className="sheet sheet-tight">
        <div className="container stack">
          {company.hasStatement ? <Flows company={company} /> : <NoStatement company={company} />}
          <div className="split">
            <Loans company={company} />
            <CurrentApplication apps={apps} />
          </div>
        </div>
      </section>
      <SiteFooter />
    </>
  );
}
