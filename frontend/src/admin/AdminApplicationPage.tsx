import { Link, useParams } from "react-router-dom";

import { getApplication, type ApplicationCard, type ApplicationDecision, type Offer } from "../api/admin";
import { ChevronLeft } from "../components/Icons";
import { useAsync } from "../lib/useAsync";
import { ScoreBreakdown, fmtValue } from "./AdminCompanyPage";
import { AdminShell, AppStatusChip, DecisionChip, GradeChip, Status, dateTime, money, num, pct, terms } from "./ui";

const SOURCE: Record<string, string> = {
  fns_egrul: "ЕГРЮЛ",
  fns_tax: "ФНС: налоги",
  rmsp: "Реестр МСП",
  fssp: "ФССП",
  efrsb: "ЕФРСБ",
  cbr_zsk: "ЗСК ЦБ",
  bki: "БКИ",
  bank_internal: "АБС банка",
  partner_bank: "банк-партнёр",
  gir_bo: "ГИР БО",
  kad_arbitr: "КАД",
  manual: "вручную",
};
const CONSENT: Record<string, string> = {
  personal_data: "обработка ПДн (152-ФЗ)",
  bki_request: "запрос в БКИ (218-ФЗ)",
  tax_secret: "налоговая тайна",
};

export function AdminApplicationPage() {
  const { id = "" } = useParams();
  const card = useAsync(() => getApplication(id), [id]);

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
        {card.status === "ready" && <Card data={card.data} />}
      </main>
    </AdminShell>
  );
}

function Card({ data }: { data: ApplicationCard }) {
  const { application: a, company: c, product: p } = data;
  const [d, ...earlier] = data.decisions;
  const s = d?.score ?? null;
  const pd = s?.pd ?? d?.model?.pd ?? null;

  return (
    <>
      <section className="container page-head page-head-col">
        <Link to="/adminuser/applications" className="back-link">
          <ChevronLeft size={16} /> Все заявки
        </Link>
        <div className="adm-title">
          <span className="adm-form">№</span>
          <div>
            <h1>Заявка № {a.number}</h1>
            <p className="page-head-sub">
              <Link to={`/adminuser/companies/${c.id}`} className="adm-head-link">
                {c.name}
              </Link>{" "}
              · ИНН {c.inn} · {p.name} · {data.applicant.name} ({data.applicant.email}) · отправлена {dateTime(a.submittedAt ?? a.createdAt)}
            </p>
          </div>
        </div>
        <div className="adm-kpis">
          <div className="adm-kpi">
            <span className="adm-kpi-label">Статус</span>
            <span className="adm-kpi-value">{a.status.label}</span>
            <span className="adm-kpi-note">{a.decidedAt ? `решение ${dateTime(a.decidedAt)}` : "решения ещё нет"}</span>
          </div>
          <div className="adm-kpi">
            <span className="adm-kpi-label">Запрошено</span>
            <span className="adm-kpi-value">{money(a.requestedAmount)}</span>
            <span className="adm-kpi-note">
              {a.requestedTerm ?? "—"} мес · базовая ставка {num(p.baseRate, 2)}%
            </span>
          </div>
          <div className={d?.decision === "decline" ? "adm-kpi adm-kpi-decision adm-kpi-accent" : "adm-kpi adm-kpi-decision"}>
            <span className="adm-kpi-label">Решение</span>
            <DecisionValue d={d} />
            <span className="adm-kpi-note">
              {d?.approvedAmount !== null && d?.approvedAmount !== undefined
                ? `одобрено ${terms(d.approvedAmount, d.approvedTerm, d.rate)}`
                : d
                  ? d.reasons[0]?.text ?? ""
                  : "конвейер ещё считает"}
            </span>
          </div>
          <div className="adm-kpi">
            <span className="adm-kpi-label">Балл · грейд · PD</span>
            <span className="adm-kpi-value">{s ? `${num(s.score)} · ${s.grade}` : "—"}</span>
            <span className="adm-kpi-note">
              {s ? `PD ${pct(pd, 2)} · ${s.model} ${s.modelVersion}` : d?.stopFactors.some((x) => x.triggered) ? "жёсткий стоп — без скоринга" : "скоринга не было"}
            </span>
          </div>
        </div>
      </section>

      <section className="sheet sheet-tight">
        <div className="container stack">
          {d ? <DecisionPanels d={d} data={data} /> : (
            <section className="panel-lg">
              <h2>Решения ещё нет</h2>
              <p className="muted">Заявка в очереди конвейера — обновите страницу через несколько секунд.</p>
            </section>
          )}

          {s && (
            <section className="panel-lg">
              <div className="adm-panel-head">
                <h2>Разложение балла</h2>
                <span className="muted">
                  база {num(s.base)} · сегмент {s.segment ?? "—"}
                  {s.segment !== s.modelSegment ? ` → модель запасного сегмента ${s.modelSegment}` : ""} · {s.model} {s.modelVersion}
                  {s.nextGradeAt ? ` · до грейда выше ${num(s.nextGradeAt - s.score)}` : ""} · вход sha256 {s.inputSha256?.slice(0, 10) ?? "—"}
                </span>
              </div>
              <ScoreBreakdown s={s} />
              <p className="muted small">
                Признаки, сильнее всего отнявшие баллы: <strong>{s.reasons.join(", ") || "—"}</strong>.
              </p>
            </section>
          )}

          <div className="split-even">
            <section className="panel-lg">
              <h2>История статусов</h2>
              {data.history.map((h, i) => (
                <div key={i} className="adm-line adm-line-top">
                  <span>
                    <AppStatusChip status={h.to} />
                    {h.comment && <div className="table-sub adm-wrap">{h.comment}</div>}
                  </span>
                  <span className="muted small">
                    {dateTime(h.at)} · {h.by}
                  </span>
                </div>
              ))}
              {!data.history.length && <p className="muted">Пусто.</p>}
            </section>
            <section className="panel-lg">
              <h2>Заявка</h2>
              <div className="adm-line">
                <span>Продукт</span>
                <span className="adm-line-right">
                  {p.name} <span className="muted">({p.code})</span>
                </span>
              </div>
              <div className="adm-line">
                <span>Условия продукта</span>
                <span className="muted">
                  {money(p.minAmount)} – {money(p.maxAmount)} · {p.minTerm}–{p.maxTerm} мес
                </span>
              </div>
              <div className="adm-line">
                <span>Цель</span>
                <span className="muted">{a.purpose || "—"}</span>
              </div>
              <div className="adm-line">
                <span>Канал</span>
                <span className="muted">{a.channel ?? "прямой"}{a.utm ? ` · ${Object.entries(a.utm).map(([k, v]) => `${k}=${v}`).join(" ")}` : ""}</span>
              </div>
              <h2 className="adm-h2-gap">Согласия</h2>
              {data.consents.map((x) => (
                <div key={x.type} className="adm-line">
                  <span>{CONSENT[x.type] ?? x.type}</span>
                  <span className="muted small">
                    {x.revokedAt ? `отозвано ${dateTime(x.revokedAt)}` : `${dateTime(x.signedAt)} · ред. ${x.version}`}
                  </span>
                </div>
              ))}
              {!data.consents.length && <p className="muted">Нет.</p>}
              <h2 className="adm-h2-gap">Задачи конвейера</h2>
              {data.tasks.map((t) => (
                <div key={t.id} className="adm-line">
                  <span>
                    #{t.id} {t.kind}
                    {t.lastError && <div className="table-sub is-bad adm-wrap">{t.lastError}</div>}
                  </span>
                  <span className={t.status === "failed" ? "is-bad" : "muted"}>
                    {t.status} · попыток {t.attempts}
                  </span>
                </div>
              ))}
              {!data.tasks.length && <p className="muted">Нет.</p>}
            </section>
          </div>

          <section className="panel-lg">
            <h2>Запросы к источникам при обработке</h2>
            {data.fetches.length ? (
              <div className="adm-fetches">
                {data.fetches.map((f) => (
                  <details key={f.id}>
                    <summary>
                      {SOURCE[f.source] ?? f.source} · <span className={f.status === "error" ? "is-bad" : ""}>{f.status}</span> · {dateTime(f.requestedAt)}
                      {f.error ? ` · ${f.error}` : ""}
                    </summary>
                    <pre>{JSON.stringify(f.payload, null, 2)}</pre>
                  </details>
                ))}
              </div>
            ) : (
              <p className="muted">Запросов за время обработки нет.</p>
            )}
            <p className="muted small">
              Агрегаты источников (БКИ, обороты, ФНС, ФССП) — в{" "}
              <Link to={`/adminuser/companies/${c.id}`}>карточке компании</Link>.
            </p>
          </section>

          {d?.features && (
            <section className="panel-lg">
              <h2>Входы модели на момент решения</h2>
              <dl className="adm-features">
                {Object.entries(d.features).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{fmtValue(v)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          {earlier.length > 0 && (
            <section className="panel-lg">
              <h2>Предыдущие решения</h2>
              {earlier.map((x) => (
                <div key={x.id} className="adm-line">
                  <span>
                    <DecisionChip decision={x.decision} label={x.decisionLabel} accepted={x.offerAccepted} />{" "}
                    <span className="muted">{x.reasons.map((r) => r.text).join("; ")}</span>
                  </span>
                  <span className="muted small">
                    {dateTime(x.decidedAt)} · {x.decidedBy}
                  </span>
                </div>
              ))}
            </section>
          )}
        </div>
      </section>
    </>
  );
}

/** Решение в плитке: длинные подписи мельче и без переноса внутри слова. */
function DecisionValue({ d }: { d: ApplicationDecision | undefined }) {
  if (!d) return <span className="adm-kpi-value">—</span>;
  if (d.decision === "counter_offer" && d.offerAccepted) {
    return (
      <span className="adm-kpi-value">
        Одобрено <span className="adm-kpi-value-sub">по контрпредложению</span>
      </span>
    );
  }
  const long = d.decisionLabel.length > 10;
  return <span className={long ? "adm-kpi-value adm-kpi-value-long" : "adm-kpi-value"}>{d.decisionLabel}</span>;
}

function DecisionPanels({ d, data }: { d: ApplicationDecision; data: ApplicationCard }) {
  const a = data.application;
  const accepted = d.acceptedOffer !== null ? d.offers[d.acceptedOffer] : null;
  return (
    <>
      <section className="panel-lg">
        <div className="adm-panel-head">
          <h2>Условия: запрошено и одобрено</h2>
          <span className="adm-panel-meta muted">
            <DecisionChip decision={d.decision} label={d.decisionLabel} accepted={d.offerAccepted} />
            <span>
              {dateTime(d.decidedAt)} · {d.decidedBy}
              {d.offerExpiresAt ? ` · предложение до ${dateTime(d.offerExpiresAt)}` : ""}
            </span>
          </span>
        </div>
        <div className="panel-scroll">
          <table className="table adm-table">
            <thead>
              <tr>
                <th />
                <th className="num">Сумма</th>
                <th className="num">Срок</th>
                <th className="num">Ставка</th>
                <th className="num">Платёж в месяц</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Запрошено</td>
                <td className="num strong">{money(a.requestedAmount)}</td>
                <td className="num">{a.requestedTerm ?? "—"} мес</td>
                <td className="num muted">{num(data.product.baseRate, 2)}% (база)</td>
                <td className="num muted">—</td>
              </tr>
              {d.offers.map((o, i) => (
                <OfferRow key={i} o={o} label={`Вариант ${i + 1}${i === d.acceptedOffer ? " · принят клиентом" : ""}`} strong={i === d.acceptedOffer} />
              ))}
              {d.alternatives.map((o, i) => (
                <OfferRow key={`alt${i}`} o={o} label={`Альтернатива: ${o.productName}`} muted />
              ))}
            </tbody>
          </table>
        </div>
        {!d.offers.length && <p className="muted">Предложений нет — {d.decisionLabel.toLowerCase()}.</p>}
        {accepted && d.offerAcceptedAt && (
          <p className="muted small">
            Клиент принял {terms(accepted.amount, accepted.termMonths, accepted.rate)} — {dateTime(d.offerAcceptedAt)}.
          </p>
        )}
        {d.error && <p className="is-bad small">Ошибка конвейера: {d.error}</p>}
        {d.comment && <p className="muted small">Комментарий: {d.comment}</p>}
      </section>

      <div className="split-even">
        <section className="panel-lg">
          <h2>Причины решения</h2>
          {d.reasons.length ? (
            d.reasons.map((r) => (
              <div key={r.code} className="adm-line">
                <span>{r.text}</span>
                <code className="muted small">{r.code}</code>
              </div>
            ))
          ) : (
            <p className="muted">Причин нет — заявка одобрена на запрошенных условиях.</p>
          )}
          {d.hints.length > 0 && (
            <>
              <h2 className="adm-h2-gap">Подсказки клиенту</h2>
              <ul className="adm-list">
                {d.hints.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </>
          )}
          <h2 className="adm-h2-gap">Входы лимита</h2>
          <div className="adm-line">
            <span>Чистый поток в месяц</span>
            <span className="adm-line-right">{money(d.inputs.income)}</span>
          </div>
          <div className="adm-line">
            <span>Текущие платежи по кредитам</span>
            <span className="adm-line-right">{money(d.inputs.payments)}</span>
          </div>
          <div className="adm-line">
            <span>DSCR</span>
            <span className={`adm-line-right ${d.inputs.dscr !== null && d.inputs.dscr < 1.2 ? "is-bad" : ""}`}>{num(d.inputs.dscr, 2)}</span>
          </div>
          {d.model && (
            <div className="adm-line">
              <span>Модель</span>
              <span className="adm-line-right">
                {d.model.name} {d.model.version} · {d.model.segment ?? "—"} · PD {pct(d.model.pd, 2)}
                {d.score?.grade && (
                  <>
                    {" "}
                    · <GradeChip grade={d.score.grade} />
                  </>
                )}
              </span>
            </div>
          )}
        </section>
        <section className="panel-lg">
          <h2>Стоп-факторы</h2>
          {d.stopFactors.length ? (
            d.stopFactors.map((x) => (
              <div key={x.code} className="adm-line">
                <span>
                  {x.name}
                  {x.triggered && x.details && <div className="table-sub">{fmtDetails(x.details)}</div>}
                </span>
                <span className={x.triggered ? "is-bad" : "is-good"}>{x.triggered ? "сработал" : "нет"}</span>
              </div>
            ))
          ) : (
            <p className="muted">Не проверялись (решение без конвейера).</p>
          )}
        </section>
      </div>
    </>
  );
}

function OfferRow({ o, label, strong, muted }: { o: Offer; label: string; strong?: boolean; muted?: boolean }) {
  return (
    <tr className={muted ? "muted" : undefined}>
      <td className={strong ? "strong" : undefined}>{label}</td>
      <td className="num strong">{money(o.amount)}</td>
      <td className="num">{o.termMonths} мес</td>
      <td className="num">{num(o.rate, 2)}%</td>
      <td className="num">{money(o.monthlyPayment)}</td>
    </tr>
  );
}

function fmtDetails(details: Record<string, unknown>): string {
  return Object.entries(details)
    .map(([k, v]) => `${k}: ${typeof v === "number" ? fmtValue(v) : String(v)}`)
    .join(" · ");
}
