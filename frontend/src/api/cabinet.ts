// API кабинета клиента (/companies, /applications; схемы — src/app/types.py бэкенда). Деньги — целые рубли.

import { readToken } from "../auth/AuthContext";
import { request } from "./client";

export type CompanyKind = "ul" | "ip";
export type SmeCategory = "micro" | "small" | "medium";

export interface Company {
  id: string;
  kind: CompanyKind;
  name: string;
  inn: string;
  registeredYear: number | null;
  /** null — не субъект МСП */
  category: SmeCategory | null;
  taxRegime: string | null;
  taxRegimeNote: string | null;
  employees: number | null;
  /** Счёт в нашем банке */
  isBankClient: boolean;
  /** Есть данные об оборотах (наш счёт или загруженная выписка) */
  hasStatement: boolean;
  /** Предварительный лимит; null — посчитать пока нельзя */
  limit: number | null;
  /** Почему лимита нет / что в нём не учтено */
  limitNote: string | null;
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
  nextPaymentDate: string | null;
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
  /** До 24 последних полных месяцев, по возрастанию */
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
  limitNote: string | null;
  debt: number;
  monthlyPayments: number;
  loansCount: number;
  nextPayment: NextPayment | null;
  /** Последний месяц в inflowTrend ("2026-09"); null — оборотов нет ни по одной */
  lastMonth: string | null;
  /** Поступления всех компаний с выпиской за 12 месяцев */
  inflowTrend: number[];
  checksOk: number;
  checksTotal: number;
  companiesWithoutStatement: number;
}

export type ApplicationStatus =
  | "draft"
  | "submitted"
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
  companyName: string;
  /** "2026-10-21" */
  createdAt: string;
  product: string;
  productCode: string;
  amount: number | null;
  termMonths: number | null;
  purpose: string | null;
  status: ApplicationStatus;
  /** Что происходит / что нужно от клиента — текст от бэкенда */
  note: string;
}

export interface ApplicationEvent {
  status: ApplicationStatus;
  label: string;
  /** ISO-время */
  at: string;
  comment: string | null;
}

export interface ApplicationDetails extends Application {
  /** Смены статуса по порядку */
  history: ApplicationEvent[];
}

export type ProductKind = "term_loan" | "credit_line" | "overdraft" | "bank_guarantee";

export interface CreditProduct {
  code: string;
  name: string;
  kind: ProductKind;
  minAmount: number;
  maxAmount: number;
  minTermMonths: number;
  maxTermMonths: number;
  /** % годовых — для примерного платежа; итоговую ставку даст решение */
  rate: number;
}

export interface ApplicationForm {
  companyId: string;
  productCode: string;
  amount: number;
  termMonths: number;
  purpose: string;
  consentPersonalData: boolean;
  consentBki: boolean;
}

export interface CompanyLookup {
  inn: string;
  kind: CompanyKind;
  name: string;
  /** «март 2021» */
  registeredAt: string | null;
  /** «56.10 · Деятельность ресторанов…» */
  activity: string | null;
  director: string | null;
  directorMatches: boolean;
  alreadyAddedId: string | null;
}

export type SourceState = "done" | "work" | "wait" | "error";

export interface SourceStatus {
  key: string;
  label: string;
  state: SourceState;
}

const get = <T>(path: string) => request<T>(path, { token: readToken() });
const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body, token: readToken() });

export const listCompanies = () => get<Company[]>("/companies");
export const getCompany = (id: string) => get<CompanyDetails>(`/companies/${encodeURIComponent(id)}`);
export const getGroupSummary = () => get<GroupSummary>("/companies/group-summary");
/** ФИО и ИНН пользователя сервер берёт из токена. 404 — нет в реестре, 503 — реестр недоступен. */
export const lookupCompany = (inn: string) => post<CompanyLookup>("/companies/lookup", { inn });
/** 403 — руководитель другой человек, 409 — уже в кабинете. */
export const addCompany = (inn: string) => post<Company>("/companies", { inn });
export const getCompanySources = (id: string) => get<SourceStatus[]>(`/companies/${encodeURIComponent(id)}/sources`);

/** Заявки всех компаний пользователя, новые выше. */
export const listApplications = () => get<Application[]>("/applications");
export const getApplication = (id: string) => get<ApplicationDetails>(`/applications/${encodeURIComponent(id)}`);
export const listProducts = () => get<CreditProduct[]>("/applications/products");
/** 422 — ошибки по полям формы (сумма/срок вне условий продукта, нет согласия и т. п.). */
export const submitApplication = (form: ApplicationForm) => post<ApplicationDetails>("/applications", form);
