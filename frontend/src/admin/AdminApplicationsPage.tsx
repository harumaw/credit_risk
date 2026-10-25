import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { listApplications, type ApplicationFilters, type ApplicationRow } from "../api/admin";
import { useAsync } from "../lib/useAsync";
import { APP_STATUSES, AdminShell, ApplicationsTable, DECISIONS, Status, int } from "./ui";

const PAGE = 50;
const KEYS: (keyof ApplicationFilters)[] = ["q", "status", "decision"];

function fromParams(p: URLSearchParams): ApplicationFilters {
  const f: ApplicationFilters = {};
  for (const k of KEYS) {
    const v = p.get(k);
    if (v) f[k] = v;
  }
  return f;
}

export function AdminApplicationsPage() {
  const [params, setParams] = useSearchParams();
  const applied = fromParams(params);
  const [draft, setDraft] = useState<ApplicationFilters>(applied);
  const [extra, setExtra] = useState<ApplicationRow[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);

  const key = params.toString();
  useEffect(() => {
    setDraft(fromParams(params));
    setExtra([]);
  }, [key]);

  const list = useAsync(() => listApplications(applied, { limit: PAGE }), [key]);

  function apply(next: ApplicationFilters) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(next)) if (v) q.set(k, v);
    setParams(q);
  }

  async function loadMore() {
    if (list.status !== "ready") return;
    setLoadingMore(true);
    try {
      const res = await listApplications(applied, { limit: PAGE, offset: list.data.items.length + extra.length });
      setExtra((e) => [...e, ...res.items]);
    } finally {
      setLoadingMore(false);
    }
  }

  const set = (k: keyof ApplicationFilters, v: string) => setDraft({ ...draft, [k]: v || undefined });
  const rows = list.status === "ready" ? [...list.data.items, ...extra] : [];
  const total = list.status === "ready" ? list.data.total : 0;

  return (
    <AdminShell>
      <main>
        <section className="container page-head page-head-col">
          <h1>Заявки</h1>
          <p className="page-head-sub">Заявки клиентов кабинета: условия, решение конвейера, балл и PD. Клик по номеру — полный разбор заявки.</p>
        </section>
        <section className="sheet sheet-tight">
          <div className="container stack">
            <form
              className="panel-lg"
              onSubmit={(e) => {
                e.preventDefault();
                apply(draft);
              }}
            >
              <div className="adm-filters">
                <label className="adm-field adm-field-wide">
                  Поиск
                  <input type="search" placeholder="Номер заявки, ИНН или название" value={draft.q ?? ""} onChange={(e) => set("q", e.target.value)} />
                </label>
                <label className="adm-field">
                  Статус
                  <select value={draft.status ?? ""} onChange={(e) => set("status", e.target.value)}>
                    <option value="">все</option>
                    {APP_STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="adm-field">
                  Решение
                  <select value={draft.decision ?? ""} onChange={(e) => set("decision", e.target.value)}>
                    <option value="">все</option>
                    {DECISIONS.map((d) => (
                      <option key={d.value} value={d.value}>
                        {d.label}
                      </option>
                    ))}
                    <option value="none">решения ещё нет</option>
                  </select>
                </label>
              </div>
              <div className="btn-row adm-actions">
                <button type="submit" className="btn btn-accent">
                  Показать
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
            </form>

            <div className="adm-toolbar">
              <span className="muted">{list.status === "ready" && `Найдено: ${int(total)} · показаны 1–${int(rows.length)}`}</span>
            </div>

            {list.status === "loading" && <Status />}
            {list.status === "error" && <Status error={list.message} onRetry={list.reload} />}
            {list.status === "ready" && <ApplicationsTable rows={rows} />}
            {list.status === "ready" && rows.length < total && (
              <button type="button" className="btn btn-dark adm-more" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? "Загружаем…" : `Показать ещё ${Math.min(PAGE, total - rows.length)}`}
              </button>
            )}
          </div>
        </section>
      </main>
    </AdminShell>
  );
}
