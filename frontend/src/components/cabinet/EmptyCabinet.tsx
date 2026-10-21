import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { PlusIcon } from "../Icons";

/** Пустой кабинет: компаний ещё нет — ведём к добавлению по ИНН. */
export function EmptyCabinet() {
  return (
    <div className="empty-grid">
      <div className="empty-hero">
        <span className="empty-kicker">Начнём с компании</span>
        <h2>Добавьте компанию по ИНН — покажем, сколько банк готов дать</h2>
        <p>Можно добавить несколько: ООО и ИП, где вы руководитель. Переключаться между ними — в шапке.</p>
        <Link to="/cabinet/companies/new" className="btn btn-accent btn-lg">
          <PlusIcon size={18} strokeWidth={2.4} />
          Добавить компанию
        </Link>
      </div>
      <div className="empty-steps">
        <h2>Что будет после</h2>
        <ol>
          <li>
            <span>1</span>Проверим компанию в реестрах — около минуты
          </li>
          <li>
            <span>2</span>Покажем предварительный лимит и подходящие кредиты
          </li>
          <li>
            <span>3</span>Заявка заполнится данными компании сама
          </li>
        </ol>
        <Link to="/calculator" className="text-link">
          Сначала посчитать платёж в калькуляторе
        </Link>
      </div>
    </div>
  );
}

/** Загрузка / ошибка внутри белого листа. */
export function SheetStatus({ error, onRetry }: { error?: string; onRetry?: () => void }) {
  if (!error) return <p className="sheet-status">Загрузка…</p>;
  return (
    <div className="sheet-status" role="alert">
      <p>{error}</p>
      {onRetry && (
        <button type="button" className="btn btn-dark" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}

/** Белый лист со скруглённым верхом — основная область страницы кабинета. */
export function Sheet({ children }: { children: ReactNode }) {
  return (
    <section className="sheet">
      <div className="container">{children}</div>
    </section>
  );
}
