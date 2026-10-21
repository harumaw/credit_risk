// API кабинета клиента. Пока бэкенд не готов, ответы отдают моки (src/mocks/cabinet.ts);
// при переходе на сервер меняются только тела функций ниже — страницы работают с этими типами.

import * as mock from "../mocks/cabinet";

export type CompanyKind = "ul" | "ip";
export type SmeCategory = "micro" | "small" | "medium";

export interface Company {
  id: string;
  kind: CompanyKind;
  name: string;
  inn: string;
  registeredYear: number;
  category: SmeCategory;
  taxRegime: string;
  taxRegimeNote: string | null;
  employees: number | null;
  /** Счёт в нашем банке */
  isBankClient: boolean;
  /** Есть данные об оборотах (наш счёт или загруженная выписка) */
  hasStatement: boolean;
  /** Предварительный лимит; null — посчитать пока нельзя */
  limit: number | null;
  debt: number;
  monthlyPayment: number;
  loansCount: number;
  /** Доход / платежи по кредитам; null — нет данных об оборотах */
  dscr: number | null;
  /** Поступления за последние 12 месяцев по возрастанию; пусто — нет данных об оборотах */
  inflowTrend: number[];
  nextPayment: NextPayment | null;
  checksOk: number;
  checksTotal: number;
}

export interface CompanyCheck {
  label: string;
  value: string;
  ok: boolean;
}

export interface Okved {
  code: string;
  title: string;
  main: boolean;
}

export interface Loan {
  id: string;
  lender: string;
  product: string;
  balance: number;
  monthlyPayment: number;
  nextPaymentDate: string;
  overdue: boolean;
}

/** Обороты и остатки за месяц ("2026-10"), раздельно по нашему банку и другим. */
export interface MonthFlow {
  month: string;
  inflow: { our: number; other: number };
  balance: { our: number; other: number };
}

export interface CompanyDetails extends Company {
  checks: CompanyCheck[];
  okved: Okved[];
  loans: Loan[];
  /** Последние 24 месяца, по возрастанию */
  flows: MonthFlow[];
  /** Прогноз на 3 месяца вперёд */
  forecast: MonthFlow[];
}

export interface NextPayment {
  amount: number;
  date: string;
  product: string;
  companyId: string;
}

export interface GroupSummary {
  /** Лимит с учётом долгов всех компаний; null — нет данных ни по одной */
  limit: number | null;
  debt: number;
  monthlyPayments: number;
  loansCount: number;
  nextPayment: NextPayment | null;
  /** Последний месяц в inflowTrend ("2026-10") */
  lastMonth: string;
  /** Поступления всех компаний с выпиской за 12 месяцев */
  inflowTrend: number[];
  checksOk: number;
  checksTotal: number;
  companiesWithoutStatement: number;
}

export type ApplicationStatus =
  | "draft"
  | "checking"
  | "docs_requested"
  | "counter_offer"
  | "approved"
  | "issued"
  | "rejected";

export interface Application {
  id: string;
  number: string;
  companyId: string;
  createdAt: string;
  product: string;
  amount: number | null;
  termMonths: number | null;
  status: ApplicationStatus;
  /** Что происходит / что нужно от клиента — текст от бэкенда */
  note: string;
}

export interface CompanyLookup {
  inn: string;
  kind: CompanyKind;
  name: string;
  registeredAt: string;
  activity: string;
  director: string;
  directorMatches: boolean;
  alreadyAddedId: string | null;
}

export type SourceState = "done" | "work" | "wait" | "error";

export interface SourceStatus {
  key: string;
  label: string;
  state: SourceState;
}

export const listCompanies = (): Promise<Company[]> => mock.listCompanies();
export const getCompany = (id: string): Promise<CompanyDetails> => mock.getCompany(id);
export const getGroupSummary = (): Promise<GroupSummary> => mock.getGroupSummary();
export const listApplications = (): Promise<Application[]> => mock.listApplications();
export const lookupCompany = (inn: string, userFullName: string): Promise<CompanyLookup> =>
  mock.lookupCompany(inn, userFullName);
export const addCompany = (inn: string): Promise<Company> => mock.addCompany(inn);
export const getCompanySources = (id: string): Promise<SourceStatus[]> => mock.getCompanySources(id);
