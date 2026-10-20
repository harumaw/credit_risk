import { useState } from "react";
import { Link } from "react-router-dom";

import { CalculatorIcon, ClockIcon, HomeIcon, TrendIcon } from "../components/Icons";
import { SiteFooter, SiteHeader } from "../components/SiteHeader";
import { PRODUCTS, type CompanyKind } from "../lib/products";

type Audience = "all" | CompanyKind;

const AUDIENCES: { id: Audience; label: string }[] = [
  { id: "all", label: "Для всех" },
  { id: "ip", label: "Для ИП" },
  { id: "llc", label: "Для ООО" },
];

const STEPS = [
  { title: "Регистрация", text: "ФИО, ИНН и email — ваши ИП и компании найдём по ИНН" },
  { title: "Выбор кредита", text: "Сумма, срок и шансы на одобрение — заранее" },
  { title: "Заявка", text: "Подтверждаете то, что банк уже знает, и подписываете в кабинете" },
  { title: "Решение", text: "Предложение, контрпредложение или понятная причина отказа" },
];

export function LandingPage() {
  const [audience, setAudience] = useState<Audience>("all");
  const products = PRODUCTS.filter((p) => audience === "all" || p.forKinds.includes(audience));

  return (
    <>
      <SiteHeader />

      <section className="container bento" aria-label="Главное">
        <div className="tile tile-hero">
          <h1>Кредит для бизнеса до 50 млн ₽ без залога</h1>
          <p>Предварительное решение — онлайн, без похода в банк</p>
          <Link to="/register" className="btn btn-accent btn-lg">
            Оформить заявку
          </Link>
          <div className="tile-art" aria-hidden="true">
            <div className="tile-art-back" />
            <div className="tile-art-front">
              <span className="brand-mark" style={{ width: 44, height: 44, borderRadius: 14 }}>
                <HomeIcon size={24} color="#FFFFFF" strokeWidth={2.2} />
              </span>
              <small style={{ marginTop: 8 }}>Предварительный лимит</small>
              <b>2 750 000 ₽</b>
              <div className="progress">
                <span style={{ width: "62%" }} />
              </div>
              <small>Заявка: проверяем данные</small>
            </div>
          </div>
        </div>

        <Link to="/credits?product=overdraft" className="tile tile-side">
          <strong>Овердрафт для клиентов банка</strong>
          <span>Платежи, даже когда на счёте ноль</span>
          <span className="tile-icon tile-icon-lg">
            <ClockIcon size={56} color="#EF3B2D" strokeWidth={1.8} />
          </span>
        </Link>

        <Link to="/credits?product=credit-line" className="tile tile-row tile-pink">
          <strong>Кредитная линия</strong>
          <span className="tile-icon">
            <TrendIcon size={30} color="#EF3B2D" strokeWidth={1.9} />
          </span>
        </Link>

        <Link to="/calculator" className="tile tile-row tile-gray">
          <span>
            <strong>Калькулятор платежа</strong>
            <small>Сумма, срок и платёж за минуту</small>
          </span>
          <span className="tile-icon">
            <CalculatorIcon size={30} color="#EF3B2D" strokeWidth={1.9} />
          </span>
        </Link>

        <Link to="/credits?product=state-support" className="tile tile-row tile-blue">
          <strong>Льготный кредит по госпрограмме</strong>
        </Link>
      </section>

      <section className="sheet" id="credits">
        <div className="container">
          <div className="sheet-head">
            <h2>Кредиты для бизнеса</h2>
            <div className="segmented" role="group" aria-label="Для кого">
              {AUDIENCES.map((a) => (
                <button key={a.id} type="button" aria-pressed={audience === a.id} onClick={() => setAudience(a.id)}>
                  {a.label}
                </button>
              ))}
            </div>
          </div>
          <div className="card-grid">
            {products.map((p) => (
              <Link key={p.slug} to={`/credits?product=${p.slug}`} className="card">
                <strong>{p.title}</strong>
                <span>{p.cardNote}</span>
                <span className="more">Подробнее</span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="sheet" id="how">
        <div className="container">
          <div className="sheet-head">
            <h2>Как получить кредит</h2>
          </div>
          <ol className="steps" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {STEPS.map((s, i) => (
              <li key={s.title} className="step">
                <span className="step-num">{i + 1}</span>
                <strong>{s.title}</strong>
                <span>{s.text}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <SiteFooter />
    </>
  );
}
