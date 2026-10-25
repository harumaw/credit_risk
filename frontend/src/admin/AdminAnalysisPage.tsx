import { useState } from "react";
import { Link } from "react-router-dom";

import {
  getDisagreement,
  getDrivers,
  getMatrix,
  getMonthly,
  listCompanies,
  listModels,
  type Filters,
} from "../api/admin";
import { useAsync } from "../lib/useAsync";
import { AdminShell, CompaniesTable, DECISIONS, FACT_LABEL, FilterBar, Status, filtersHref, int, num, pct } from "./ui";

const PRESETS: { label: string; hint: string; f: Filters }[] = [
  { label: "Пропуски модели", hint: "одобрили, а был дефолт", f: { decision: "approve", fact: "default" } },
  { label: "Упущенные клиенты", hint: "отказали, а дефолта не было", f: { decision: "decline", fact: "no_default" } },
  { label: "Пограничные ±5", hint: "в 5 баллах от границы грейда — решение решает один признак", f: { borderline: "5" } },
  { label: "Ручной разбор", hint: "грейд C — нужна ручная проверка", f: { decision: "manual_review" } },
  { label: "Стоп-факторы", hint: "отказ без модели", f: { hard_stop: "true" } },
  { label: "Клиенты кабинета", hint: "реальные заявители, не синтетика", f: { source: "live" } },
];

const sameFilters = (a: Filters, b: Filters) => JSON.stringify(clean(a)) === JSON.stringify(clean(b));
function clean(f: Filters): Filters {
  return Object.fromEntries(
    Object.entries(f)
      .filter(([, v]) => v)
      .sort(),
  );
}
const newSeed = () => Math.floor(Math.random() * 999_999) + 1;

export function AdminAnalysisPage() {
  const meta = useAsync(listModels, []);
  const [draft, setDraft] = useState<Filters>(PRESETS[0].f);
  const [applied, setApplied] = useState<Filters>(PRESETS[0].f);
  const [size, setSize] = useState(20);
  const [seed, setSeed] = useState(newSeed);

  const key = JSON.stringify([clean(applied), size, seed]);
  const sample = useAsync(() => listCompanies(applied, { limit: size, random: true, seed }), [key]);
  // Матрица — по всем, кроме самих решения и факта, иначе она схлопнется в одну ячейку
  const { decision: _d, fact: _f, ...matrixFilters } = applied;
  const matrix = useAsync(() => getMatrix(matrixFilters), [JSON.stringify(clean(matrixFilters))]);
  const drivers = useAsync(() => getDrivers(applied), [JSON.stringify(clean(applied))]);
  const monthly = useAsync(() => getMonthly(matrixFilters), [JSON.stringify(clean(matrixFilters))]);

  function run(f: Filters) {
    setDraft(f);
    setApplied(f);
    setSeed(newSeed());
  }

  const title = PRESETS.find((p) => sameFilters(p.f, applied))?.label ?? "по условиям";

  return (
    <AdminShell>
      <main>
        <section className="container page-head page-head-col">
          <h1>Выборки и узкие места</h1>
          <p className="page-head-sub">
            Случайные компании под условия, решение × факт, чем группа отличается от одобренных, дрейф по месяцам и расхождения моделей.
          </p>
        </section>
        <section className="sheet sheet-tight">
          <div className="container stack">
            <form
              className="panel-lg"
              onSubmit={(e) => {
                e.preventDefault();
                run(draft);
              }}
            >
              <h2>Условия выборки</h2>
              <div className="adm-presets">
                <span className="muted small">Готовые срезы</span>
                <div className="segmented segmented-sm">
                  {PRESETS.map((p) => (
                    <button key={p.label} type="button" title={p.hint} aria-pressed={sameFilters(p.f, applied)} onClick={() => run(p.f)}>
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
              {meta.status === "ready" && (
                <FilterBar value={draft} onChange={setDraft} models={meta.data.models} segments={meta.data.segments} extended />
              )}
              <div className="btn-row adm-actions">
                <label className="adm-field adm-field-sm adm-field-inline">
                  Размер
                  <input type="number" min={1} max={200} value={size} onChange={(e) => setSize(Math.max(1, Math.min(200, Number(e.target.value) || 20)))} />
                </label>
                <button type="submit" className="btn btn-accent">
                  Случайная выборка
                </button>
                <Link to={filtersHref(applied)} className="btn btn-dark">
                  Показать все по фильтрам
                </Link>
                <span className="muted small">
                  {sample.status === "ready" && `Под условия подходит ${int(sample.data.total)} · seed ${sample.data.seed} (повторяемо)`}
                </span>
              </div>
            </form>

            <div className="split-even">
              <section className="panel-lg">
                <h2>Решение × факт</h2>
                {matrix.status === "ready" ? (
                  <Matrix cells={matrix.data.cells} onPick={(decision, fact) => run({ ...matrixFilters, decision, fact })} />
                ) : (
                  <Status error={matrix.status === "error" ? matrix.message : undefined} />
                )}
                <p className="muted small">
                  Клик по ячейке — эта группа во всех блоках ниже. Факт известен только для синтетики (дефолт в 12 мес. после среза).
                </p>
              </section>
              <section className="panel-lg">
                <h2>Что объединяет группу</h2>
                {drivers.status === "ready" ? (
                  <>
                    <span className="muted small">
                      Группа {int(drivers.data.groupSize)} против всех одобренных ({int(drivers.data.referenceSize)}): медианы и доли признаков
                    </span>
                    {drivers.data.items.slice(0, 7).map((d) => (
                      <div key={d.feature} className="adm-driver">
                        <span className="adm-driver-name">{d.name}</span>
                        <span className="adm-driver-bar" aria-hidden="true">
                          <span
                            className={d.effect > 0 ? "is-up" : "is-down"}
                            style={{ width: `${Math.min(100, Math.abs(d.effect) * 50)}%` }}
                          />
                        </span>
                        <span className="adm-driver-note">
                          {d.kind === "num"
                            ? `${num(d.group, 2)} против ${num(d.reference, 2)}`
                            : `«${d.top}»: ${pct(d.group, 0)} против ${pct(d.reference, 0)}`}
                        </span>
                      </div>
                    ))}
                    {!drivers.data.items.length && <p className="muted">Группа пуста.</p>}
                  </>
                ) : (
                  <Status error={drivers.status === "error" ? drivers.message : undefined} />
                )}
              </section>
            </div>

            <section className="panel-lg">
              <div className="adm-panel-head">
                <h2>Выборка: {title}</h2>
                {sample.status === "ready" && (
                  <span className="muted">
                    {sample.data.items.length} из {int(sample.data.total)}
                  </span>
                )}
              </div>
              {sample.status === "ready" ? (
                <CompaniesTable rows={sample.data.items} />
              ) : (
                <Status error={sample.status === "error" ? sample.message : undefined} onRetry={sample.reload} />
              )}
            </section>

            <Disagreements filters={matrixFilters} />

            <section className="panel-lg">
              <h2>Стабильность по месяцам среза</h2>
              <p className="muted small">Доля одобрений, средний PD и фактический дефолт: дрейф виден раньше, чем растут потери.</p>
              {monthly.status === "ready" ? (
                <Monthly rows={monthly.data.months} />
              ) : (
                <Status error={monthly.status === "error" ? monthly.message : undefined} />
              )}
            </section>

            <section className="panel-lg">
              <h2>Дальше</h2>
              <ul className="adm-list">
                <li>Воронка конвейера заявок: на каком шаге застревают и сколько ждут (данные уже есть в истории статусов и tasks).</li>
                <li>Расхождения источников (ЕГРЮЛ ↔ анкета, БКИ ↔ выписка).</li>
              </ul>
            </section>
          </div>
        </section>
      </main>
    </AdminShell>
  );
}

function Matrix({
  cells,
  onPick,
}: {
  cells: { decision: string; fact: string; count: number }[];
  onPick: (decision: string, fact: string) => void;
}) {
  const get = (d: string, f: string) => cells.find((c) => c.decision === d && c.fact === f)?.count ?? 0;
  const hasUnknown = cells.some((c) => c.fact === "unknown" && c.count > 0);
  const facts = hasUnknown ? ["no_default", "default", "unknown"] : ["no_default", "default"];
  return (
    <div className="panel-scroll">
      <table className="table adm-matrix">
        <thead>
          <tr>
            <th />
            {facts.map((f) => (
              <th key={f} className="num">
                {FACT_LABEL[f as keyof typeof FACT_LABEL]}
              </th>
            ))}
            <th className="num">доля дефолта</th>
          </tr>
        </thead>
        <tbody>
          {DECISIONS.map((d) => {
            const good = get(d.value, "no_default");
            const bad = get(d.value, "default");
            return (
              <tr key={d.value}>
                <td className="strong">{d.label}</td>
                {facts.map((f) => {
                  const n = get(d.value, f);
                  const flag =
                    d.value === "approve" && f === "default" ? "пропуск" : d.value === "decline" && f === "no_default" ? "упущено" : null;
                  return (
                    <td key={f} className="num">
                      <button type="button" className={`adm-cell ${flag ? "is-flag" : ""}`} onClick={() => onPick(d.value, f)} disabled={!n}>
                        {int(n)}
                        {flag && <small>{flag}</small>}
                      </button>
                    </td>
                  );
                })}
                <td className="num">{good + bad ? pct(bad / (good + bad)) : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Monthly({ rows }: { rows: { month: string; n: number; approveShare: number; avgPd: number; defaultRate: number | null; avgScore: number }[] }) {
  if (!rows.length) return <p className="muted">Нет данных.</p>;
  const maxPd = Math.max(...rows.map((r) => Math.max(r.avgPd, r.defaultRate ?? 0)), 0.01);
  return (
    <div className="panel-scroll">
      <table className="table table-wide adm-table">
        <thead>
          <tr>
            <th>Месяц</th>
            <th className="num">Компаний</th>
            <th className="num">Средний балл</th>
            <th>Одобрено</th>
            <th>Средний PD vs факт дефолта</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.month}>
              <td>{r.month}</td>
              <td className="num">{int(r.n)}</td>
              <td className="num">{num(r.avgScore)}</td>
              <td>
                <span className="adm-rate">
                  <span className="adm-rate-bar">
                    <span style={{ width: `${r.approveShare * 100}%` }} className="is-ok" />
                  </span>
                  {pct(r.approveShare, 0)}
                </span>
              </td>
              <td>
                <span className="adm-pd">
                  <span className="adm-rate-bar">
                    <span style={{ width: `${(r.avgPd / maxPd) * 100}%` }} />
                  </span>
                  <span className="adm-rate-bar">
                    <span style={{ width: `${((r.defaultRate ?? 0) / maxPd) * 100}%` }} className="is-high" />
                  </span>
                  <span className="small">
                    {pct(r.avgPd)} / {r.defaultRate === null ? "—" : pct(r.defaultRate)}
                  </span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Disagreements({ filters }: { filters: Filters }) {
  const [size, setSize] = useState(300);
  const [seed, setSeed] = useState(newSeed);
  const data = useAsync(() => getDisagreement(filters, size, seed), [JSON.stringify([clean(filters), size, seed])]);
  return (
    <section className="panel-lg">
      <div className="adm-panel-head">
        <h2>Champion / challenger: где модели расходятся</h2>
        <span className="btn-row">
          <select className="adm-select" value={size} onChange={(e) => setSize(Number(e.target.value))} aria-label="Размер выборки">
            {[100, 300, 1000, 2000].map((n) => (
              <option key={n} value={n}>
                {n} компаний
              </option>
            ))}
          </select>
          <button type="button" className="btn btn-dark" onClick={() => setSeed(newSeed())}>
            Другая выборка
          </button>
        </span>
      </div>
      <p className="muted small">
        Каждую компанию пересчитываем всеми моделями на тех же входах. «Совпадает» — доля, где решение модели равно применённому.
      </p>
      {data.status !== "ready" ? (
        <Status error={data.status === "error" ? data.message : undefined} />
      ) : (
        <>
          <div className="panel-scroll">
            <table className="table adm-table">
              <thead>
                <tr>
                  <th>Модель</th>
                  <th className="num">Совпадает</th>
                  <th className="num">Одобрила бы</th>
                  <th className="num">Дефолт среди её одобренных</th>
                </tr>
              </thead>
              <tbody>
                {data.data.models.map((m) => (
                  <tr key={m.model}>
                    <td>
                      <strong>{m.model}</strong>
                      <div className="table-sub">
                        {m.segment} · {m.status}
                      </div>
                    </td>
                    <td className="num">{pct(m.agreeShare)}</td>
                    <td className="num">{pct(m.approveShare)}</td>
                    <td className="num strong">{pct(m.defaultAmongApproved)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.data.examples.length > 0 && (
            <details className="adm-fetches">
              <summary>Компании с разными решениями ({data.data.examples.length}{data.data.examples.length === 30 ? "+" : ""})</summary>
              <div className="panel-scroll">
                <table className="table table-wide adm-table">
                  <thead>
                    <tr>
                      <th>Компания</th>
                      <th>Применено</th>
                      {data.data.models.map((m) => (
                        <th key={m.model}>{m.model}</th>
                      ))}
                      <th>Факт</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.data.examples.map((e) => (
                      <tr key={e.id}>
                        <td>
                          <Link to={`/adminuser/companies/${e.id}`} className="table-company">
                            {e.name}
                          </Link>
                        </td>
                        <td>
                          {e.decisionLabel}
                          <div className="table-sub">{e.model}</div>
                        </td>
                        {data.data.models.map((m) => (
                          <td key={m.model} className={e.byModel[m.model] !== e.decisionLabel ? "strong" : "muted"}>
                            {e.byModel[m.model] ?? "—"}
                          </td>
                        ))}
                        <td className={e.fact === "default" ? "is-bad" : ""}>{FACT_LABEL[e.fact]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          <p className="muted small">seed {data.data.seed} · выборка {int(data.data.sample)}</p>
        </>
      )}
    </section>
  );
}
