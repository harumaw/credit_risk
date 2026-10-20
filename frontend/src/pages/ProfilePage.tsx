import type { UserStatus } from "../api/auth";
import { useAuth } from "../auth/AuthContext";

const STATUS_LABELS: Record<UserStatus, string> = {
  active: "Подтверждён",
  pending_verification: "Ожидает подтверждения",
  blocked: "Заблокирован",
};

export function ProfilePage() {
  const { state, logout } = useAuth();
  if (state.status !== "authenticated") return null;
  const { user } = state;
  const fullName = [user.last_name, user.first_name, user.middle_name].filter(Boolean).join(" ");

  const rows: [string, string][] = [
    ["ФИО", fullName],
    ["ИНН", user.inn_fl ?? "—"],
    ["Email", user.email ?? "—"],
    ["Телефон", user.phone ?? "—"],
  ];

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">К</span>Кредитный кабинет
        </div>
        <div className="spacer" />
        <div className="account">
          <span>{user.first_name}</span>
          <span className="avatar" aria-hidden="true">
            {user.first_name.charAt(0).toUpperCase()}
          </span>
          <button type="button" className="btn btn-link" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>

      <main>
        <h1>Профиль</h1>
        <section className="panel">
          <div className="panel-head">
            <h2>Ваши данные</h2>
          </div>
          <dl className="details">
            {rows.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
            <div>
              <dt>Статус</dt>
              <dd>
                <span className="badge">{STATUS_LABELS[user.status]}</span>
              </dd>
            </div>
          </dl>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>Компании и заявки</h2>
          </div>
          <div className="panel-body">Здесь появятся ваши ИП и компании, найденные по ИНН, и заявки на кредит.</div>
        </section>
      </main>
    </>
  );
}
