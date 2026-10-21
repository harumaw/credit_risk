import { Link, NavLink } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useCompanies } from "../../cabinet/CompanyContext";
import { HomeIcon } from "../Icons";
import { CompanySwitcher } from "./CompanySwitcher";

/** Шапка кабинета: разделы, переключатель компаний, профиль. Без компаний — только логотип и профиль. */
export function CabinetHeader() {
  const { state } = useAuth();
  const { companies, selected } = useCompanies();
  const hasCompanies = companies.status === "ready" && companies.data.length > 0;
  const user = state.status === "authenticated" ? state.user : null;
  const fullName = user ? `${user.first_name} ${user.last_name}` : "";

  return (
    <header className="site-header">
      <div className="container site-header-row">
        <Link to="/cabinet" className="brand" aria-label="Кредитный кабинет, главная кабинета">
          <span className="brand-mark">
            <HomeIcon size={19} color="#FFFFFF" strokeWidth={2.3} />
          </span>
          Кредитный кабинет
        </Link>
        {hasCompanies && (
          <nav className="site-nav" aria-label="Кабинет">
            <NavLink to="/cabinet" end className="nav-link">
              Главная
            </NavLink>
            <NavLink to="/cabinet/applications" className="nav-link">
              Заявки
            </NavLink>
            <Link to={selected ? `/cabinet/companies/${selected.id}#loans` : "/cabinet/companies"} className="nav-link">
              Кредиты
            </Link>
          </nav>
        )}
        <div className="header-actions">
          <CompanySwitcher />
          {user && (
            <Link to="/profile" className="user-avatar" aria-label={`Профиль: ${fullName}`} title={fullName}>
              {user.first_name.charAt(0).toUpperCase()}
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
