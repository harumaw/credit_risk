import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  downloadCsv,
  filtersFromParams,
  getSummary,
  listCompanies,
  listModels,
  type CompanyRow,
  type Filters,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { AdminShell, CompaniesTable, FilterBar, Status, dateTime, int, pct } from "./ui";

const PAGE = 50;

const SORT_OPTIONS = [
  ["-as_of", "сначала новые срезы"],
  ["as_of", "сначала старые срезы"],
  ["-score", "балл ↓"],
  ["score", "балл ↑"],
  ["-pd", "PD ↓"],
  ["name", "по названию"],
] as const;

export function AdminCompaniesPage() {
  const [params, setParams] = useSearchParams();
  const applied = filtersFromParams(params);
  const sort = params.get("sort") ?? "-as_of";
  const seedParam = params.get("seed");
  const random = params.get("random") === "1";

  const [draft, setDraft] = useState<Filters>(applied);
  const [extended, setExtended] = useState(
    Boolean(applied.score_min || applied.score_max || applied.as_of_from || applied.as_of_to || applied.borderline || applied.hard_stop),
  );
  const [extra, setExtra] = useState<CompanyRow[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);

  const key = params.toString();
  useEffect(() => {
    setDraft(filtersFromParams(params));
    setExtra([]);
  }, [key]);

  const meta = useAsync(() => Promise.all([getSummary(), listModels()]), []);
  const list = useAsync(
    () =>
      listCompanies(applied, {
        limit: random ? 20 : PAGE,
        sort,
        random,
        seed: seedParam ? Number(seedParam) : undefined,
      }),
    [key],
  );

  function apply(next: Filters, mode: { random?: boolean } = {}) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(next)) if (v) q.set(k, v);
    if (sort !== "-as_of") q.set("sort", sort);
    if (mode.random) {
      q.set("random", "1");
      q.set("seed", String(Math.floor(Math.random() * 999_999) + 1));
    }
    setParams(q);
  }

  async function loadMore() {
    if (list.status !== "ready") return;
    setLoadingMore(true);
    try {
      const res = await listCompanies(applied, { limit: PAGE, offset: list.data.items.length + extra.length, sort });
      setExtra((e) => [...e, ...res.items]);
    } finally {
      setLoadingMore(false);
    }
  }

  async function csv() {
    setCsvError(null);
    try {
      await downloadCsv(applied, sort);
    } catch (e) {
      setCsvError(e instanceof ApiError ? e.message : "Не удалось выгрузить CSV");
    }
  }

  function setSort(value: string) {
    const q = new URLSearchParams(params);
    q.delete("random");
    q.delete("seed");
    if (value === "-as_of") q.delete("sort");
    else q.set("sort", value);
    setParams(q);
  }

  const summary = meta.status === "ready" ? meta.data[0] : null;
  const models = meta.status === "ready" ? meta.data[1] : null;
  const rows = list.status === "ready" ? [...list.data.items, ...extra] : [];
  const total = list.status === "ready" ? list.data.total : 0;

  return (
    <AdminShell>
      <main>
        <section className="container page-head page-head-col">
          <h1>Компании</h1>
          {summary && (
            <div className="adm-kpis">
              <Kpi label="Компаний" value={int(summary.companies)} note={`синтетика ${int(summary.synthetic)} · кабинет ${int(summary.live)}`} />
              <Kpi label="Оскорено" value={int(summary.scored)} note={`последний — ${dateTime(summary.lastScoredAt)}`} />
              <Kpi label="Одобрено" value={pct(summary.approveShare)} note={`ручной разбор ${pct(summary.manualShare)}`} />
              <Kpi label="Отказ" value={pct(summary.declineShare)} note="грейд D–E или стоп-фактор" />
              <Kpi
                label="Дефолт среди одобренных"
                value={pct(summary.defaultAmongApproved)}
                note="пропуск модели — по синтетике"
                accent
              />
            </div>
          )}
        </section>
        <section className="sheet sheet-tight">
          <div className="container stack">
            {models && (
              <form
                className="panel-lg"
                onSubmit={(e) => {
                  e.preventDefault();
                  apply(draft);
                }}
              >
                <FilterBar value={draft} onChange={setDraft} models={models.models} segments={models.segments} extended={extended} />
                <div className="btn-row adm-actions">
                  <button type="submit" className="btn btn-accent">
                    Показать все по фильтрам
                  </button>
                  <button type="button" className="btn btn-dark" onClick={() => apply(draft, { random: true })}>
                    Случайные 20
                  </button>
                  <button type="button" className="btn btn-white adm-outline" onClick={csv}>
                    Выгрузить CSV
                  </button>
                  <button type="button" className="text-link" onClick={() => setExtended((x) => !x)}>
                    {extended ? "Меньше условий" : "Ещё условия: балл, даты, пограничные"}
                  </button>
                  <button
                    type="button"
                    className="text-link"
                    onClick={() => {
                      setDraft({});
                      apply({});
                    }}
                  >
                    Сбросить
                  </button>
                </div>
                {csvError && <p className="is-bad small">{csvError}</p>}
              </form>
            )}

            <div className="adm-toolbar">
              <span className="muted">
                {list.status === "ready" &&
                  (random
                    ? `Случайные ${rows.length} из ${int(total)} · seed ${list.data.seed} (повторяемо по ссылке)`
                    : `Найдено: ${int(total)} · показаны 1–${int(rows.length)}`)}
              </span>
              {!random && (
                <label className="adm-field adm-field-inline">
                  Сортировка
                  <select value={sort} onChange={(e) => setSort(e.target.value)}>
                    {SORT_OPTIONS.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>

            {list.status === "loading" && <Status />}
            {list.status === "error" && <Status error={list.message} onRetry={list.reload} />}
            {list.status === "ready" && <CompaniesTable rows={rows} reasons />}
            {list.status === "ready" && !random && rows.length < total && (
              <button type="button" className="btn btn-dark adm-more" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? "Загружаем…" : `Показать ещё ${Math.min(PAGE, total - rows.length)}`}
              </button>
            )}
            <p className="muted small">
              Клик по компании — полный разбор: источники, разложение балла, что сказали бы другие модели, стоп-факторы, история
              скорингов.
            </p>
          </div>
        </section>
      </main>
    </AdminShell>
  );
}

function Kpi({ label, value, note, accent }: { label: string; value: string; note: string; accent?: boolean }) {
  return (
    <div className={accent ? "adm-kpi adm-kpi-accent" : "adm-kpi"}>
      <span className="adm-kpi-label">{label}</span>
      <span className="adm-kpi-value">{value}</span>
      <span className="adm-kpi-note">{note}</span>
    </div>
  );
}
