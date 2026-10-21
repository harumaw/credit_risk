import { useState } from "react";

import { rubAxis, rubShort } from "../../lib/format";

export interface FlowBar {
  label: string;
  inflow: number;
  balance: number;
  forecast: boolean;
}

/** Круглый шаг шкалы (1, 2, 2,5, 5 × 10ⁿ), чтобы делений было не больше `count`. */
function niceScale(max: number, count = 4): number[] {
  const raw = max / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * pow).find((s) => s >= raw) ?? 10 * pow;
  const top = Math.ceil(max / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
}

/** Столбики «поступления + остаток» по периодам, прогноз — светлым. Без библиотек, на CSS. */
export function FlowChart({ bars }: { bars: FlowBar[] }) {
  const lastFact = bars.map((b) => b.forecast).lastIndexOf(false);
  const [active, setActive] = useState<number | null>(null);
  const current = bars[active ?? (lastFact >= 0 ? lastFact : bars.length - 1)];

  const ticks = niceScale(Math.max(...bars.map((b) => Math.max(b.inflow, b.balance)), 1));
  const top = ticks[ticks.length - 1];
  const pct = (v: number) => `${Math.max((v / top) * 100, v > 0 ? 1 : 0)}%`;
  const fact = bars.filter((b) => !b.forecast);
  const summary = fact.length
    ? `Поступления от ${rubShort(Math.min(...fact.map((b) => b.inflow)))} до ${rubShort(Math.max(...fact.map((b) => b.inflow)))} за период`
    : "Нет данных";
  const dense = bars.length > 8 ? "is-dense" : "";

  return (
    <div className="flow">
      <div className="flow-legend" aria-hidden="true">
        <span>
          <i className="sw-inflow" />
          Поступления
        </span>
        <span>
          <i className="sw-balance" />
          Остаток на конец периода
        </span>
        <span>
          <i className="sw-forecast" />
          Прогноз
        </span>
      </div>
      <div className="flow-plot" role="group" aria-label={summary}>
        <div className="flow-axis" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t} style={{ bottom: `${(t / top) * 100}%` }}>
              {rubAxis(t)}
            </span>
          ))}
        </div>
        <div className={`flow-chart ${dense}`}>
          {ticks.map((t) => (
            <i key={t} className="flow-grid" style={{ bottom: `${(t / top) * 100}%` }} />
          ))}
          {bars.map((b, i) => (
            <button
              type="button"
              key={`${b.label}-${i}`}
              className={`flow-col ${b.forecast ? "is-forecast" : ""} ${b === current ? "is-active" : ""}`}
              title={`${b.label}${b.forecast ? " (прогноз)" : ""}: поступления ${rubShort(b.inflow)}, остаток ${rubShort(b.balance)}`}
              aria-label={`${b.label}${b.forecast ? ", прогноз" : ""}`}
              onClick={() => setActive(i)}
              onMouseEnter={() => setActive(i)}
            >
              <span className="bar-inflow" style={{ height: pct(b.inflow) }} />
              <span className="bar-balance" style={{ height: pct(b.balance) }} />
            </button>
          ))}
        </div>
        <div className={`flow-labels ${dense}`} aria-hidden="true">
          {bars.map((b, i) => (
            <span key={`${b.label}-${i}`} className={b === current ? "is-active" : ""}>
              {b.label}
            </span>
          ))}
        </div>
      </div>
      {/* Подсказка по выбранному столбику: на телефоне title не виден, а подписи сокращены */}
      {current && (
        <p className="flow-detail" aria-live="polite">
          <b>
            {current.label}
            {current.forecast ? " · прогноз" : ""}
          </b>
          <span>
            <i className={current.forecast ? "sw-forecast" : "sw-inflow"} />
            поступления {rubShort(current.inflow)}
          </span>
          <span>
            <i className={current.forecast ? "sw-forecast-soft" : "sw-balance"} />
            остаток {rubShort(current.balance)}
          </span>
        </p>
      )}
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
