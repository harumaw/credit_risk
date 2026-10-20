import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

interface AuthLayoutProps {
  wide?: boolean;
  footer: ReactNode;
  children: ReactNode;
}

export function AuthLayout({ wide, footer, children }: AuthLayoutProps) {
  return (
    <div className="auth-screen">
      <div className={wide ? "auth-card wide" : "auth-card"}>
        <div className="auth-brand">Кредитный кабинет</div>
        <div className="auth-tagline">Кредиты для малого бизнеса</div>
        <nav className="tabs" aria-label="Вход или регистрация">
          <NavLink to="/login">Вход</NavLink>
          <NavLink to="/register">Регистрация</NavLink>
        </nav>
        {children}
        <div className="auth-foot">{footer}</div>
      </div>
    </div>
  );
}
