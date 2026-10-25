/** API кабинета администратора (/admin/*). Токен сотрудника — отдельный от клиентского. */
import { ApiError, request } from "./client";

const TOKEN_KEY = "admin_token";

export function readAdminToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function writeAdminToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // хранилище недоступно — сессия не переживёт перезагрузку
  }
}

export type Decision = "approve" | "counter_offer" | "manual_review" | "decline";
export type Fact = "default" | "no_default" | "unknown";

export interface Staff {
  id: string;
  login: string;
  fullName: string;
  role: string;
}

export interface Filters {
  q?: string;
  decision?: string;
  segment?: string;
  model?: string;
  grade?: string;
  fact?: string;
  source?: string;
  score_min?: string;
  score_max?: string;
  as_of_from?: string;
  as_of_to?: string;
  borderline?: string;
  hard_stop?: string;
}

export const FILTER_KEYS: (keyof Filters)[] = [
  "q",
  "decision",
  "segment",
  "model",
  "grade",
  "fact",
  "source",
  "score_min",
  "score_max",
  "as_of_from",
  "as_of_to",
  "borderline",
  "hard_stop",
];

export function filtersFromParams(p: URLSearchParams): Filters {
  const f: Filters = {};
  for (const k of FILTER_KEYS) {
    const v = p.get(k);
    if (v) f[k] = v;
  }
  return f;
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

function authed<T>(path: string, opts: { method?: "GET" | "POST"; body?: unknown } = {}): Promise<T> {
  return request<T>(path, { ...opts, token: readAdminToken() }).catch((err) => {
    // Протухший токен — на вход
    if (err instanceof ApiError && err.status === 401) {
      writeAdminToken(null);
      window.dispatchEvent(new Event("admin-logout"));
    }
    throw err;
  });
}

export async function adminLogin(login: string, password: string): Promise<{ token: string; staff: Staff }> {
  const res = await request<{ access_token: string; staff: Staff }>("/admin/auth/login", {
    method: "POST",
    body: { login, password },
  });
  return { token: res.access_token, staff: res.staff };
}

export const adminMe = (token: string) => request<Staff>("/admin/me", { token });

// ---------------------------------------------------------------- компании

export interface Summary {
  companies: number;
  synthetic: number;
  live: number;
  scored: number;
  byDecision: Partial<Record<Decision, number>>;
  approveShare: number;
  manualShare: number;
  declineShare: number;
  defaultAmongApproved: number | null;
  lastScoredAt: string | null;
}

export interface CompanyRow {
  id: string;
  name: string;
  inn: string;
  legalForm: string | null;
  msp: string | null;
  region: string | null;
  status: string | null;
  source: "synthetic" | "live";
  segment: string | null;
  model: string | null;
  modelVersion: string | null;
  modelSegment: string | null;
  score: number | null;
  pd: number | null;
  grade: string | null;
  decision: Decision | null;
  decisionLabel: string | null;
  hardStop: boolean | null;
  fact: Fact;
  asOf: string | null;
  scoredAt: string | null;
}

export interface CompanyList {
  total: number;
  items: CompanyRow[];
  seed: number | null;
}

export const getSummary = () => authed<Summary>("/admin/summary");

export function listCompanies(
  filters: Filters,
  opts: { limit?: number; offset?: number; sort?: string; random?: boolean; seed?: number | null } = {},
) {
  return authed<CompanyList>(
    `/admin/companies${query({ ...filters, limit: opts.limit, offset: opts.offset, sort: opts.sort, random: opts.random || undefined, seed: opts.seed })}`,
  );
}

/** CSV под фильтры — через fetch с токеном, затем отдаём браузеру как файл. */
export async function downloadCsv(filters: Filters, sort: string): Promise<void> {
  const res = await fetch(`/admin/companies.csv${query({ ...filters, sort })}`, {
    headers: { Authorization: `Bearer ${readAdminToken() ?? ""}` },
  });
  if (!res.ok) throw new ApiError(res.status, "Не удалось выгрузить CSV");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "companies.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export interface Contribution {
  feature: string;
  name: string;
  value: string | number | null;
  bin: string;
  points: number;
  best: number;
  lost: number;
  eventRate: number | null;
}

export interface ScoreDetail {
  scoreId: string;
  model: string;
  modelVersion: string;
  modelId: string;
  modelSegment: string | null;
  segment: string | null;
  score: number;
  base: number;
  pd: number;
  grade: string;
  nextGradeAt: number | null;
  decision: Decision | null;
  decisionLabel: string;
  hardStop: boolean;
  reasonCodes: string[];
  reasons: string[];
  asOf: string;
  scoredAt: string;
  inputSha256: string | null;
  contributions: Contribution[];
  stops: { code: string; name: string; triggered: boolean }[];
}

export interface Obligation {
  lender: string | null;
  product: string | null;
  limit: number | null;
  outstanding: number | null;
  overdue: number | null;
  maxDpd: number | null;
  openedAt: string | null;
  closedAt: string | null;
  paymentString: string | null;
  source: string;
}

export interface CompanyCard {
  company: {
    id: string;
    name: string;
    fullName: string | null;
    inn: string;
    ogrn: string | null;
    legalForm: string | null;
    msp: string | null;
    headcount: number | null;
    taxRegime: string | null;
    region: string | null;
    address: string | null;
    registrationDate: string | null;
    status: string | null;
    okved: string[];
    source: "synthetic" | "live";
    dataset: string | null;
    sample: string | null;
  };
  fact: { known: boolean; default: boolean; defaultDate: string | null; trigger: string | null };
  users: { name: string; email: string; role: string; status: string }[];
  features: Record<string, string | number | null> | null;
  score: ScoreDetail | null;
  alternatives: {
    model: string;
    version: string;
    segment: string | null;
    status: string;
    score: number;
    grade: string;
    pd: number;
    decisionLabel: string;
    isCurrent: boolean;
  }[];
  history: {
    id: string;
    model: string;
    version: string;
    score: number;
    grade: string;
    pd: number;
    decisionLabel: string;
    asOf: string;
    scoredAt: string;
  }[];
  applications: ApplicationRow[];
  sources: {
    obligations: Obligation[];
    turnovers: { month: string; inflow: number; outflow: number; balance: number }[];
    accounts: { bik: string; account: string; ownBank: boolean }[];
    tax: { asOf: string; debt: number; penalties: number; fines: number }[];
    fssp: { number: string; openedAt: string; closedAt: string | null; subject: string | null; amount: number; remaining: number }[];
    zsk: { zone: string; asOf: string }[];
    bankruptcy: { caseNumber: string | null; type: string; date: string }[];
    fetches: { id: string; source: string; status: string; requestedAt: string; payload: unknown }[];
  };
}

export const getCompany = (id: string) => authed<CompanyCard>(`/admin/companies/${id}`);
export const rescoreCompany = (id: string) => authed<unknown>(`/admin/companies/${id}/score`, { method: "POST" });

// ---------------------------------------------------------------- заявки

export interface AppStatus {
  code: string;
  label: string;
}

export interface ApplicationRow {
  id: string;
  number: string;
  companyId: string;
  companyName: string;
  inn: string;
  product: string;
  productCode: string;
  requestedAmount: number | null;
  requestedTerm: number | null;
  status: AppStatus;
  decision: Decision | null;
  decisionLabel: string | null;
  approvedAmount: number | null;
  approvedTerm: number | null;
  rate: number | null;
  score: number | null;
  grade: string | null;
  pd: number | null;
  createdAt: string;
  submittedAt: string | null;
  decidedAt: string | null;
}

export interface ApplicationFilters {
  q?: string;
  status?: string;
  decision?: string;
}

export interface Offer {
  productCode: string;
  productName: string;
  amount: number;
  termMonths: number;
  rate: number;
  monthlyPayment: number;
}

export interface StopFactorCheck {
  code: string;
  name: string;
  triggered: boolean;
  details: Record<string, unknown> | null;
}

export interface ApplicationDecision {
  id: string;
  decision: Decision;
  decisionLabel: string;
  approvedAmount: number | null;
  approvedTerm: number | null;
  rate: number | null;
  reasons: { code: string; text: string }[];
  offers: Offer[];
  acceptedOffer: number | null;
  alternatives: Offer[];
  hints: string[];
  inputs: { income: number | null; payments: number | null; dscr: number | null };
  stopFactors: StopFactorCheck[];
  model: { segment: string | null; name: string; version: string; pd: number } | null;
  error: string | null;
  offerExpiresAt: string | null;
  offerAcceptedAt: string | null;
  decidedBy: string;
  comment: string | null;
  decidedAt: string;
  features: Record<string, string | number | null> | null;
  score: (ScoreDetail & { latencyMs: number | null }) | null;
}

export interface ApplicationCard {
  application: {
    id: string;
    number: string;
    status: AppStatus;
    requestedAmount: number | null;
    requestedTerm: number | null;
    purpose: string | null;
    channel: string | null;
    utm: Record<string, string> | null;
    createdAt: string;
    submittedAt: string | null;
    decidedAt: string | null;
    updatedAt: string;
  };
  product: {
    code: string;
    name: string;
    kind: string;
    minAmount: number | null;
    maxAmount: number | null;
    minTerm: number | null;
    maxTerm: number | null;
    baseRate: number | null;
  };
  company: { id: string; name: string; inn: string; legalForm: string | null; region: string | null };
  applicant: { name: string; email: string };
  decisions: ApplicationDecision[];
  history: { from: AppStatus | null; to: AppStatus; comment: string | null; by: string; at: string }[];
  fetches: {
    id: string;
    source: string;
    status: string;
    requestedAt: string;
    receivedAt: string | null;
    error: string | null;
    payload: unknown;
  }[];
  tasks: { id: number; kind: string; status: string; attempts: number; lastError: string | null; createdAt: string; updatedAt: string }[];
  consents: { type: string; version: string; signedAt: string; revokedAt: string | null }[];
}

export function listApplications(filters: ApplicationFilters, opts: { limit?: number; offset?: number; companyId?: string } = {}) {
  return authed<{ total: number; items: ApplicationRow[] }>(
    `/admin/applications${query({ ...filters, company_id: opts.companyId, limit: opts.limit, offset: opts.offset })}`,
  );
}

export const getApplication = (id: string) => authed<ApplicationCard>(`/admin/applications/${id}`);

// ---------------------------------------------------------------- модели

export interface ModelInfo {
  id: string;
  name: string;
  version: string;
  type: string;
  segment: string | null;
  status: string;
  giniTrain: number | null;
  giniOot: number | null;
  ksOot: number | null;
  cutoff: number | null;
  params: Record<string, number | string>;
  trainFrom: string | null;
  trainTo: string | null;
  ootFrom: string | null;
  ootTo: string | null;
  target: string | null;
}

export interface SegmentRule {
  code: string;
  name: string;
  description: string | null;
  priority: number;
  conditions: { any?: Condition[]; all?: Condition[] };
  isActive: boolean;
}

export interface Condition {
  feature: string;
  op: string;
  value: string | number | (string | number)[];
}

export interface ModelBin {
  order: number;
  label: string;
  lower: number | null;
  upper: number | null;
  categories: string[] | null;
  isMissing: boolean;
  points: number;
  woe: number | null;
  eventRate: number | null;
  share: number | null;
}

export interface ModelFeature {
  code: string;
  name: string;
  kind: string;
  coefficient: number | null;
  iv: number | null;
  formula: string | null;
  bins: ModelBin[];
}

export interface Grade {
  grade: string;
  from: number;
  to: number;
  pd: number | null;
}

export interface ModelDetail {
  id: string;
  name: string;
  version: string;
  segment: string | null;
  status: string;
  base: number;
  params: Record<string, number | string>;
  features: ModelFeature[];
  grades: Grade[];
}

export interface CalcResult {
  score: number;
  pd: number;
  grade: string;
  decisionLabel: string;
  reasons: string[];
  contributions: Contribution[];
}

export const listModels = () => authed<{ models: ModelInfo[]; segments: SegmentRule[] }>("/admin/models");
export const getModel = (id: string) => authed<ModelDetail>(`/admin/models/${id}`);
export const calculate = (id: string, features: Record<string, unknown>) =>
  authed<CalcResult>(`/admin/models/${id}/calculate`, { method: "POST", body: { features } });
export const randomExample = (filters: Filters, seed?: number) =>
  authed<{ companyId: string; name: string; features: Record<string, string | number | null> }>(
    `/admin/example${query({ ...filters, seed })}`,
  );

// ---------------------------------------------------------------- срезы

export interface MatrixCell {
  decision: Decision | "none";
  decisionLabel: string;
  fact: Fact;
  count: number;
}

export interface Driver {
  feature: string;
  name: string;
  kind: "num" | "cat";
  group: number;
  reference: number;
  effect: number;
  top?: string;
}

export interface MonthRow {
  month: string;
  n: number;
  approveShare: number;
  avgPd: number;
  defaultRate: number | null;
  avgScore: number;
}

export const getMatrix = (f: Filters) => authed<{ cells: MatrixCell[] }>(`/admin/analysis/matrix${query({ ...f })}`);
export function getDrivers(f: Filters, ref?: Filters) {
  const refParams = Object.fromEntries(Object.entries(ref ?? {}).map(([k, v]) => [`ref_${k}`, v]));
  return authed<{ groupSize: number; referenceSize: number; items: Driver[] }>(
    `/admin/analysis/drivers${query({ ...f, ...refParams })}`,
  );
}
export const getMonthly = (f: Filters) => authed<{ months: MonthRow[] }>(`/admin/analysis/monthly${query({ ...f })}`);

export interface Disagreement {
  sample: number;
  seed: number;
  models: {
    model: string;
    version: string;
    segment: string | null;
    status: string;
    agreeShare: number | null;
    approveShare: number | null;
    defaultAmongApproved: number | null;
  }[];
  examples: { id: string; name: string; model: string; fact: Fact; decisionLabel: string; byModel: Record<string, string | null> }[];
}

export const getDisagreement = (f: Filters, sample: number, seed?: number) =>
  authed<Disagreement>(`/admin/analysis/disagreement${query({ ...f, sample, seed })}`);
