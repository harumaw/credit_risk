import { useEffect, useId, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { listProducts, submitApplication, type CreditProduct } from "../../api/cabinet";
import { ApiError, type FieldErrors } from "../../api/client";
import { useCompanies } from "../../cabinet/CompanyContext";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { EmptyCabinet, Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import { ChevronLeft } from "../../components/Icons";
import { SiteFooter } from "../../components/SiteHeader";
import { rub, rubShort } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";

const PURPOSES = ["Пополнение оборотных средств", "Закупка товаров", "Покупка оборудования", "Рефинансирование"];
const OTHER = "Другое";
const DEFAULT_AMOUNT = 1_000_000;
const AMOUNT_STEP = 50_000;

const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max);

/** Аннуитетный платёж в месяц. */
function annuity(amount: number, months: number, yearRatePct: number): number {
  const r = yearRatePct / 100 / 12;
  return r === 0 ? amount / months : (amount * r) / (1 - Math.pow(1 + r, -months));
}

/** «300 тыс. – 50 млн ₽, 6–60 мес» */
function conditions(p: CreditProduct): string {
  return `${rubShort(p.minAmount)} – ${rubShort(p.maxAmount)}, ${p.minTermMonths}–${p.maxTermMonths} мес`;
}

/** Число из адреса или null. */
const numParam = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null);

/** Ключ идемпотентности: один на открытие формы, повторное нажатие не создаст вторую заявку. */
const newIdempotencyKey = () =>
  typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

export function ApplicationFormPage() {
  const { companies, selected, reload } = useCompanies();
  // Предзаполнение из «Что вам скорее одобрят»: ?company=&product=&amount=&term=
  const [params] = useSearchParams();
  const [idempotencyKey] = useState(newIdempotencyKey);
  const products = useAsync(listProducts, []);
  const navigate = useNavigate();
  const ids = { amount: useId(), term: useId(), purpose: useId() };

  const list = companies.status === "ready" ? companies.data : [];
  const catalog = products.status === "ready" ? products.data : [];

  const [companyId, setCompanyId] = useState<string | null>(() => params.get("company"));
  const [productCode, setProductCode] = useState<string | null>(() => params.get("product"));
  const [amount, setAmount] = useState<number | null>(() => numParam(params.get("amount")));
  const [term, setTerm] = useState(() => numParam(params.get("term")) ?? 12);
  const [purpose, setPurpose] = useState(PURPOSES[0]);
  const [purposeOther, setPurposeOther] = useState("");
  const [consentPd, setConsentPd] = useState(false);
  const [consentBki, setConsentBki] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Компания по умолчанию — выбранная в шапке, продукт — первый в каталоге
  const company = list.find((c) => c.id === companyId) ?? selected ?? list[0] ?? null;
  const product = catalog.find((p) => p.code === productCode) ?? catalog[0] ?? null;

  // Сумма по умолчанию — предварительный лимит компании, если он есть
  useEffect(() => {
    if (amount === null && company)
      setAmount(company.limit && company.limit > 0 ? Math.floor(company.limit / AMOUNT_STEP) * AMOUNT_STEP : DEFAULT_AMOUNT);
  }, [amount, company]);

  const sum = product ? clamp(amount ?? DEFAULT_AMOUNT, product.minAmount, product.maxAmount) : 0;
  const months = product ? clamp(term, product.minTermMonths, product.maxTermMonths) : term;
  const payment = product ? annuity(sum, months, product.rate) : 0;
  const purposeText = purpose === OTHER ? purposeOther.trim() : purpose;
  const overLimit = company?.limit != null && sum > company.limit;

  const clearError = (key: string) => setFieldErrors((prev) => ({ ...prev, [key]: "" }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!company || !product) return;
    const errors: FieldErrors = {};
    if (purposeText.length < 3) errors.purpose = "Опишите, на что нужны деньги";
    if (!consentPd) errors.consentPersonalData = "Нужно согласие";
    if (!consentBki) errors.consentBki = "Нужно согласие";
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      setError(null);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const form = {
        companyId: company.id,
        productCode: product.code,
        amount: sum,
        termMonths: months,
        purpose: purposeText,
        consentPersonalData: consentPd,
        consentBki,
      };
      const app = await submitApplication(form, idempotencyKey);
      navigate(`/cabinet/applications/${app.id}`, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        setError(Object.keys(err.fieldErrors).length ? "Проверьте поля формы" : err.message);
      } else {
        setError("Не удалось отправить заявку");
      }
      setSubmitting(false);
    }
  }

  let body;
  if (companies.status === "error") body = <SheetStatus error={companies.message} onRetry={reload} />;
  else if (products.status === "error") body = <SheetStatus error={products.message} onRetry={products.reload} />;
  else if (companies.status === "loading" || products.status === "loading") body = <SheetStatus />;
  else if (!list.length) body = <EmptyCabinet />;
  else if (!product || !company) body = <SheetStatus error="Нет доступных кредитных продуктов" />;
  else
    body = (
      <form className="apply" onSubmit={onSubmit} noValidate>
        <div className="apply-form">
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          <fieldset className="apply-block">
            <legend>Компания</legend>
            <div className="choice-list">
              {list.map((c) => (
                <label key={c.id} className={`choice ${c.id === company.id ? "is-on" : ""}`}>
                  <input
                    type="radio"
                    name="company"
                    checked={c.id === company.id}
                    onChange={() => {
                      setCompanyId(c.id);
                      clearError("companyId");
                    }}
                  />
                  <span className="choice-title">{c.name}</span>
                  <span className="choice-note">
                    ИНН {c.inn}
                    {c.limit != null ? ` · лимит ${rubShort(c.limit)}` : ""}
                  </span>
                </label>
              ))}
            </div>
            {fieldErrors.companyId && <div className="error">{fieldErrors.companyId}</div>}
          </fieldset>

          <fieldset className="apply-block">
            <legend>Кредит</legend>
            <div className="choice-list">
              {catalog.map((p) => (
                <label key={p.code} className={`choice ${p.code === product.code ? "is-on" : ""}`}>
                  <input
                    type="radio"
                    name="product"
                    checked={p.code === product.code}
                    onChange={() => {
                      setProductCode(p.code);
                      clearError("productCode");
                    }}
                  />
                  <span className="choice-title">{p.name}</span>
                  <span className="choice-note">
                    {conditions(p)} · от {p.rate.toLocaleString("ru-RU")}%
                  </span>
                </label>
              ))}
            </div>
            {fieldErrors.productCode && <div className="error">{fieldErrors.productCode}</div>}
          </fieldset>

          <fieldset className="apply-block">
            <legend>Сумма и срок</legend>
            <div className="calc-slider">
              <label htmlFor={ids.amount}>
                Сумма <output htmlFor={ids.amount}>{rub(sum)}</output>
              </label>
              <input
                id={ids.amount}
                type="range"
                min={product.minAmount}
                max={product.maxAmount}
                step={AMOUNT_STEP}
                value={sum}
                aria-invalid={fieldErrors.amount ? true : undefined}
                onChange={(e) => {
                  setAmount(Number(e.target.value));
                  clearError("amount");
                }}
              />
              <div className="calc-range">
                <span>{rubShort(product.minAmount)}</span>
                <span>{rubShort(product.maxAmount)}</span>
              </div>
              {fieldErrors.amount ? (
                <div className="error">{fieldErrors.amount}</div>
              ) : (
                overLimit && (
                  <div className="hint">
                    Больше предварительного лимита компании ({rubShort(company.limit!)}) — банк может предложить
                    меньшую сумму или другой срок
                  </div>
                )
              )}
            </div>
            <div className="calc-slider">
              <label htmlFor={ids.term}>
                Срок <output htmlFor={ids.term}>{months} мес</output>
              </label>
              <input
                id={ids.term}
                type="range"
                min={product.minTermMonths}
                max={product.maxTermMonths}
                step={1}
                value={months}
                aria-invalid={fieldErrors.termMonths ? true : undefined}
                onChange={(e) => {
                  setTerm(Number(e.target.value));
                  clearError("termMonths");
                }}
              />
              <div className="calc-range">
                <span>{product.minTermMonths} мес</span>
                <span>{product.maxTermMonths} мес</span>
              </div>
              {fieldErrors.termMonths && <div className="error">{fieldErrors.termMonths}</div>}
            </div>
          </fieldset>

          <fieldset className="apply-block">
            <legend>Цель кредита</legend>
            <div className="segmented segmented-sm segmented-wrap" role="group" aria-label="Цель кредита">
              {[...PURPOSES, OTHER].map((p) => (
                <button
                  key={p}
                  type="button"
                  aria-pressed={p === purpose}
                  onClick={() => {
                    setPurpose(p);
                    clearError("purpose");
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
            {purpose === OTHER && (
              <div className="field">
                <label htmlFor={ids.purpose}>На что нужны деньги</label>
                <textarea
                  id={ids.purpose}
                  rows={3}
                  maxLength={500}
                  value={purposeOther}
                  aria-invalid={fieldErrors.purpose ? true : undefined}
                  onChange={(e) => {
                    setPurposeOther(e.target.value);
                    clearError("purpose");
                  }}
                />
              </div>
            )}
            {fieldErrors.purpose && <div className="error">{fieldErrors.purpose}</div>}
          </fieldset>

          <fieldset className="apply-block">
            <legend>Согласия</legend>
            <label className="check">
              <input
                type="checkbox"
                checked={consentPd}
                aria-invalid={fieldErrors.consentPersonalData ? true : undefined}
                onChange={(e) => {
                  setConsentPd(e.target.checked);
                  clearError("consentPersonalData");
                }}
              />
              <span>Согласен на обработку персональных данных</span>
            </label>
            {fieldErrors.consentPersonalData && <div className="error">{fieldErrors.consentPersonalData}</div>}
            <label className="check">
              <input
                type="checkbox"
                checked={consentBki}
                aria-invalid={fieldErrors.consentBki ? true : undefined}
                onChange={(e) => {
                  setConsentBki(e.target.checked);
                  clearError("consentBki");
                }}
              />
              <span>Согласен на запрос кредитной истории компании и руководителя в бюро кредитных историй</span>
            </label>
            {fieldErrors.consentBki && <div className="error">{fieldErrors.consentBki}</div>}
          </fieldset>
        </div>

        <aside className="calc-result apply-summary">
          <div>
            <small>{company.name}</small>
            <div className="apply-summary-product">{product.name}</div>
          </div>
          <div>
            <small>Примерный платёж в месяц</small>
            <b>{rub(payment)}</b>
          </div>
          <div className="apply-summary-row">
            <span>
              <small>Сумма</small>
              {rub(sum)}
            </span>
            <span>
              <small>Срок</small>
              {months} мес
            </span>
          </div>
          <p className="calc-note">
            Платёж посчитан по ставке {product.rate.toLocaleString("ru-RU")}% годовых. Итоговые условия банк покажет в
            решении по заявке.
          </p>
          <button type="submit" className="btn btn-accent btn-lg btn-block" disabled={submitting}>
            {submitting ? "Отправляем…" : "Отправить заявку"}
          </button>
        </aside>
      </form>
    );

  return (
    <>
      <CabinetHeader />
      <section className="container page-head page-head-col">
        <Link to="/cabinet/applications" className="back-link">
          <ChevronLeft size={14} strokeWidth={2.4} />
          Заявки
        </Link>
        <h1>Новая заявка</h1>
        <p className="page-head-sub">Данные компании подставим сами — выберите кредит, сумму и срок.</p>
      </section>
      <Sheet>{body}</Sheet>
      <SiteFooter />
    </>
  );
}
