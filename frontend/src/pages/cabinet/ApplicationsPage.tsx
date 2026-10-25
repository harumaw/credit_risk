import { useState } from "react";
import { Link } from "react-router-dom";

import { listApplications } from "../../api/cabinet";
import { useCompanies } from "../../cabinet/CompanyContext";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { EmptyCabinet, Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import {
  STATUS,
  StageBar,
  StatusChip,
  applicationHref,
  applicationTitle,
  requestedNote,
  sortByUrgency,
} from "../../components/cabinet/StatusChip";
import { SiteFooter } from "../../components/SiteHeader";
import { dayMonthNum, plural } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";

type Tab = "active" | "done";

export function ApplicationsPage() {
  const { companies, selected, select, reload } = useCompanies();
  const data = useAsync(listApplications, []);
  const [tab, setTab] = useState<Tab>("active");

  const list = companies.status === "ready" ? companies.data : [];
  const all = data.status === "ready" ? data.data : [];
  // В выбранной компании — только её заявки, в «Все компании» — все
  const scoped = selected ? all.filter((a) => a.companyId === selected.id) : all;
  const active = sortByUrgency(scoped.filter((a) => STATUS[a.status].active));
  const done = scoped
    .filter((a) => !STATUS[a.status].active)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  const shown = tab === "active" ? active : done;
  const companyName = (id: string) => list.find((c) => c.id === id)?.name ?? "";

  let body;
  if (companies.status === "error") body = <SheetStatus error={companies.message} onRetry={reload} />;
  else if (data.status === "error") body = <SheetStatus error={data.message} onRetry={data.reload} />;
  else if (companies.status === "loading" || data.status === "loading") body = <SheetStatus />;
  else if (!list.length) body = <EmptyCabinet />;
  else
    body = (
      <div className="stack">
        <div className="apps-toolbar">
          <div className="segmented segmented-sm" role="tablist" aria-label="Какие заявки">
            <button type="button" role="tab" aria-selected={tab === "active"} onClick={() => setTab("active")}>
              Активные · {active.length}
            </button>
            <button type="button" role="tab" aria-selected={tab === "done"} onClick={() => setTab("done")}>
              Завершённые · {done.length}
            </button>
          </div>
          {selected && list.length > 1 ? (
            <button type="button" className="text-link" onClick={() => select("all")}>
              Показать заявки всех компаний
            </button>
          ) : (
            tab === "active" && active.length > 0 && <span className="muted">Сначала — где нужно ваше действие</span>
          )}
        </div>

        {shown.length ? (
          <div className="app-rows" role="tabpanel">
            {shown.map((a) => {
              const urgent = STATUS[a.status].tone === "act";
              const was = requestedNote(a);
              return (
                <div key={a.id} className={`app-row ${urgent ? "is-urgent" : ""}`}>
                  <div className="app-row-main">
                    <span className="app-row-meta">
                      {companyName(a.companyId)} · № {a.number} · {dayMonthNum(a.createdAt)}
                    </span>
                    <strong>
                      {applicationTitle(a)}
                      {was && <span className="app-row-was">{was}</span>}
                    </strong>
                    <span className="app-row-note">{a.note}</span>
                  </div>
                  <div className="app-row-status">
                    <StatusChip status={a.status} />
                    <StageBar status={a.status} />
                  </div>
                  <Link to={applicationHref(a)} className={`btn btn-lg ${urgent ? "btn-accent" : "btn-white"}`}>
                    {STATUS[a.status].action}
                  </Link>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="panel-lg empty-apps" role="tabpanel">
            <h2>{tab === "active" ? "Активных заявок нет" : "Завершённых заявок нет"}</h2>
            <p className="muted-lg">
              {tab === "active"
                ? "Подайте заявку — данные компании подставим сами, решение покажем здесь."
                : "Здесь появятся выданные кредиты и заявки с решением."}
            </p>
            {tab === "active" && (
              <Link to="/cabinet/applications/new" className="btn btn-accent btn-lg">
                Новая заявка
              </Link>
            )}
          </div>
        )}
      </div>
    );

  const scope = selected ? selected.name : "По всем компаниям";
  return (
    <>
      <CabinetHeader />
      <section className="container page-head">
        <div>
          {data.status === "ready" && list.length > 0 && (
            <p className="page-head-meta">
              {scope} · {active.length} {plural(active.length, ["активная", "активные", "активных"])}, {done.length}{" "}
              {plural(done.length, ["завершённая", "завершённые", "завершённых"])}
            </p>
          )}
          <h1>Заявки</h1>
        </div>
        {list.length > 0 && (
          <Link to="/cabinet/applications/new" className="btn btn-accent btn-lg">
            Новая заявка
          </Link>
        )}
      </section>
      <Sheet>{body}</Sheet>
      <SiteFooter />
    </>
  );
}
