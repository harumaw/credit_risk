import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { ApplicationDetails } from "../../api/cabinet";
import { ChevronLeft } from "../Icons";
import { StageBar } from "./StatusChip";

interface Props {
  back: { to: string; label: string };
  title: string;
  sub?: ReactNode;
  /** Справа от заголовка: чип статуса */
  aside?: ReactNode;
  /** Полоска этапов под заголовком */
  app?: ApplicationDetails | null;
}

/** Тёмная шапка экранов заявки: назад, заголовок, подзаголовок, этапы. */
export function ApplicationHead({ back, title, sub, aside, app }: Props) {
  return (
    <section className="container page-head app-head">
      <div className="app-head-row">
        <div className="app-head-text">
          <Link to={back.to} className="back-link">
            <ChevronLeft size={14} strokeWidth={2.4} />
            {back.label}
          </Link>
          <h1>{title}</h1>
          {sub && <p className="page-head-sub">{sub}</p>}
        </div>
        {aside}
      </div>
      {app && app.status !== "draft" && <StageBar status={app.status} labels />}
    </section>
  );
}
