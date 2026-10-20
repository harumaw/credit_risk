import { Link, useSearchParams } from "react-router-dom";

import { SiteFooter, SiteHeader } from "../components/SiteHeader";
import { findProduct, PRODUCTS } from "../lib/products";

/** Заглушка: все пункты меню «Кредиты» ведут сюда, страницы продуктов появятся позже. */
export function CreditsPage() {
  const [params] = useSearchParams();
  const product = findProduct(params.get("product"));

  return (
    <>
      <SiteHeader />
      <div className="container">
        <h1 className="page-title">{product ? product.title : "Кредиты для бизнеса"}</h1>
      </div>
      <section className="sheet">
        <div className="container">
          <div className="panel">
            <h2>Страница в разработке</h2>
            <p className="lead">
              {product
                ? `${product.cardNote}. Подробные условия и подача заявки появятся здесь.`
                : "Скоро здесь появятся подробные условия по каждому кредиту."}
            </p>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 48 }}>
            <Link to="/register" className="btn btn-accent btn-lg">
              Зарегистрироваться
            </Link>
            <Link to="/calculator" className="btn btn-dark btn-lg">
              Рассчитать платёж
            </Link>
          </div>
          <div className="card-grid">
            {PRODUCTS.filter((p) => p.slug !== product?.slug).map((p) => (
              <Link key={p.slug} to={`/credits?product=${p.slug}`} className="card">
                <strong>{p.title}</strong>
                <span>{p.cardNote}</span>
                <span className="more">Подробнее</span>
              </Link>
            ))}
          </div>
        </div>
      </section>
      <SiteFooter />
    </>
  );
}
