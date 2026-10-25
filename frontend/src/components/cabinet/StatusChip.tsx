import type { Application, ApplicationStatus } from "../../api/cabinet";
import { rub } from "../../lib/format";

type Tone = "act" | "offer" | "wait" | "draft" | "ok" | "no";

interface StatusMeta {
  label: string;
  tone: Tone;
  /** Текущий этап (индекс в STAGES); -1 — заявка ещё не отправлена */
  stage: number;
  /** Чем выше, тем раньше в списке: сначала то, где нужно действие клиента */
  priority: number;
  active: boolean;
  action: string;
}

export const STATUS: Record<ApplicationStatus, StatusMeta> = {
  docs_requested: { label: "Нужны документы", tone: "act", stage: 1, priority: 5, active: true, action: "Открыть" },
  signing: { label: "Подписание", tone: "act", stage: 3, priority: 4, active: true, action: "Подписать" },
  counter_offer: { label: "Контрпредложение", tone: "offer", stage: 2, priority: 3, active: true, action: "Выбрать вариант" },
  approved: { label: "Одобрено", tone: "offer", stage: 2, priority: 3, active: true, action: "Принять" },
  submitted: { label: "Отправлена", tone: "wait", stage: 0, priority: 2, active: true, action: "Открыть" },
  checking: { label: "Проверяем", tone: "wait", stage: 1, priority: 2, active: true, action: "Открыть" },
  draft: { label: "Черновик", tone: "draft", stage: -1, priority: 1, active: true, action: "Продолжить" },
  issued: { label: "Выдан", tone: "ok", stage: 4, priority: 0, active: false, action: "Открыть" },
  rejected: { label: "Отказ", tone: "no", stage: 2, priority: 0, active: false, action: "Почему" },
  cancelled: { label: "Отменена", tone: "no", stage: 2, priority: 0, active: false, action: "Открыть" },
};

export const STAGES = ["Отправлена", "Проверяем", "Решение", "Подписание", "Выдан"];

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

/** Куда ведёт кнопка заявки: решение — на экран решения, подписание — на подписание, остальное — на ход заявки. */
export function applicationHref(app: Application): string {
  const base = `/cabinet/applications/${app.id}`;
  if (app.status === "approved" || app.status === "counter_offer" || app.status === "rejected") return `${base}/decision`;
  return app.status === "signing" ? `${base}/sign` : base;
}

export function StatusChip({ status }: { status: ApplicationStatus }) {
  const meta = STATUS[status];
  return <span className={`chip chip-${meta.tone}`}>{meta.label}</span>;
}

/** Полоска этапов: пройденные — залиты, текущий — акцентом; у выданного кредита залиты все. */
export function StageBar({ status, labels = false }: { status: ApplicationStatus; labels?: boolean }) {
  const { stage } = STATUS[status];
  const done = status === "issued";
  const label = stage < 0 ? "Заявка не отправлена" : `Этап ${stage + 1} из ${STAGES.length}: ${STAGES[stage]}`;
  const cls = (i: number) => (i < stage || (done && i === stage) ? "on" : i === stage ? "now" : undefined);
  return (
    <div className="stage-bar" role="img" aria-label={label}>
      <div className="stage-track">
        {STAGES.map((s, i) => (
          <span key={s} className={cls(i)} />
        ))}
      </div>
      {labels && (
        <div className="stage-labels" aria-hidden="true">
          {STAGES.map((s, i) => (
            <span key={s} className={i === stage ? `${cls(i)} cur` : cls(i)}>
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
