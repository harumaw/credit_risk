import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { SiteHeader } from "./SiteHeader";

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  wide?: boolean;
  footer: ReactNode;
  children: ReactNode;
}

export function AuthLayout({ title, subtitle, wide, footer, children }: AuthLayoutProps) {
  return (
    <>
      <SiteHeader />
      <main className="auth-main">
        <div className={wide ? "auth-card wide" : "auth-card"}>
          <h1>{title}</h1>
          <p className="auth-sub">{subtitle}</p>
          <nav className="auth-tabs" aria-label="Вход или регистрация">
            <NavLink to="/login">Вход</NavLink>
            <NavLink to="/register">Регистрация</NavLink>
          </nav>
          {children}
          {footer}
        </div>
      </main>
    </>
  );
}
