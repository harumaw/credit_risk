// Мок решения по заявке — пока backend не сделал GET .decision, accept, sign-code, sign, cancel и SSE /events.
// Берёт настоящую заявку в статусе «отправлена» и за несколько секунд проводит её дальше по контракту:
// сбор данных → проверки → оценка → решение. Исход — по сумме и предварительному лимиту компании:
//   в пределах лимита — одобрено; до двух лимитов — контрпредложение; больше — отказ с альтернативами;
//   нет выписки — на рассмотрении у специалиста; компания не действует — отказ.
// Любой исход для демо: открыть заявку с ?outcome=approved|counter_offer|declined|manual_review (начнёт заново).
// Принятие условий, подпись и отзыв хранятся в localStorage этого браузера.

import type {
  Application,
  ApplicationDetails,
  ApplicationEvent,
  ApplicationStatus,
  Company,
  CreditAlternative,
  CreditOffer,
  CreditProduct,
  Decision,
  DecisionOutcome,
  DecisionReason,
  SignCode,
} from "../api/cabinet";
import { ApiError } from "../api/client";
import { dayMonthNum, rub } from "../lib/format";

const STORAGE_KEY = "decision_mock_v1";
const OUTCOMES: DecisionOutcome[] = ["approved", "counter_offer", "declined", "manual_review"];
const DECISION_AT_MS = 7000;
const CODE_TTL_MS = 5 * 60_000;
const POLL_MS = 500;

interface MockState {
  /** Когда мок впервые увидел заявку — начало сценария, если время отправки с сервера позже */
  firstSeen: number;
  /** Сценарий перезапущен через ?outcome= — считаем от этого момента */
  restartedAt?: number;
  outcome?: DecisionOutcome;
  accepted?: number;
  acceptedAt?: number;
  signedAt?: number;
  cancelledAt?: number;
  code?: string;
  codeExpires?: number;
}

type Store = Record<string, MockState>;

function readStore(): Store {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Store;
  } catch {
    return {};
  }
}

function writeStore(store: Store): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // приватный режим — сценарий просто начнётся заново после перезагрузки
  }
}

function stateOf(id: string): MockState {
  const store = readStore();
  if (!store[id]) {
    store[id] = { firstSeen: Date.now() };
    writeStore(store);
  }
  return store[id];
}

/** restart — начать сценарий заново (новый firstSeen, прежние действия забыть). */
function patchState(id: string, patch: Partial<MockState>, restart = false): void {
  const store = readStore();
  const prev = restart ? undefined : store[id];
  store[id] = { ...(prev ?? { firstSeen: Date.now() }), ...patch };
  writeStore(store);
}

/** ?outcome=… в адресе — начать сценарий заново с этим исходом. */
function applyOutcomeParam(id: string): void {
  const param = new URLSearchParams(window.location.search).get("outcome") as DecisionOutcome | null;
  if (param && OUTCOMES.includes(param) && stateOf(id).outcome !== param) patchState(id, { outcome: param, restartedAt: Date.now() }, true);
}

// ---------- расчёты ----------

function annuity(amount: number, months: number, ratePct: number): number {
  const r = ratePct / 100 / 12;
  return r === 0 ? amount / months : (amount * r) / (1 - Math.pow(1 + r, -months));
}

/** Сколько можно взять при платеже `payment` в месяц. */
function presentValue(payment: number, months: number, ratePct: number): number {
  const r = ratePct / 100 / 12;
  return r === 0 ? payment * months : (payment * (1 - Math.pow(1 + r, -months))) / r;
}

const floorTo = (v: number, step: number) => Math.floor(v / step) * step;

function offer(amount: number, termMonths: number, rate: number): CreditOffer {
  return { amount, termMonths, rate, monthlyPayment: Math.round(annuity(amount, termMonths, rate)) };
}

const terms = (o: CreditOffer) => `${rub(o.amount)} на ${o.termMonths} мес`;

interface Context {
  base: ApplicationDetails;
  company: Company | undefined;
  products: CreditProduct[];
}

/** Последние настоящие данные заявки — для accept/sign/cancel/watch, которые получают только id. */
const seen = new Map<string, Context>();

function autoOutcome(app: Application, company: Company | undefined): DecisionOutcome {
  if (!company) return "manual_review";
  if (company.limit === null) return company.hasStatement ? "declined" : "manual_review";
  const amount = app.amount ?? 0;
  if (amount <= company.limit) return "approved";
  return amount <= company.limit * 2 ? "counter_offer" : "declined";
}

function makeDecision({ base: app, company, products }: Context, outcome: DecisionOutcome, s: MockState, at: number): Decision {
  const product = products.find((p) => p.code === app.productCode);
  const rate = product?.rate || 24;
  const amount = app.amount ?? product?.minAmount ?? 1_000_000;
  const term = app.termMonths ?? 12;
  const maxTerm = product?.maxTermMonths ?? 60;
  // Предварительного лимита нет (нет выписки) — для демо считаем, что доход тянет половину суммы
  const limit = company?.limit ?? null;
  const capAmount = limit ?? amount / 2;
  const payCap = annuity(capAmount, term, rate);
  const payAsked = Math.round(annuity(amount, term, rate));

  let offers: CreditOffer[] = [];
  let alternatives: CreditAlternative[] = [];
  let reasons: DecisionReason[] = [];
  let hints: string[] = [];
  let grade = "C";
  let score = 600;

  if (outcome === "approved") {
    offers = [offer(amount, term, rate)];
    const share = limit ? amount / limit : 1;
    [grade, score] = share <= 0.7 ? ["A", 665] : ["B", 640];
    reasons = [
      { code: "INCOME_OK", text: `Платёж ${rub(offers[0].monthlyPayment)} в месяц укладывается в доход с запасом` },
      { code: "HISTORY_OK", text: "Кредиты гасили без просрочек" },
      { code: "CHECKS_OK", text: "Проверки пройдены: налоги, приставы, банкротства, зона риска ЦБ" },
    ];
  } else if (outcome === "counter_offer") {
    const same = offer(floorTo(Math.min(capAmount, amount), 10_000), term, rate);
    const longTerm = Math.min(term * 2, maxTerm);
    offers = [same];
    if (longTerm > term) {
      const more = floorTo(Math.min(presentValue(payCap, longTerm, rate), amount), 10_000);
      if (more > same.amount) offers.push(offer(more, longTerm, rate));
    }
    [grade, score] = ["B", 630];
    reasons = [
      {
        code: "DSCR_LIMIT",
        text: `Платёж за ${rub(amount)} на ${term} мес — ${rub(payAsked)} в месяц, это больше, чем позволяет доход (до ${rub(Math.round(payCap))})`,
      },
      { code: "GRADE_OK", text: "Рейтинг хороший — сумму ограничивает только доход" },
      { code: "BUFFER", text: "Платёж по вариантам оставляет запас 25% дохода" },
    ];
  } else if (outcome === "manual_review") {
    [grade, score] = ["C", 600];
    reasons = [
      company && !company.hasStatement
        ? { code: "NO_STATEMENT", text: "Счёт в другом банке — доход посмотрит специалист по выписке" }
        : { code: "AUTO_UNSURE", text: "Автоматическая оценка не дала однозначного ответа" },
      { code: "CHECKS_OK", text: "Ограничений по реестрам нет: банкротства, ликвидации и красной зоны ЦБ нет" },
    ];
  } else if (limit === null && company?.hasStatement) {
    // Стоп-фактор: компания не действует
    [grade, score] = ["E", 540];
    reasons = [{ code: "STOP_STATUS", text: company.limitNote ?? "Компания не действует по данным ЕГРЮЛ" }];
    hints = ["Кредит можно получить только на действующую компанию", "Если в реестре ошибка — обратитесь в налоговую, затем подайте снова"];
  } else {
    [grade, score] = ["D", 570];
    reasons = [
      {
        code: "DSCR_FAIL",
        text: `Платёж ${rub(payAsked)} в месяц намного больше, чем позволяет доход (до ${rub(Math.round(payCap))})`,
      },
    ];
    if (company?.monthlyPayment)
      reasons.push({ code: "DEBT_LOAD", text: `Текущие кредиты уже забирают ${rub(company.monthlyPayment)} в месяц` });
    hints = [
      `Подайте на сумму до ${rub(floorTo(capAmount, 10_000))} — она проходит уже сейчас`,
      "Срок длиннее уменьшает платёж — так можно взять больше",
      "Залог (недвижимость или оборудование) позволит взять больше",
    ];
    if (product) {
      const altTerm = Math.min(Math.max(term, 24), product.maxTermMonths);
      const altAmount = floorTo(Math.min(presentValue(payCap * 0.9, altTerm, rate), product.maxAmount), 10_000);
      if (altAmount >= product.minAmount)
        alternatives.push({ ...offer(altAmount, altTerm, rate), productCode: product.code, productName: product.name });
    }
    const overdraft = products.find((p) => p.kind === "overdraft" && p.code !== product?.code);
    const inflow = company?.inflowTrend.length ? company.inflowTrend.reduce((a, b) => a + b, 0) / company.inflowTrend.length : 0;
    if (overdraft && inflow) {
      const odAmount = floorTo(Math.min(inflow * 0.2, overdraft.maxAmount), 10_000);
      const odTerm = Math.min(12, overdraft.maxTermMonths);
      if (odAmount >= overdraft.minAmount)
        alternatives.push({ ...offer(odAmount, odTerm, overdraft.rate), productCode: overdraft.code, productName: overdraft.name });
    }
    alternatives = alternatives.slice(0, 2);
  }

  const chosen = s.accepted !== undefined ? offers[s.accepted] : outcome === "approved" ? offers[0] : undefined;
  return {
    outcome,
    amount: chosen?.amount ?? null,
    termMonths: chosen?.termMonths ?? null,
    rate: chosen?.rate ?? null,
    monthlyPayment: chosen?.monthlyPayment ?? null,
    grade,
    score,
    reasons,
    offers,
    alternatives,
    hints,
    decidedAt: new Date(at).toISOString(),
  };
}

// ---------- сценарий ----------

interface Computed {
  history: ApplicationEvent[];
  status: ApplicationStatus;
  decision: Decision | null;
  note: string;
}

const event = (status: ApplicationStatus, label: string, at: number, comment: string | null = null): ApplicationEvent => ({
  status,
  label,
  at: new Date(at).toISOString(),
  comment,
});

function compute(ctx: Context, now = Date.now()): Computed {
  const { base, company } = ctx;
  const s = stateOf(base.id);
  const submitted = base.history[0];
  const sent = submitted ? Date.parse(submitted.at) : NaN;
  const start = s.restartedAt ?? (Number.isNaN(sent) ? s.firstSeen : Math.min(sent, s.firstSeen));
  const outcome = s.outcome ?? autoOutcome(base, company);
  const inactive = outcome === "declined" && company?.limit === null && company.hasStatement;

  const plan: ApplicationEvent[] = [
    ...base.history,
    event("checking", "Собрали данные", start + 1500, "8 источников: ЕГРЮЛ, ФНС, МСП, ФССП, банкротства, ЗСК, БКИ, обороты"),
    event(
      "checking",
      "Проверили ограничения",
      start + 3000,
      inactive ? `Нашли ограничение: ${company?.limitNote ?? "компания не действует"}` : "Банкротства, ликвидации и красной зоны ЗСК нет",
    ),
    event("checking", "Оцениваем заявку", start + 4500, "Считаем рейтинг и сколько платежей потянет бизнес"),
  ];
  const decidedAt = start + DECISION_AT_MS;
  const decided = now >= decidedAt;
  const decision = decided ? makeDecision(ctx, outcome, s, decidedAt) : null;
  if (decision) {
    if (outcome === "approved") plan.push(event("approved", "Одобрено", decidedAt, "Примите условия и подпишите договор"));
    else if (outcome === "counter_offer")
      plan.push(event("counter_offer", "Контрпредложение", decidedAt, "Можем дать меньше, чем вы просили"));
    else if (outcome === "manual_review")
      plan.push(event("checking", "На рассмотрении у специалиста", decidedAt, "Обычно до 1 рабочего дня"));
    else plan.push(event("rejected", "Отказ", decidedAt, "Эту сумму сейчас дать не можем"));

    const chosen = s.accepted !== undefined ? decision.offers[s.accepted] : undefined;
    if (chosen && s.acceptedAt) plan.push(event("signing", "Условия приняты", s.acceptedAt, terms(chosen)));
    if (s.signedAt) {
      plan.push(event("signing", "Договор подписан", s.signedAt, "Подписан кодом"));
      plan.push(event("issued", "Кредит выдан", s.signedAt + 1000, "Деньги на расчётном счёте"));
    }
  }
  if (s.cancelledAt) plan.push(event("rejected", "Заявка отозвана", s.cancelledAt, null));

  const history = plan
    .filter((e) => Date.parse(e.at) <= now || e === base.history[0])
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  const status = history[history.length - 1]?.status ?? base.status;

  let note: string;
  if (s.cancelledAt) note = "Заявка отозвана";
  else if (status === "issued") note = `Кредит выдан ${dayMonthNum(new Date(s.signedAt ?? now).toISOString())}, платёж ${rub(decision?.monthlyPayment ?? 0)} в месяц`;
  else if (status === "signing") note = "Условия приняты — подпишите договор кодом";
  else if (status === "approved" && decision) note = `Одобрено ${terms(decision.offers[0])} — примите условия`;
  else if (status === "counter_offer" && decision) note = `Можем дать ${decision.offers.map(terms).join(" или ")}`;
  else if (status === "rejected") note = "Эту сумму дать не можем — посмотрите, что одобрят";
  else if (decision?.outcome === "manual_review") note = "Заявку смотрит специалист — обычно до 1 рабочего дня";
  else note = "Банк проверяет данные компании — обычно пару минут";

  return { history, status, decision, note };
}

/** Мок работает только поверх заявок, которые сервер держит в «отправлена». */
const handled = (app: Application) => app.status === "submitted";

export function overlay(app: ApplicationDetails, companies: Company[], products: CreditProduct[]): ApplicationDetails {
  if (!handled(app)) return { ...app, decision: app.decision ?? null };
  const ctx: Context = { base: app, company: companies.find((c) => c.id === app.companyId), products };
  seen.set(app.id, ctx);
  applyOutcomeParam(app.id);
  const { history, status, decision, note } = compute(ctx);
  return { ...app, history, status, decision, note };
}

export function overlayList(apps: Application[], companies: Company[], products: CreditProduct[]): Application[] {
  return apps.map((app) => {
    if (!handled(app)) return app;
    const known = seen.get(app.id)?.base;
    // В списке нет истории — время отправки неизвестно; сценарий считаем от первого показа
    const base: ApplicationDetails = known ?? { ...app, history: [], decision: null };
    const { status, note } = compute({ base, company: companies.find((c) => c.id === app.companyId), products });
    return { ...app, status, note };
  });
}

// ---------- действия ----------

const reply = <T>(value: T, ms = 400) => new Promise<T>((resolve) => setTimeout(() => resolve(value), ms));
const fail = (err: ApiError, ms = 400) => new Promise<never>((_, reject) => setTimeout(() => reject(err), ms));

function current(id: string): { ctx: Context; c: Computed } | null {
  const ctx = seen.get(id);
  return ctx ? { ctx, c: compute(ctx) } : null;
}

function details(ctx: Context): ApplicationDetails {
  const { history, status, decision, note } = compute(ctx);
  return { ...ctx.base, history, status, decision, note };
}

const notFound = () => fail(new ApiError(404, "Заявка не найдена"));
const conflict = (text: string) => fail(new ApiError(409, text));

export function accept(id: string, offerIndex: number): Promise<ApplicationDetails> {
  const cur = current(id);
  if (!cur) return notFound();
  const { status, decision } = cur.c;
  if ((status !== "approved" && status !== "counter_offer") || !decision) return conflict("Сейчас принять условия нельзя");
  if (!decision.offers[offerIndex]) return fail(new ApiError(422, "Такого варианта нет"));
  patchState(id, { accepted: offerIndex, acceptedAt: Date.now() });
  return reply(details(cur.ctx));
}

export function signCode(id: string): Promise<SignCode> {
  const cur = current(id);
  if (!cur) return notFound();
  if (cur.c.status !== "signing") return conflict("Подписать можно после того, как приняты условия");
  const code = String(Math.floor(100_000 + Math.random() * 900_000));
  const expires = Date.now() + CODE_TTL_MS;
  patchState(id, { code, codeExpires: expires });
  return reply({ code, expiresAt: new Date(expires).toISOString() });
}

export function sign(id: string, code: string): Promise<ApplicationDetails> {
  const cur = current(id);
  if (!cur) return notFound();
  if (cur.c.status !== "signing") return conflict("Договор уже подписан или заявка закрыта");
  const s = stateOf(id);
  if (!s.code || !s.codeExpires || s.codeExpires < Date.now())
    return fail(new ApiError(422, "Код истёк — запросите новый", { code: "Код истёк — запросите новый" }));
  if (s.code !== code) return fail(new ApiError(422, "Неверный код", { code: "Неверный код" }));
  patchState(id, { signedAt: Date.now(), code: undefined, codeExpires: undefined });
  return reply(details(cur.ctx), 600);
}

const CANCELLABLE: ApplicationStatus[] = ["submitted", "checking", "counter_offer", "approved", "signing"];

export function cancel(id: string): Promise<ApplicationDetails> {
  const cur = current(id);
  if (!cur) return notFound();
  if (!CANCELLABLE.includes(cur.c.status)) return conflict("Заявку уже нельзя отозвать");
  patchState(id, { cancelledAt: Date.now() });
  return reply(details(cur.ctx));
}

/** Имитация SSE: отдаёт историю при подключении и при каждом новом событии, после issued/rejected — стоп. */
export function watch(id: string, onHistory: (history: ApplicationEvent[]) => void): () => void {
  let last = "";
  let timer: ReturnType<typeof setInterval> | undefined;
  const tick = () => {
    const ctx = seen.get(id);
    if (!ctx) return;
    const { history, status } = compute(ctx);
    const key = history.map((e) => e.at + e.label).join("|");
    if (key !== last) {
      last = key;
      onHistory(history);
    }
    if (status === "issued" || status === "rejected") clearInterval(timer);
  };
  timer = setInterval(tick, POLL_MS);
  tick();
  return () => clearInterval(timer);
}
