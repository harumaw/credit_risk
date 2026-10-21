import type { Application, ApplicationStatus } from "../../api/cabinet";
import { rub } from "../../lib/format";

type Tone = "act" | "offer" | "wait" | "draft" | "ok" | "no";

interface StatusMeta {
  label: string;
  tone: Tone;
  /** Сколько этапов из 4 (заполнение → проверка → решение → подписание) пройдено */
  stage: number;
  /** Чем выше, тем раньше в списке: сначала то, где нужно действие клиента */
  priority: number;
  active: boolean;
  action: string;
}

export const STATUS: Record<ApplicationStatus, StatusMeta> = {
  docs_requested: { label: "Нужна выписка", tone: "act", stage: 2, priority: 4, active: true, action: "Загрузить" },
  counter_offer: { label: "Контрпредложение", tone: "offer", stage: 3, priority: 3, active: true, action: "Посмотреть" },
  approved: { label: "Одобрено", tone: "offer", stage: 3, priority: 3, active: true, action: "Подписать" },
  checking: { label: "Проверяем данные", tone: "wait", stage: 2, priority: 2, active: true, action: "Открыть" },
  draft: { label: "Черновик", tone: "draft", stage: 1, priority: 1, active: true, action: "Продолжить" },
  issued: { label: "Выдан", tone: "ok", stage: 4, priority: 0, active: false, action: "Открыть" },
  rejected: { label: "Отказ", tone: "no", stage: 3, priority: 0, active: false, action: "Почему" },
};

export const STAGES = ["Заполнение", "Проверка", "Решение", "Подписание"];

/** Активные — по срочности, затем новые выше. */
export function sortByUrgency(apps: Application[]): Application[] {
  return [...apps].sort(
    (a, b) => STATUS[b.status].priority - STATUS[a.status].priority || b.createdAt.localeCompare(a.createdAt),
  );
}

/** «3 000 000 ₽ на 24 мес» или «Овердрафт, сумма не указана» */
export function applicationTitle(app: Application): string {
  if (app.amount === null) return `${app.product}, сумма не указана`;
  return app.termMonths ? `${rub(app.amount)} на ${app.termMonths} мес` : rub(app.amount);
}

/** Куда ведёт кнопка заявки: за выпиской — на страницу компании, остальное — на экран заявки. */
export function applicationHref(app: Application): string {
  return app.status === "docs_requested" ? `/cabinet/companies/${app.companyId}` : `/cabinet/applications/${app.id}`;
}

export function StatusChip({ status }: { status: ApplicationStatus }) {
  const meta = STATUS[status];
  return <span className={`chip chip-${meta.tone}`}>{meta.label}</span>;
}

/** Полоска этапов заявки; подписи — по желанию. */
export function StageBar({ status, labels = false }: { status: ApplicationStatus; labels?: boolean }) {
  const { stage, tone } = STATUS[status];
  return (
    <div className={`stage-bar stage-${tone}`} role="img" aria-label={`Этап ${stage} из 4: ${STAGES[stage - 1]}`}>
      <div className="stage-track">
        {STAGES.map((s, i) => (
          <span key={s} className={i < stage ? "on" : undefined} />
        ))}
      </div>
      {labels && (
        <div className="stage-labels" aria-hidden="true">
          {STAGES.map((s) => (
            <span key={s}>{s}</span>
          ))}
        </div>
      )}
    </div>
  );
}
