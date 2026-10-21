import { rubShort } from "../../lib/format";

export interface FlowBar {
  label: string;
  inflow: number;
  balance: number;
  forecast: boolean;
}

/** Столбики «поступления + остаток» по периодам, прогноз — светлым. Без библиотек, на CSS. */
export function FlowChart({ bars }: { bars: FlowBar[] }) {
  const max = Math.max(...bars.map((b) => Math.max(b.inflow, b.balance)), 1);
  const pct = (v: number) => `${Math.max(Math.round((v / max) * 100), v > 0 ? 2 : 0)}%`;
  const fact = bars.filter((b) => !b.forecast);
  const summary = fact.length
    ? `Поступления от ${rubShort(Math.min(...fact.map((b) => b.inflow)))} до ${rubShort(Math.max(...fact.map((b) => b.inflow)))} за период`
    : "Нет данных";

  return (
    <div className="flow">
      <div className="flow-legend" aria-hidden="true">
        <span>
          <i className="sw-inflow" />
          Поступления
        </span>
        <span>
          <i className="sw-balance" />
          Остаток
        </span>
        <span>
          <i className="sw-forecast" />
          Прогноз
        </span>
      </div>
      <div className={`flow-chart ${bars.length > 8 ? "is-dense" : ""}`} role="img" aria-label={summary}>
        {bars.map((b, i) => (
          <div
            key={`${b.label}-${i}`}
            className={`flow-col ${b.forecast ? "is-forecast" : ""}`}
            title={`${b.label}${b.forecast ? " (прогноз)" : ""}: поступления ${rubShort(b.inflow)}, остаток ${rubShort(b.balance)}`}
          >
            <div className="flow-bars">
              <span className="bar-inflow" style={{ height: pct(b.inflow) }} />
              <span className="bar-balance" style={{ height: pct(b.balance) }} />
            </div>
            <span className="flow-label">{b.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const GHOST = [40, 55, 35, 45, 60, 50, 65, 48, 52, 70, 58, 62];

/** Заглушка графика, пока нет данных об оборотах. */
export function GhostChart() {
  return (
    <div className="flow-ghost" aria-hidden="true">
      {GHOST.map((h, i) => (
        <span key={i} style={{ height: `${h}%` }} />
      ))}
    </div>
  );
}
