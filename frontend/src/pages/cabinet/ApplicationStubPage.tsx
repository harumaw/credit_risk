import { Link, useParams } from "react-router-dom";

import { listApplications } from "../../api/cabinet";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { Sheet, SheetStatus } from "../../components/cabinet/EmptyCabinet";
import { StageBar, StatusChip, applicationTitle } from "../../components/cabinet/StatusChip";
import { SiteFooter } from "../../components/SiteHeader";
import { useAsync } from "../../lib/useAsync";

/** Заглушка: мастер заявки (/new) и экран заявки (/:id) появятся в следующих задачах. */
export function ApplicationStubPage() {
  const { id } = useParams();
  const data = useAsync(listApplications, []);
  const app = id && data.status === "ready" ? data.data.find((a) => a.id === id) : undefined;

  return (
    <>
      <CabinetHeader />
      <section className="container page-head">
        <div>
          <h1>{id ? `Заявка${app ? ` № ${app.number}` : ""}` : "Новая заявка"}</h1>
        </div>
      </section>
      <Sheet>
        <div className="stack">
          {id && data.status === "loading" && <SheetStatus />}
          {app && (
            <div className="panel-lg">
              <div className="stub-app">
                <strong>{applicationTitle(app)}</strong>
                <StatusChip status={app.status} />
              </div>
              <StageBar status={app.status} labels />
              <p className="muted-lg">{app.note}</p>
            </div>
          )}
          <div className="panel-lg">
            <h2>Страница в разработке</h2>
            <p className="muted-lg">
              {id
                ? "Подробности, решение банка и подписание появятся здесь в следующей версии."
                : "Мастер заявки из 6 шагов с автозаполнением по компании появится здесь в следующей версии."}
            </p>
          </div>
          <div className="btn-row">
            <Link to="/cabinet/applications" className="btn btn-dark btn-lg">
              Все заявки
            </Link>
            <Link to="/calculator" className="btn btn-accent btn-lg">
              Рассчитать платёж
            </Link>
          </div>
        </div>
      </Sheet>
      <SiteFooter />
    </>
  );
}
