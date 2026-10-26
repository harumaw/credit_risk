import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getCompany, rescoreCompany, type CompanyCard, type Obligation, type ScoreDetail } from "../api/admin";
import { ApiError } from "../api/client";
import { ChevronLeft } from "../components/Icons";
import { rubShort } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { AdminShell, ApplicationsTable, DecisionChip, GradeChip, Status, date, dateTime, num, pct } from "./ui";

const TRIGGER: Record<string, string> = { dpd_90: "90+ дней просрочки", bankruptcy: "банкротство" };
const ZSK: Record<string, string> = { green: "зелёная зона", yellow: "жёлтая зона", red: "красная зона" };
const PRODUCT: Record<string, string> = {
  term_loan: "кредит",
  credit_line: "кредитная линия",
  overdraft: "овердрафт",
  bank_guarantee: "банковская гарантия",
  leasing: "лизинг",
  credit_card: "кредитная карта",
};

export function AdminCompanyPage() {
  const { id = "" } = useParams();
  const card = useAsync(() => getCompany(id), [id]);

  return (
    <AdminShell>
      <main>
        {card.status === "loading" && (
          <div className="container">
            <Status />
          </div>
        )}
        {card.status === "error" && (
          <div className="container">
            <Status error={card.message} onRetry={card.reload} />
          </div>
        )}
        {card.status === "ready" && <Card data={card.data} reload={card.reload} />}
      </main>
    </AdminShell>
  );
}

function Card({ data, reload }: { data: CompanyCard; reload: () => void }) {
  const { company: c, score: s, fact } = data;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function rescore() {
    setBusy(true);
    setErr(null);
    try {
      await rescoreCompany(c.id);
      reload();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Не удалось пересчитать");
    } finally {
      setBusy(false);
    }
  }

  const age = data.features?.company_age_months;
  const meta = [
    `ИНН ${c.inn}`,
    c.okved[0] && `ОКВЭД ${c.okved[0]}${data.features?.okved_section ? ` (${data.features.okved_section})` : ""}`,
    c.region && `регион ${c.region}`,
    c.taxRegime,
    age !== undefined && age !== null && `возраст ${age} мес.`,
    c.source === "synthetic" ? `синтетика ${c.dataset ?? ""}${c.sample ? ` · ${c.sample}` : ""}` : "клиент кабинета",
    s && `срез ${date(s.asOf)}`,
  ].filter(Boolean);

  const lostTotal = s ? s.contributions.reduce((acc, x) => acc + x.points, 0) : 0;
  const current = data.alternatives.find((a) => a.isCurrent);
  const disagree = data.alternatives.filter((a) => a.decisionLabel !== s?.decisionLabel);

  return (
    <>
      <section className="container page-head page-head-col">
        <Link to="/adminuser" className="back-link">
          <ChevronLeft size={16} /> Все компании
        </Link>
        <div className="adm-title">
          <span className="adm-form">{c.legalForm ?? "—"}</span>
          <div>
            <h1>{c.name}</h1>
            <p className="page-head-sub">{meta.join(" · ")}</p>
          </div>
        </div>
        <div className="adm-kpis">
          <div className="adm-kpi">
            <span className="adm-kpi-label">Балл</span>
            <span className="adm-kpi-value">{s ? num(s.score) : "—"}</span>
            <span className="adm-kpi-note">{s ? `база ${num(s.base)} ${lostTotal >= 0 ? "+" : "−"} признаки ${num(Math.abs(lostTotal))}` : "скоринга не было"}</span>
          </div>
          <div className="adm-kpi">
            <span className="adm-kpi-label">Грейд · PD</span>
            <span className="adm-kpi-value">{s ? `${s.grade} · ${pct(s.pd)}` : "—"}</span>
            <span className="adm-kpi-note">
              {s?.nextGradeAt ? `до грейда выше ${num(s.nextGradeAt - s.score)} балла (граница ${num(s.nextGradeAt)})` : s ? "высший грейд" : ""}
            </span>
          </div>
          <div className="adm-kpi">
            <span className="adm-kpi-label">Решение (матрица)</span>
            <span className="adm-kpi-value">{s?.decisionLabel ?? "—"}</span>
            <span className="adm-kpi-note">{s?.hardStop ? "сработал стоп-фактор" : s ? `${s.model} ${s.modelVersion}` : ""}</span>
          </div>
          <div className={fact.default ? "adm-kpi adm-kpi-accent" : "adm-kpi"}>
            <span className="adm-kpi-label">Факт через 12 мес.</span>
            <span className="adm-kpi-value">{!fact.known ? "нет данных" : fact.default ? "Дефолт" : "Без дефолта"}</span>
            <span className="adm-kpi-note">
              {fact.default
                ? `${TRIGGER[fact.trigger ?? ""] ?? fact.trigger} с ${date(fact.defaultDate)}${s?.decision === "approve" ? " — пропуск модели" : ""}`
                : fact.known
                  ? s?.decision === "decline"
                    ? "отказали зря — упущенный клиент"
                    : "модель права"
                  : "известен только для синтетики и выданных кредитов"}
            </span>
          </div>
        </div>
        <div className="page-head-actions">
          <button type="button" className="btn btn-accent" onClick={rescore} disabled={busy}>
            {busy ? "Считаем…" : c.source === "live" ? "Пересчитать по данным источников" : "Пересчитать"}
          </button>
          {err && <span className="is-bad small">{err}</span>}
        </div>
      </section>

      <section className="sheet sheet-tight">
        <div className="container stack">
          {s ? (
            <section className="panel-lg">
              <div className="adm-panel-head">
                <h2>Разложение балла</h2>
                <span className="muted">
                  сегмент {s.segment ?? "—"}
                  {s.segment !== s.modelSegment ? ` → модель запасного сегмента ${s.modelSegment}` : ""} · {s.model} {s.modelVersion} · вход sha256{" "}
                  {s.inputSha256?.slice(0, 10) ?? "—"}
                </span>
              </div>
              <ScoreBreakdown s={s} />
              <p className="muted small">
                Коды причин для клиента: <strong>{s.reasons.join(", ") || "—"}</strong> — признаки, сильнее всего отнявшие баллы.
              </p>
            </section>
          ) : (
            <section className="panel-lg">
              <h2>Скоринга ещё не было</h2>
              <p className="muted">Нажмите «Пересчитать» — балл посчитается по данным источников на сегодня.</p>
            </section>
          )}

          <div className="split-even">
            <section className="panel-lg">
              <h2>Что сказали бы другие модели</h2>
              {data.alternatives.map((a) => (
                <div key={`${a.model}${a.version}`} className={`adm-line ${a.isCurrent ? "is-current" : ""}`}>
                  <span>
                    <strong>{a.model}</strong>{" "}
                    <span className="muted">
                      {a.segment} · {a.status}
                      {a.isCurrent ? " · применена" : ""}
                    </span>
                  </span>
                  <span className="adm-line-right">
                    {num(a.score)} · <GradeChip grade={a.grade} /> · {a.decisionLabel}
                  </span>
                </div>
              ))}
              {current && disagree.length > 0 && (
                <p className="muted small">
                  Расхождение: {disagree.map((d) => `${d.model} → ${d.decisionLabel.toLowerCase()}`).join(", ")}. Повод посмотреть сегмент.
                </p>
              )}
            </section>
            <section className="panel-lg">
              <h2>Стоп-факторы</h2>
              {s && s.stops.length ? (
                s.stops.map((x) => (
                  <div key={x.code} className="adm-line">
                    <span>{x.name}</span>
                    <span className={x.triggered ? "is-bad" : "is-good"}>{x.triggered ? "сработал" : "нет"}</span>
                  </div>
                ))
              ) : (
                <p className="muted">Жёсткие стоп-факторы не сработали (банкротство/ликвидация, красная зона ЗСК).</p>
              )}
              <h2 className="adm-h2-gap">Пользователи кабинета</h2>
              {data.users.length ? (
                data.users.map((u) => (
                  <div key={u.email} className="adm-line">
                    <span>
                      {u.name} <span className="muted">{u.email}</span>
                    </span>
                    <span className="muted">{u.role}</span>
                  </div>
                ))
              ) : (
                <p className="muted">Нет — синтетическая компания.</p>
              )}
            </section>
          </div>

          <section className="panel-lg">
            <h2>Заявки компании</h2>
            {data.applications.length ? (
              <ApplicationsTable rows={data.applications} company={false} />
            ) : (
              <p className="muted">{c.source === "synthetic" ? "Нет — синтетическая компания." : "Заявок ещё не было."}</p>
            )}
          </section>

          <section className="panel-lg">
            <h2>Кредитная история (БКИ) — строки платёжной дисциплины</h2>
            {data.sources.obligations.length ? (
              data.sources.obligations.map((o, i) => <LoanRow key={i} o={o} />)
            ) : (
              <p className="muted">Кредитов в БКИ нет.</p>
            )}
            <p className="muted small">Зелёный — без просрочки, жёлтый — до 30 дн., красный — 30+, серый — нет данных. Слева — последний месяц.</p>
          </section>

          <section className="panel-lg">
            <h2>Обороты за 12 мес. и прочие источники</h2>
            <Turnovers data={data.sources.turnovers.slice(-12)} />
            <div className="adm-sources">
              <div>
                <strong>ЕГРЮЛ</strong>
                <div className="muted">
                  {c.status ?? "—"} · рег. {date(c.registrationDate)} · {c.address ?? ""}
                </div>
              </div>
              <div>
                <strong>ФНС</strong>
                <div className="muted">
                  налоговый долг{" "}
                  {data.sources.tax.length ? rubShort(data.sources.tax[0].debt) : "0 ₽"}
                </div>
              </div>
              <div>
                <strong>ФССП</strong>
                <div className="muted">
                  {data.sources.fssp.filter((f) => !f.closedAt).length
                    ? `открытых ИП: ${data.sources.fssp.filter((f) => !f.closedAt).length}`
                    : "открытых ИП нет"}
                </div>
              </div>
              <div>
                <strong>ЗСК ЦБ</strong>
                <div className="muted">{data.sources.zsk.length ? ZSK[data.sources.zsk[0].zone] : "нет данных"}</div>
              </div>
              <div>
                <strong>ЕФРСБ</strong>
                <div className="muted">{data.sources.bankruptcy.length ? data.sources.bankruptcy.map((b) => b.type).join(", ") : "сообщений нет"}</div>
              </div>
              <div>
                <strong>Счета</strong>
                <div className="muted">
                  {data.sources.accounts.map((a) => `${a.account}${a.ownBank ? " (наш банк)" : ""}`).join(", ") || "нет"}
                </div>
              </div>
            </div>
            {data.sources.fetches.length > 0 && (
              <details className="adm-fetches">
                <summary>Снимки ответов источников ({data.sources.fetches.length})</summary>
                {data.sources.fetches.map((f) => (
                  <details key={f.id}>
                    <summary>
                      {f.source} · {f.status} · {dateTime(f.requestedAt)}
                    </summary>
                    <pre>{JSON.stringify(f.payload, null, 2)}</pre>
                  </details>
                ))}
              </details>
            )}
          </section>

          <div className="split-even">
            <section className="panel-lg">
              <h2>История скорингов</h2>
              {data.history.map((h) => (
                <div key={h.id} className="adm-line">
                  <span>
                    {dateTime(h.scoredAt)} · {h.model} {h.version}
                  </span>
                  <span className="adm-line-right">
                    {num(h.score)} · <GradeChip grade={h.grade} /> · {h.decisionLabel}
                  </span>
                </div>
              ))}
              {!data.history.length && <p className="muted">Пусто.</p>}
            </section>
            {data.features && (
              <section className="panel-lg">
                <h2>Входы модели</h2>
                <dl className="adm-features">
                  {Object.entries(data.features).map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{fmtValue(v)}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
          </div>
          <p className="muted small">
            <DecisionChip decision={s?.decision ?? null} label={s?.decisionLabel ?? null} /> Решение — рекомендация по матрице грейдов; у клиентов
            кабинета — итог заявки.
          </p>
        </div>
      </section>
    </>
  );
}

/** Разложение балла по признакам: значение, бин, баллы, потеря до лучшего бина. */
export function ScoreBreakdown({ s }: { s: ScoreDetail }) {
  return (
    <div className="panel-scroll">
      <table className="table table-wide adm-table">
        <thead>
          <tr>
            <th>Признак</th>
            <th>Значение</th>
            <th>Бин</th>
            <th className="num">Баллы</th>
            <th className="num">Лучший бин</th>
            <th className="num">Потеря</th>
            <th>Bad rate бина</th>
          </tr>
        </thead>
        <tbody>
          {s.contributions.map((x) => (
            <tr key={x.feature}>
              <td>
                {x.name}
                <div className="table-sub">{x.feature}</div>
              </td>
              <td>{fmtValue(x.value)}</td>
              <td>{x.bin}</td>
              <td className={`num strong ${x.points < 0 ? "is-bad" : ""}`}>{num(x.points, 2)}</td>
              <td className="num">{num(x.best, 2)}</td>
              <td className={`num ${x.lost > 15 ? "is-bad" : ""}`}>{num(x.lost, 2)}</td>
              <td>
                <RateBar rate={x.eventRate} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function fmtValue(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Math.abs(v) >= 10000 ? rubShort(v) : v.toLocaleString("ru-RU", { maximumFractionDigits: 4 });
  return v;
}

export function RateBar({ rate }: { rate: number | null }) {
  if (rate === null) return <span className="muted">—</span>;
  const w = Math.min(100, (rate / 0.25) * 100);
  return (
    <span className="adm-rate">
      <span className="adm-rate-bar">
        <span style={{ width: `${w}%` }} className={rate > 0.08 ? "is-high" : ""} />
      </span>
      {pct(rate)}
    </span>
  );
}

function LoanRow({ o }: { o: Obligation }) {
  const cells = (o.paymentString ?? "").slice(0, 24).split("");
  return (
    <div className="adm-loan">
      <div className="adm-loan-title">
        {o.lender ?? "—"} · {PRODUCT[o.product ?? ""] ?? o.product ?? "—"}
        <div className="table-sub">
          лимит {o.limit !== null ? rubShort(o.limit) : "—"} · остаток {o.outstanding !== null ? rubShort(o.outstanding) : "—"} · с {date(o.openedAt)}
          {o.closedAt ? ` по ${date(o.closedAt)}` : " · действует"}
          {o.maxDpd ? ` · макс. просрочка ${o.maxDpd} дн.` : ""}
        </div>
      </div>
      <div className="adm-pay" aria-label="Статусы по месяцам, слева — последний">
        {cells.length ? (
          cells.map((ch, i) => <span key={i} className={`pay-${ch === "-" ? "na" : ch}`} title={ch} />)
        ) : (
          <span className="muted small">строки нет</span>
        )}
      </div>
    </div>
  );
}

function Turnovers({ data }: { data: { month: string; inflow: number; balance: number }[] }) {
  if (!data.length) return <p className="muted">Оборотов нет (нужна выписка).</p>;
  const max = Math.max(...data.map((d) => d.inflow), 1);
  return (
    <div className="adm-bars">
      {data.map((d) => (
        <div key={d.month} className="adm-bar" title={`${d.month}: поступления ${rubShort(d.inflow)}, остаток ${rubShort(d.balance)}`}>
          <span style={{ height: `${(d.inflow / max) * 100}%` }} />
          <small>{d.month.slice(2).replace("-", ".")}</small>
        </div>
      ))}
    </div>
  );
}
