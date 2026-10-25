import { Link, useSearchParams } from "react-router-dom";

import { CheckIcon } from "../components/Icons";
import { SiteFooter, SiteHeader } from "../components/SiteHeader";
import { findProduct, PRODUCTS, type Product } from "../lib/products";

const STEPS = [
  { title: "Компания", text: "добавьте по ИНН — данные подтянем из реестров сами" },
  { title: "Заявка", text: "сумма, срок, цель и два согласия — около 2 минут" },
  { title: "Решение", text: "через несколько секунд: одобрение, другой вариант или причина отказа с советом" },
  { title: "Подпись", text: "кодом прямо в кабинете — деньги на счёт" },
];

function ProductCards({ items }: { items: Product[] }) {
  return (
    <div className="card-grid">
      {items.map((p) => (
        <Link key={p.slug} to={`/credits?product=${p.slug}`} className="card">
          <strong>{p.title}</strong>
          <span>{p.cardNote}</span>
          <span className="more">Подробнее</span>
        </Link>
      ))}
    </div>
  );
}

function ProductView({ product }: { product: Product }) {
  // Без входа RequireAuth отправит на вход и вернёт сюда же (?next=)
  const applyHref = `/cabinet/applications/new?product=${product.code}`;
  return (
    <>
      <section className="container product-head">
        <nav className="product-tabs" aria-label="Кредиты">
          {PRODUCTS.map((p) => (
            <Link
              key={p.slug}
              to={`/credits?product=${p.slug}`}
              className="product-tab"
              aria-current={p.slug === product.slug ? "page" : undefined}
            >
              {p.short}
            </Link>
          ))}
        </nav>
        <h1>{product.title}</h1>
        <p className="product-lead">{product.lead}</p>
        <div className="btn-row">
          <Link to={applyHref} className="btn btn-accent btn-lg">
            Подать заявку
          </Link>
          {product.calc && (
            <Link to="/calculator" className="btn btn-dark btn-lg">
              Рассчитать платёж
            </Link>
          )}
        </div>
        <small className="product-hint">
          Без аккаунта — сначала вход или регистрация, потом сразу форма заявки с этим кредитом.
        </small>
      </section>

      <section className="sheet product-sheet">
        <div className="container product-body">
          <div className="product-facts">
            {product.facts.map((f) => (
              <div key={f.label} className="product-fact">
                <span className="product-fact-label">{f.label}</span>
                <strong>{f.value}</strong>
                {f.note && <span>{f.note}</span>}
              </div>
            ))}
          </div>

          <div className="product-example">
            <span>Пример</span>
            <p>{product.example}</p>
          </div>

          <div className="product-cols">
            <div>
              <h2>Кому подходит</h2>
              <ul className="product-fit">
                {product.fit.map((x) => (
                  <li key={x}>
                    <CheckIcon size={18} strokeWidth={2.6} />
                    {x}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h2>Как получить</h2>
              <ol className="product-steps">
                {STEPS.map((s, i) => (
                  <li key={s.title}>
                    <span className="product-step-num" aria-hidden="true">
                      {i + 1}
                    </span>
                    <span>
                      <strong>{s.title}</strong> — {s.text}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div>
            <h2>Другие кредиты</h2>
            <ProductCards items={PRODUCTS.filter((p) => p.slug !== product.slug)} />
          </div>
        </div>
      </section>
    </>
  );
}

/** Кредиты: страница продукта (?product=<slug>) или список всех. */
export function CreditsPage() {
  const [params] = useSearchParams();
  const product = findProduct(params.get("product"));

  return (
    <>
      <SiteHeader />
      {product ? (
        <ProductView product={product} />
      ) : (
        <>
          <div className="container">
            <h1 className="page-title">Кредиты для бизнеса</h1>
          </div>
          <section className="sheet">
            <div className="container">
              <ProductCards items={PRODUCTS} />
            </div>
          </section>
        </>
      )}
      <SiteFooter />
    </>
  );
}
