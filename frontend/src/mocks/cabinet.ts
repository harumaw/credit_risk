// Моки кабинета клиента — синтетические данные, пока нет API бэкенда.
// Сценарий по макету: ООО «Северный ветер» (клиент банка, заявка на проверке) + ИП без выписки.
// Пустой кабинет: открыть /cabinet?demo=empty (до перезагрузки страницы).

import type {
  Application,
  Company,
  CompanyDetails,
  CompanyLookup,
  GroupSummary,
  MonthFlow,
  NextPayment,
  SourceStatus,
} from "../api/cabinet";
import { ApiError } from "../api/client";

/** Как компания хранится в моке; производные поля (тренд, ближайший платёж, проверки) считаются при ответе. */
type MockCompany = Omit<CompanyDetails, "inflowTrend" | "nextPayment" | "checksOk" | "checksTotal">;

const LAST_MONTH = "2026-10";
const MLN = 1_000_000;

function addMonths(ym: string, delta: number): string {
  const [y, m] = ym.split("-").map(Number);
  const total = y * 12 + (m - 1) + delta;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
}

/** 24 месяца истории: прошлый год — те же месяцы с поправкой на рост. */
function makeFlows(inflow: number[], balance: number[], ourShare: number, growth: number): MonthFlow[] {
  const yearAgo = inflow.map((v, i) => v / growth + ((i % 3) - 1) * 0.08);
  const all = [...yearAgo, ...inflow];
  const allBalance = [...balance.map((b) => b / growth), ...balance];
  return all.map((v, i) => ({
    month: addMonths(LAST_MONTH, i - 23),
    inflow: { our: Math.round(v * ourShare * MLN), other: Math.round(v * (1 - ourShare) * MLN) },
    balance: { our: Math.round(allBalance[i] * ourShare * MLN), other: Math.round(allBalance[i] * (1 - ourShare) * MLN) },
  }));
}

function makeForecast(inflow: number[], balance: number[], ourShare: number): MonthFlow[] {
  return inflow.map((v, i) => ({
    month: addMonths(LAST_MONTH, i + 1),
    inflow: { our: Math.round(v * ourShare * MLN), other: Math.round(v * (1 - ourShare) * MLN) },
    balance: { our: Math.round(balance[i] * ourShare * MLN), other: Math.round(balance[i] * (1 - ourShare) * MLN) },
  }));
}

const NORTH_WIND: MockCompany = {
  id: "c-north-wind",
  kind: "ul",
  name: "ООО «Северный ветер»",
  inn: "7701234560",
  registeredYear: 2019,
  category: "small",
  taxRegime: "УСН",
  taxRegimeNote: "«доходы»",
  employees: 24,
  isBankClient: true,
  hasStatement: true,
  limit: 2_750_000,
  debt: 2_100_000,
  monthlyPayment: 100_000,
  loansCount: 2,
  dscr: 1.8,
  checks: [
    { label: "Статус в ЕГРЮЛ", value: "Действует", ok: true },
    { label: "Налоговый долг", value: "Нет", ok: true },
    { label: "ФССП", value: "Нет производств", ok: true },
    { label: "Банкротства", value: "0", ok: true },
    { label: "Красная зона ЦБ", value: "Нет", ok: true },
    { label: "Спецрежим", value: "УСН «доходы»", ok: true },
    { label: "Категория МСП", value: "Малое", ok: true },
    { label: "Численность", value: "24 человека", ok: true },
  ],
  okved: [
    { code: "46.90", title: "Неспециализированная оптовая торговля", main: true },
    { code: "47.91", title: "Торговля через интернет", main: false },
    { code: "52.29", title: "Транспортная обработка грузов", main: false },
  ],
  loans: [
    {
      id: "l-1",
      lender: "Наш банк",
      product: "оборотный кредит",
      balance: 1_240_000,
      monthlyPayment: 68_400,
      nextPaymentDate: "2026-10-25",
      overdue: false,
    },
    {
      id: "l-2",
      lender: "Банк «Пример»",
      product: "лизинг",
      balance: 860_000,
      monthlyPayment: 31_600,
      nextPaymentDate: "2026-11-02",
      overdue: false,
    },
  ],
  flows: makeFlows(
    [3.4, 4.8, 2.9, 3.3, 3.9, 4.1, 4.4, 3.8, 4.0, 4.6, 4.5, 4.9],
    [1.6, 2.1, 1.2, 1.5, 1.8, 2.0, 2.2, 1.9, 2.0, 2.3, 2.2, 2.4],
    0.82,
    1.12,
  ),
  forecast: makeForecast([5.0, 5.6, 3.5], [2.5, 2.8, 1.7], 0.82),
};

const IP_SMIRNOVA: MockCompany = {
  id: "c-ip-smirnova",
  kind: "ip",
  name: "ИП Смирнова А. В.",
  inn: "500100000015",
  registeredYear: 2022,
  category: "micro",
  taxRegime: "Патент",
  taxRegimeNote: "розничная торговля",
  employees: null,
  isBankClient: false,
  hasStatement: false,
  limit: null,
  debt: 0,
  monthlyPayment: 0,
  loansCount: 0,
  dscr: null,
  checks: [
    { label: "Статус в ЕГРИП", value: "Действует", ok: true },
    { label: "Налоговый долг", value: "Нет", ok: true },
    { label: "ФССП", value: "Нет производств", ok: true },
    { label: "Банкротства", value: "0", ok: true },
    { label: "Красная зона ЦБ", value: "Нет", ok: true },
    { label: "Категория МСП", value: "Микро", ok: true },
  ],
  okved: [
    { code: "47.71", title: "Торговля одеждой", main: true },
    { code: "47.19", title: "Прочая розничная торговля", main: false },
  ],
  loans: [],
  flows: [],
  forecast: [],
};

const APPLICATIONS: Application[] = [
  {
    id: "a-1051",
    number: "1051",
    companyId: IP_SMIRNOVA.id,
    createdAt: "2026-10-20",
    product: "Оборотный кредит",
    amount: 1_500_000,
    termMonths: 12,
    status: "docs_requested",
    note: "Счёт в другом банке — без выписки не сможем решить",
  },
  {
    id: "a-1047",
    number: "1047",
    companyId: NORTH_WIND.id,
    createdAt: "2026-10-18",
    product: "Оборотный кредит",
    amount: 5_000_000,
    termMonths: 12,
    status: "counter_offer",
    note: "Можем дать 2 750 000 ₽ на 12 мес или 4 920 000 ₽ на 24 мес",
  },
  {
    id: "a-1042",
    number: "1042",
    companyId: NORTH_WIND.id,
    createdAt: "2026-10-15",
    product: "Оборотный кредит",
    amount: 3_000_000,
    termMonths: 24,
    status: "checking",
    note: "От вас ничего не нужно — сообщим здесь",
  },
  {
    id: "a-1053",
    number: "1053",
    companyId: NORTH_WIND.id,
    createdAt: "2026-10-21",
    product: "Овердрафт",
    amount: null,
    termMonths: null,
    status: "draft",
    note: "Заполнено 3 шага из 6",
  },
  {
    id: "a-1012",
    number: "1012",
    companyId: NORTH_WIND.id,
    createdAt: "2026-08-02",
    product: "Оборотный кредит",
    amount: 1_200_000,
    termMonths: 18,
    status: "issued",
    note: "Кредит выдан 05.08, платёж 68 400 ₽ в месяц",
  },
  {
    id: "a-1008",
    number: "1008",
    companyId: IP_SMIRNOVA.id,
    createdAt: "2026-07-27",
    product: "Оборотный кредит",
    amount: 800_000,
    termMonths: 6,
    status: "rejected",
    note: "Не хватило данных об оборотах — подайте снова с выпиской",
  },
];

/** Справочник «ЕГРЮЛ» симулятора: известные ИНН; остальные корректные ИНН находятся с выдуманным названием. */
const REGISTRY: Record<string, { name: string; registeredAt: string; activity: string; director?: string }> = {
  "7705551232": { name: "ООО «Ромашка»", registeredAt: "март 2021", activity: "56.10 · рестораны" },
  "7812345675": {
    name: "ООО «Балтийский берег»",
    registeredAt: "июнь 2017",
    activity: "49.41 · грузоперевозки",
    director: "Кузнецов Игорь Петрович",
  },
};

const SOURCES = [
  ["egrul", "ЕГРЮЛ"],
  ["fns", "Налоги и отчётность (ФНС)"],
  ["fssp", "Приставы (ФССП)"],
  ["efrsb", "Банкротства (ЕФРСБ)"],
  ["zsk", "Зона риска ЦБ"],
  ["bki", "Кредитная история (БКИ)"],
  ["turnover", "Обороты по счетам"],
] as const;
const SOURCE_STEP_MS = 700;

const demoEmpty = new URLSearchParams(window.location.search).get("demo") === "empty";
const companies: MockCompany[] = demoEmpty ? [] : [NORTH_WIND, IP_SMIRNOVA];
const applications: Application[] = demoEmpty ? [] : APPLICATIONS;
/** Когда начали собирать данные по компании (для шага 3 «Собираем данные») */
const sourcesStartedAt = new Map<string, number>();
/** Названия из последних поисков по ИНН — чтобы добавленная компания называлась так же */
const lookedUpNames = new Map<string, string>();

const reply = <T>(value: T, ms = 250) =>
  new Promise<T>((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));
const fail = (err: ApiError, ms = 250) => new Promise<never>((_, reject) => setTimeout(() => reject(err), ms));

const total = (f: MonthFlow) => f.inflow.our + f.inflow.other;

function nextPaymentOf(c: MockCompany): NextPayment | null {
  const next = [...c.loans].sort((a, b) => a.nextPaymentDate.localeCompare(b.nextPaymentDate))[0];
  return next ? { amount: next.monthlyPayment, date: next.nextPaymentDate, product: next.product, companyId: c.id } : null;
}

function toDetails(c: MockCompany): CompanyDetails {
  return {
    ...c,
    inflowTrend: c.flows.slice(-12).map(total),
    nextPayment: nextPaymentOf(c),
    checksOk: c.checks.filter((x) => x.ok).length,
    checksTotal: c.checks.length,
  };
}

function toCompany(c: MockCompany): Company {
  const { checks: _c, okved: _o, loans: _l, flows: _f, forecast: _p, ...company } = toDetails(c);
  return company;
}

export const listCompanies = () => reply(companies.map(toCompany));

export function getCompany(id: string) {
  const company = companies.find((c) => c.id === id);
  return company ? reply(toDetails(company)) : fail(new ApiError(404, "Компания не найдена"));
}

export function getGroupSummary() {
  const list = companies.map(toDetails);
  const withLimit = list.filter((c) => c.limit !== null);
  const next = list
    .map((c) => c.nextPayment)
    .filter((p): p is NextPayment => p !== null)
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  const summary: GroupSummary = {
    limit: withLimit.length ? withLimit.reduce((s, c) => s + (c.limit ?? 0), 0) : null,
    debt: list.reduce((s, c) => s + c.debt, 0),
    monthlyPayments: list.reduce((s, c) => s + c.monthlyPayment, 0),
    loansCount: list.reduce((s, c) => s + c.loansCount, 0),
    nextPayment: next ?? null,
    lastMonth: LAST_MONTH,
    inflowTrend: Array.from({ length: 12 }, (_, i) => list.reduce((s, c) => s + (c.inflowTrend[i] ?? 0), 0)),
    checksOk: list.reduce((s, c) => s + c.checksOk, 0),
    checksTotal: list.reduce((s, c) => s + c.checksTotal, 0),
    companiesWithoutStatement: list.filter((c) => !c.hasStatement).length,
  };
  return reply(summary);
}

export const listApplications = () => reply(applications);

export function lookupCompany(inn: string, userFullName: string) {
  if (inn.startsWith("99")) return fail(new ApiError(404, "Компания с таким ИНН не найдена в ЕГРЮЛ и ЕГРИП"), 600);
  const kind = inn.length === 12 ? "ip" : "ul";
  const known = REGISTRY[inn];
  const director = known?.director ?? userFullName;
  const [last = "", first = "", middle = ""] = userFullName.split(" ");
  const lookup: CompanyLookup = {
    inn,
    kind,
    name:
      known?.name ??
      (kind === "ip" ? `ИП ${last} ${first.charAt(0)}.${middle ? ` ${middle.charAt(0)}.` : ""}` : `ООО «Компания ${inn.slice(-4)}»`),
    registeredAt: known?.registeredAt ?? "январь 2020",
    activity: known?.activity ?? (kind === "ip" ? "47.19 · розничная торговля" : "46.90 · оптовая торговля"),
    director,
    directorMatches: director === userFullName,
    alreadyAddedId: companies.find((c) => c.inn === inn)?.id ?? null,
  };
  lookedUpNames.set(inn, lookup.name);
  return reply(lookup, 600);
}

export function addCompany(inn: string) {
  if (companies.some((c) => c.inn === inn)) return fail(new ApiError(409, "Эта компания уже в кабинете"));
  const kind = inn.length === 12 ? "ip" : "ul";
  const seed = Number(inn.slice(-3)) % 7;
  const scale = 0.4 + seed / 10;
  const scaleFlow = (f: MonthFlow): MonthFlow => ({
    month: f.month,
    inflow: { our: Math.round(f.inflow.our * scale), other: Math.round(f.inflow.other * scale) },
    balance: { our: Math.round(f.balance.our * scale), other: Math.round(f.balance.other * scale) },
  });
  const base = kind === "ul" ? NORTH_WIND : IP_SMIRNOVA;
  const company: MockCompany = {
    ...structuredClone(base),
    id: `c-${inn}`,
    inn,
    name: lookedUpNames.get(inn) ?? (kind === "ip" ? `ИП ${inn.slice(-4)}` : `ООО «Компания ${inn.slice(-4)}»`),
    registeredYear: 2020 + (seed % 4),
    debt: 0,
    monthlyPayment: 0,
    loansCount: 0,
    loans: [],
    flows: base.flows.map(scaleFlow),
    forecast: base.forecast.map(scaleFlow),
  };
  if (kind === "ul") {
    company.limit = Math.round((total(company.flows[company.flows.length - 1]) * 0.6) / 50_000) * 50_000;
    company.dscr = null;
  }
  companies.push(company);
  sourcesStartedAt.set(company.id, Date.now());
  return reply(toCompany(company), 500);
}

export function getCompanySources(id: string) {
  const company = companies.find((c) => c.id === id);
  if (!company) return fail(new ApiError(404, "Компания не найдена"));
  const started = sourcesStartedAt.get(id) ?? 0;
  const done = Math.floor((Date.now() - started) / SOURCE_STEP_MS);
  const statuses: SourceStatus[] = SOURCES.map(([key, label], i) => {
    const title = key === "egrul" && company.kind === "ip" ? "ЕГРИП" : label;
    if (i < done) {
      // У ИП без счёта в нашем банке обороты не найти — понадобится выписка
      return { key, label: title, state: key === "turnover" && !company.hasStatement ? "error" : "done" };
    }
    return { key, label: title, state: i === done ? "work" : "wait" };
  });
  return reply(statuses, 150);
}
