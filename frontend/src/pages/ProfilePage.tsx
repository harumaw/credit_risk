import type { UserStatus } from "../api/auth";
import { useAuth } from "../auth/AuthContext";
import { SiteFooter, SiteHeader } from "../components/SiteHeader";

const STATUS_LABELS: Record<UserStatus, string> = {
  active: "Подтверждён",
  pending_verification: "Ожидает подтверждения",
  blocked: "Заблокирован",
};

export function ProfilePage() {
  const { state } = useAuth();
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
      <SiteHeader />
      <div className="container">
        <h1 className="page-title">Здравствуйте, {user.first_name}</h1>
      </div>
      <section className="sheet">
        <div className="container">
          <div className="panel">
            <h2>Ваши данные</h2>
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
          </div>
          <div className="panel">
            <h2>Компании и заявки</h2>
            <p className="lead">Здесь появятся ваши ИП и компании, найденные по ИНН, и заявки на кредит.</p>
          </div>
        </div>
      </section>
      <SiteFooter />
    </>
  );
}
