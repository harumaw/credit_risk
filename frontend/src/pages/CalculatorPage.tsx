import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { SiteFooter, SiteHeader } from "../components/SiteHeader";
import { PRODUCTS } from "../lib/products";

// Ставка для примера: реальные ставки по продуктам придут с бэкенда (credit_products.base_rate)
const DEMO_RATE = 24;

const CALC_PRODUCTS = PRODUCTS.filter((p) => p.calc);

const rub = (n: number) => `${Math.round(n).toLocaleString("ru-RU")} ₽`;
const short = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toLocaleString("ru-RU")} млн ₽` : `${n / 1000} тыс. ₽`;

/** Аннуитетный платёж в месяц. */
function annuity(amount: number, months: number, yearRatePct: number): number {
  const r = yearRatePct / 100 / 12;
  return (amount * r) / (1 - Math.pow(1 + r, -months));
}

const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max);

export function CalculatorPage() {
  const [slug, setSlug] = useState(CALC_PRODUCTS[0].slug);
  const [amountRaw, setAmount] = useState(3_000_000);
  const [termRaw, setTerm] = useState(24);
  const amountId = useId();
  const termId = useId();

  const product = CALC_PRODUCTS.find((p) => p.slug === slug) ?? CALC_PRODUCTS[0];
  const limits = product.calc!;
  const amount = clamp(amountRaw, limits.minAmount, limits.maxAmount);
  const term = clamp(termRaw, limits.minTerm, limits.maxTerm);
  const payment = annuity(amount, term, DEMO_RATE);
  const overpay = payment * term - amount;

  return (
    <>
      <SiteHeader />
      <div className="container">
        <h1 className="page-title">Калькулятор кредита</h1>
      </div>
      <section className="sheet">
        <div className="container calc">
          <div className="calc-panel" style={{ color: "#111111" }}>
            <div className="segmented" role="group" aria-label="Кредит" style={{ alignSelf: "flex-start" }}>
              {CALC_PRODUCTS.map((p) => (
                <button key={p.slug} type="button" aria-pressed={p.slug === slug} onClick={() => setSlug(p.slug)}>
                  {p.title.replace("Кредит на оборотные средства", "Оборотные")}
                </button>
              ))}
            </div>
            <div className="calc-slider">
              <label htmlFor={amountId}>
                Сумма <output htmlFor={amountId}>{rub(amount)}</output>
              </label>
              <input
                id={amountId}
                type="range"
                min={limits.minAmount}
                max={limits.maxAmount}
                step={100_000}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
              />
              <div className="calc-range">
                <span>{short(limits.minAmount)}</span>
                <span>{short(limits.maxAmount)}</span>
              </div>
            </div>
            <div className="calc-slider">
              <label htmlFor={termId}>
                Срок <output htmlFor={termId}>{term} мес</output>
              </label>
              <input
                id={termId}
                type="range"
                min={limits.minTerm}
                max={limits.maxTerm}
                step={1}
                value={term}
                onChange={(e) => setTerm(Number(e.target.value))}
              />
              <div className="calc-range">
                <span>{limits.minTerm} мес</span>
                <span>{limits.maxTerm} мес</span>
              </div>
            </div>
          </div>

          <div className="calc-result">
            <div>
              <small>Платёж в месяц</small>
              <b>{rub(payment)}</b>
            </div>
            <div>
              <small>Переплата за весь срок</small>
              <div style={{ fontSize: 20, fontWeight: 800, marginTop: 4 }}>{rub(overpay)}</div>
            </div>
            <p className="calc-note">
              Ставка {DEMO_RATE}% годовых — для примера. Точные условия и предварительное решение покажем после
              регистрации, без запроса в кредитное бюро.
            </p>
            <Link to="/register" className="btn btn-accent btn-lg btn-block">
              Подать заявку
            </Link>
          </div>
        </div>
      </section>
      <SiteFooter />
    </>
  );
}
