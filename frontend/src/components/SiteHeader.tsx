import { useEffect, useId, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { PRODUCTS } from "../lib/products";
import { ChevronDown, HomeIcon } from "./Icons";

function CreditsMenu() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const location = useLocation();

  // Закрываем при переходе, клике мимо и по Escape
  useEffect(() => setOpen(false), [location]);
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="dropdown" ref={rootRef}>
      <button
        type="button"
        className="nav-link"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        Кредиты
        <ChevronDown size={14} strokeWidth={2.4} />
      </button>
      {open && (
        <div className="dropdown-menu" id={menuId}>
          {PRODUCTS.map((p) => (
            <Link key={p.slug} to={`/credits?product=${p.slug}`} className="dropdown-item">
              <strong>{p.title}</strong>
              <span>{p.menuNote}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function SiteHeader() {
  const { state, logout } = useAuth();

  return (
    <header className="site-header">
      <div className="container site-header-row">
        <Link to="/" className="brand" aria-label="Кредитный кабинет, на главную">
          <span className="brand-mark">
            <HomeIcon size={19} color="#FFFFFF" strokeWidth={2.3} />
          </span>
          Кредитный кабинет
        </Link>
        <nav className="site-nav" aria-label="Основное меню">
          <CreditsMenu />
          <NavLink to="/calculator" className="nav-link">
            Калькулятор
          </NavLink>
          <Link to="/#how" className="nav-link">
            Как получить
          </Link>
        </nav>
        <div className="header-actions">
          {state.status === "authenticated" ? (
            <>
              <Link to="/profile" className="btn btn-dark">
                Кабинет
              </Link>
              <button type="button" className="btn btn-accent" onClick={logout}>
                Выйти
              </button>
            </>
          ) : (
            <>
              <Link to="/register" className="btn btn-dark">
                Регистрация
              </Link>
              <Link to="/login" className="btn btn-accent">
                Войти
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return <footer className="site-footer">Прототип для хакатона. Все данные синтетические.</footer>;
}
