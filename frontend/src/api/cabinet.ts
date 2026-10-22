// API кабинета клиента (/companies, /applications; схемы — src/app/types.py бэкенда). Деньги — целые рубли.

import { readToken } from "../auth/AuthContext";
import { ApiError, request, toApiError } from "./client";

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

/** Обороты и остатки за месяц ("2026-10"), раздельно по нашему банку и другим, плюс кредиты. */
export interface MonthFlow {
  month: string;
  inflow: { our: number; other: number };
  balance: { our: number; other: number };
  /** Плановые платежи по кредитам за месяц; до даты кредитного отчёта — оценка */
  payments: number;
  /** Долг по кредитам на конец месяца; до даты кредитного отчёта — оценка */
  debt: number;
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

/**
 * Статус для клиента. checking — и автоматическая оценка, и ручной разбор (различаются по decision.outcome);
 * docs_requested — нужны документы; signing — условия приняты / договор подписан; rejected — отказ или отзыв.
 */
export type ApplicationStatus =
  | "draft"
  | "submitted"
  | "checking"
  | "docs_requested"
  | "counter_offer"
  | "approved"
  | "signing"
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

export type DecisionOutcome = "approved" | "counter_offer" | "declined" | "manual_review";

/** Вариант кредита в решении; платёж — аннуитет в месяц. */
export interface CreditOffer {
  amount: number;
  termMonths: number;
  /** % годовых */
  rate: number;
  monthlyPayment: number;
}

/** «Что вам скорее одобрят» при отказе — другой продукт или сумма на тех же данных. */
export interface CreditAlternative extends CreditOffer {
  productCode: string;
  productName: string;
}

export interface DecisionReason {
  code: string;
  text: string;
}

export interface Decision {
  outcome: DecisionOutcome;
  /** Выбранный вариант (до выбора — offers[0]); null при отказе и ручном разборе */
  amount: number | null;
  termMonths: number | null;
  rate: number | null;
  monthlyPayment: number | null;
  /** Рейтинг A–E и балл скоркарты; null — до скоринга не дошло (стоп-фактор) */
  grade: string | null;
  score: number | null;
  reasons: DecisionReason[];
  /** 1–2 варианта для approved / counter_offer */
  offers: CreditOffer[];
  /** Какой вариант клиент принял; null — ещё не выбирал */
  acceptedOfferIndex: number | null;
  /** Только при отказе по доходу — для новой заявки; может быть пустым */
  alternatives: CreditAlternative[];
  hints: string[];
  decidedAt: string;
}

export interface ApplicationDetails extends Application {
  /** Смены статуса по порядку */
  history: ApplicationEvent[];
  decision: Decision | null;
}

export interface SignCode {
  /** 6 цифр. В демо показываем на экране — SMS в кейсе нет */
  code: string;
  expiresAt: string;
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

const appPath = (id: string, tail = "") => `/applications/${encodeURIComponent(id)}${tail}`;

/** Заявки всех компаний пользователя, новые выше. */
export const listApplications = () => get<Application[]>("/applications");
export const getApplication = (id: string) => get<ApplicationDetails>(appPath(id));
export const listProducts = () => get<CreditProduct[]>("/applications/products");

/** 422 — ошибки по полям формы. idempotencyKey — один на открытие формы: повторная отправка не создаст вторую заявку. */
export const submitApplication = (form: ApplicationForm, idempotencyKey: string) =>
  request<ApplicationDetails>("/applications", {
    method: "POST",
    body: form,
    token: readToken(),
    headers: { "Idempotency-Key": idempotencyKey },
  });

/** Принять вариант из decision.offers → статус signing. 409 — переход сейчас недопустим. */
export const acceptOffer = (id: string, offerIndex: number) =>
  post<ApplicationDetails>(appPath(id, "/accept"), { offerIndex });

/** Имитация SMS: код приходит прямо в ответе. */
export const requestSignCode = (id: string) => post<SignCode>(appPath(id, "/sign-code"), {});

/** 422 — неверный или просроченный код. */
export const signApplication = (id: string, code: string) =>
  post<ApplicationDetails>(appPath(id, "/sign"), { code });

/** Отозвать заявку или отказаться от предложения → rejected. */
export const cancelApplication = (id: string) => post<ApplicationDetails>(appPath(id, "/cancel"), {});

const RECONNECT_MS = 3000;

/** Разбор одного блока SSE: имя события и данные (строки data: склеиваются через \n). */
function parseSseBlock(block: string): { event: string; data: string } {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue; // ping
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  return { event, data: data.join("\n") };
}

/**
 * Живая история заявки (SSE). onHistory получает всю историю: при подключении сервер присылает её целиком,
 * потом — новые события. При обрыве переподключаемся и заменяем историю. Возвращает функцию отписки.
 * EventSource не умеет заголовок Authorization — читаем поток через fetch.
 */
export function watchApplication(
  id: string,
  onHistory: (history: ApplicationEvent[]) => void,
  onError?: (err: ApiError) => void,
): () => void {
  const abort = new AbortController();
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const connect = async () => {
    const history: ApplicationEvent[] = [];
    let finished = false;
    try {
      const token = readToken();
      const res = await fetch(appPath(id, "/events"), {
        headers: { Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        signal: abort.signal,
      });
      if (!res.ok || !res.body) {
        onError?.(res.ok ? new ApiError(0, "Нет связи с сервером") : await toApiError(res));
        // 4xx (нет доступа, нет заявки) — переподключение не поможет
        if (res.status >= 400 && res.status < 500) return;
      } else {
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value.replace(/\r\n?/g, "\n");
          let end;
          while ((end = buffer.indexOf("\n\n")) >= 0) {
            const { event, data } = parseSseBlock(buffer.slice(0, end));
            buffer = buffer.slice(end + 2);
            if (event !== "status" || !data) continue;
            const e = JSON.parse(data) as ApplicationEvent;
            history.push(e);
            onHistory([...history]);
            if (e.status === "issued" || e.status === "rejected") finished = true;
          }
        }
      }
    } catch {
      if (stopped) return;
    }
    // Сервер закрывает поток после issued/rejected — это конец; иначе обрыв, переподключаемся
    if (!stopped && !finished) timer = setTimeout(connect, RECONNECT_MS);
  };

  connect();
  return () => {
    stopped = true;
    clearTimeout(timer);
    abort.abort();
  };
}
