import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import type { AppStatus, ApplicationRow, Decision, Fact, Filters, ModelInfo, SegmentRule } from "../api/admin";
import { SiteFooter } from "../components/SiteHeader";
import { rubShort } from "../lib/format";
import { useAdminAuth } from "./AdminAuth";

export const DECISIONS: { value: Decision; label: string }[] = [
  { value: "approve", label: "Одобрено" },
  { value: "counter_offer", label: "Контрпредложение" },
  { value: "manual_review", label: "Ручной разбор" },
  { value: "decline", label: "Отказ" },
];

export const FACT_LABEL: Record<Fact, string> = { default: "дефолт", no_default: "нет дефолта", unknown: "нет данных" };

const GRADE_TONE: Record<string, string> = { A: "g-a", B: "g-b", C: "g-c", D: "g-d", E: "g-e" };
/** Решение по грейду — та же матрица, что на бэкенде (app/credit/recommendation.py). */
export const GRADE_DECISION: Record<string, string> = {
  A: "Одобрено",
  B: "Одобрено",
  C: "Ручной разбор",
  D: "Отказ",
  E: "Отказ",
};

export const num = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "—" : v.toLocaleString("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: digits });
export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toLocaleString("ru-RU", { maximumFractionDigits: digits })}%`;
export const int = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toLocaleString("ru-RU"));
export const date = (iso: string | null | undefined) => (iso ? iso.slice(0, 10).split("-").reverse().join(".") : "—");
export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" }) : "—";

export function GradeChip({ grade }: { grade: string | null }) {
  if (!grade) return <span className="muted">—</span>;
  return <span className={`grade ${GRADE_TONE[grade] ?? ""}`}>{grade}</span>;
}

export function DecisionChip({ decision, label, accepted = false }: { decision: string | null; label: string | null; accepted?: boolean }) {
  if (!decision) return <span className="muted">без скоринга</span>;
  // Принятое контрпредложение — уже одобрение: зелёный, как «Одобрено»
  const tone =
    decision === "approve" || (decision === "counter_offer" && accepted)
      ? "chip-ok"
      : decision === "decline" ? "chip-act" : decision === "manual_review" ? "chip-wait" : "chip-offer";
  return <span className={`chip ${tone}`}>{label}</span>;
}

/** Статусы заявки в БД — как в app/services/admin.py STATUS_LABEL. */
export const APP_STATUSES: { value: string; label: string }[] = [
  { value: "submitted", label: "Отправлена" },
  { value: "scoring", label: "Скоринг" },
  { value: "manual_review", label: "Ручной разбор" },
  { value: "approved", label: "Одобрена" },
  { value: "offer_accepted", label: "Условия приняты" },
  { value: "contract_signed", label: "Договор подписан" },
  { value: "issued", label: "Выдан" },
  { value: "declined", label: "Отказ" },
  { value: "cancelled", label: "Отменена клиентом" },
];

const STATUS_TONE: Record<string, string> = {
  submitted: "chip-wait",
  scoring: "chip-wait",
  data_collection: "chip-wait",
  manual_review: "chip-offer",
  approved: "chip-ok",
  offer_accepted: "chip-ok",
  contract_signed: "chip-ok",
  issued: "chip-ok",
  declined: "chip-act",
  cancelled: "chip-no",
  draft: "chip-draft",
};

export function AppStatusChip({ status }: { status: AppStatus }) {
  return <span className={`chip ${STATUS_TONE[status.code] ?? "chip-draft"}`}>{status.label}</span>;
}

export const money = (v: number | null | undefined) => (v === null || v === undefined ? "—" : rubShort(v));

/** Условия: «1,5 млн ₽ · 12 мес · 18%». */
export function terms(amount: number | null, term: number | null, rate?: number | null): string {
  if (amount === null && term === null) return "—";
  const r = rate !== null && rate !== undefined ? `${rate.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}%` : null;
  return [money(amount), term !== null ? `${term} мес` : null, r]
    .filter(Boolean)
    .join(" · ");
}

export function ApplicationsTable({ rows, company = true }: { rows: ApplicationRow[]; company?: boolean }) {
  if (!rows.length) return <p className="muted">Заявок нет.</p>;
  return (
    <div className="panel-scroll">
      <table className="table table-wide adm-table">
        <thead>
          <tr>
            <th>Заявка</th>
            {company && <th>Компания</th>}
            <th>Запрошено</th>
            <th>Статус</th>
            <th>Решение</th>
            <th>Одобрено</th>
            <th className="num">Балл</th>
            <th>Грейд</th>
            <th className="num">PD</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <Link to={`/adminuser/applications/${r.id}`} className="table-company">
                  № {r.number}
                </Link>
                <div className="table-sub" title={r.product}>
                  {dateTime(r.submittedAt ?? r.createdAt)}
                </div>
              </td>
              {company && (
                <td>
                  <Link to={`/adminuser/companies/${r.companyId}`}>{r.companyName}</Link>
                  <div className="table-sub">ИНН {r.inn}</div>
                </td>
              )}
              <td>{terms(r.requestedAmount, r.requestedTerm)}</td>
              <td>
                <AppStatusChip status={r.status} />
              </td>
              <td>{r.decision ? <DecisionChip decision={r.decision} label={r.decisionLabel} accepted={r.offerAccepted} /> : <span className="muted">ещё нет</span>}</td>
              <td>{r.approvedAmount !== null ? terms(r.approvedAmount, r.approvedTerm, r.rate) : "—"}</td>
              <td className="num strong">{num(r.score)}</td>
              <td>
                <GradeChip grade={r.grade} />
              </td>
              <td className="num">{pct(r.pd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FactCell({ fact }: { fact: Fact }) {
  return <span className={fact === "default" ? "is-bad" : fact === "no_default" ? "" : "muted"}>{FACT_LABEL[fact]}</span>;
}

export function AdminShell({ children }: { children: ReactNode }) {
  const { state, logout } = useAdminAuth();
  const staff = state.status === "authenticated" ? state.staff : null;
  return (
    <>
      <header className="site-header">
        <div className="container site-header-row">
          <Link to="/adminuser" className="brand">
            <span className="brand-mark" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round">
                <path d="M4 18 12 6l8 12" />
              </svg>
            </span>
            Кредитный кабинет <span className="admin-badge">ADMIN</span>
          </Link>
          <nav className="site-nav" aria-label="Разделы администратора">
            <NavLink to="/adminuser" end className="nav-link">
              Компании
            </NavLink>
            <NavLink to="/adminuser/applications" className="nav-link">
              Заявки
            </NavLink>
            <NavLink to="/adminuser/analysis" className="nav-link">
              Выборки и узкие места
            </NavLink>
            <NavLink to="/adminuser/models" className="nav-link">
              Модели
            </NavLink>
          </nav>
          {staff && (
            <div className="header-actions">
              <span className="header-user">{staff.login}</span>
              <button type="button" className="btn btn-dark" onClick={logout}>
                Выйти
              </button>
            </div>
          )}
        </div>
      </header>
      {children}
      <SiteFooter />
    </>
  );
}

export function Status({ error, onRetry }: { error?: string; onRetry?: () => void }) {
  if (!error) return <div className="sheet-status">Загрузка…</div>;
  return (
    <div className="sheet-status" role="alert">
      {error}
      {onRetry && (
        <button type="button" className="btn btn-dark" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}

interface FilterBarProps {
  value: Filters;
  onChange: (f: Filters) => void;
  models: ModelInfo[];
  segments: SegmentRule[];
  /** Расширенные поля: балл, даты, пограничные, стоп-факторы */
  extended?: boolean;
}

/** Фильтры компаний — одни и те же для таблицы, выборок и срезов. */
export function FilterBar({ value, onChange, models, segments, extended }: FilterBarProps) {
  const set = (k: keyof Filters, v: string) => onChange({ ...value, [k]: v || undefined });
  const modelNames = [...new Set(models.map((m) => m.name))];
  return (
    <div className="adm-filters">
      <label className="adm-field adm-field-wide">
        Поиск
        <input type="search" placeholder="ИНН или название" value={value.q ?? ""} onChange={(e) => set("q", e.target.value)} />
      </label>
      <label className="adm-field">
        Решение
        <select value={value.decision ?? ""} onChange={(e) => set("decision", e.target.value)}>
          <option value="">все</option>
          {DECISIONS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
          <option value="none">без скоринга</option>
        </select>
      </label>
      <label className="adm-field">
        Сегмент
        <select value={value.segment ?? ""} onChange={(e) => set("segment", e.target.value)}>
          <option value="">все</option>
          {segments.map((s) => (
            <option key={s.code} value={s.code}>
              {s.code}
            </option>
          ))}
        </select>
      </label>
      <label className="adm-field">
        Модель
        <select value={value.model ?? ""} onChange={(e) => set("model", e.target.value)}>
          <option value="">любая</option>
          {modelNames.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label className="adm-field">
        Грейд
        <select value={value.grade ?? ""} onChange={(e) => set("grade", e.target.value)}>
          <option value="">любой</option>
          <option value="A,B">A–B</option>
          {["A", "B", "C", "D", "E"].map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
          <option value="D,E">D–E</option>
        </select>
      </label>
      <label className="adm-field">
        Факт дефолта
        <select value={value.fact ?? ""} onChange={(e) => set("fact", e.target.value)}>
          <option value="">все</option>
          <option value="default">был</option>
          <option value="no_default">не было</option>
          <option value="unknown">нет данных</option>
        </select>
      </label>
      <label className="adm-field">
        Источник
        <select value={value.source ?? ""} onChange={(e) => set("source", e.target.value)}>
          <option value="">все</option>
          <option value="live">клиенты кабинета</option>
          <option value="synthetic">синтетика</option>
        </select>
      </label>
      {extended && (
        <>
          <label className="adm-field adm-field-sm">
            Балл от
            <input type="number" value={value.score_min ?? ""} onChange={(e) => set("score_min", e.target.value)} />
          </label>
          <label className="adm-field adm-field-sm">
            до
            <input type="number" value={value.score_max ?? ""} onChange={(e) => set("score_max", e.target.value)} />
          </label>
          <label className="adm-field">
            Срез с
            <input type="date" value={value.as_of_from ?? ""} onChange={(e) => set("as_of_from", e.target.value)} />
          </label>
          <label className="adm-field">
            по
            <input type="date" value={value.as_of_to ?? ""} onChange={(e) => set("as_of_to", e.target.value)} />
          </label>
          <label className="adm-field adm-field-sm" title="Баллы в ±N от границы грейда">
            ± к границе
            <input type="number" min={0} max={50} value={value.borderline ?? ""} onChange={(e) => set("borderline", e.target.value)} />
          </label>
          <label className="adm-field">
            Стоп-фактор
            <select value={value.hard_stop ?? ""} onChange={(e) => set("hard_stop", e.target.value)}>
              <option value="">неважно</option>
              <option value="true">сработал</option>
              <option value="false">нет</option>
            </select>
          </label>
        </>
      )}
    </div>
  );
}

/** Фильтры → строка запроса для ссылки «Показать все по фильтрам». */
export function filtersHref(f: Filters): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `/adminuser?${s}` : "/adminuser";
}

export function CompaniesTable({ rows, reasons }: { rows: import("../api/admin").CompanyRow[]; reasons?: boolean }) {
  if (!rows.length) return <p className="muted">Под условия никто не подходит.</p>;
  return (
    <div className="panel-scroll">
      <table className="table table-wide adm-table">
        <thead>
          <tr>
            <th>Компания</th>
            <th>ОПФ · МСП</th>
            <th>Сегмент → модель</th>
            <th className="num">Балл</th>
            <th>Грейд</th>
            <th className="num">PD</th>
            <th>Решение</th>
            <th>Факт</th>
            <th>Дата среза</th>
            {reasons && <th>Источник</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <Link to={`/adminuser/companies/${r.id}`} className="table-company">
                  {r.name}
                </Link>
                <div className="table-sub">ИНН {r.inn}</div>
              </td>
              <td>
                {r.legalForm ?? "—"} · {r.msp ?? "—"}
              </td>
              <td>
                {r.segment ?? "—"}
                <div className="table-sub">
                  {r.model ? `${r.model} ${r.modelVersion}` : "—"}
                  {r.segment && r.modelSegment && r.segment !== r.modelSegment ? " (запасная)" : ""}
                </div>
              </td>
              <td className="num strong">{num(r.score)}</td>
              <td>
                <GradeChip grade={r.grade} />
              </td>
              <td className="num">{pct(r.pd)}</td>
              <td>
                <DecisionChip decision={r.decision} label={r.decisionLabel} />
                {r.hardStop && <div className="table-sub is-bad">стоп-фактор</div>}
              </td>
              <td>
                <FactCell fact={r.fact} />
              </td>
              <td>{date(r.asOf)}</td>
              {reasons && <td className="muted">{r.source === "live" ? "кабинет" : "синтетика"}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
