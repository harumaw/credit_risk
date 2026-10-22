import { useState } from "react";

import { rubAxis, rubShort } from "../../lib/format";

export interface FlowBar {
  label: string;
  inflow: number;
  balance: number;
  /** Платежи по кредитам за период */
  payments: number;
  /** Долг по кредитам на конец периода */
  debt: number;
  forecast: boolean;
}

type SeriesKey = "inflow" | "balance" | "payments" | "debt" | "net";

interface Series {
  key: SeriesKey;
  label: string;
  short: string;
  kind: "bar" | "line";
}

const SERIES: Series[] = [
  { key: "inflow", label: "Поступления", short: "поступления", kind: "bar" },
  { key: "balance", label: "Остаток на конец периода", short: "остаток", kind: "bar" },
  { key: "payments", label: "Платежи по кредитам", short: "платежи", kind: "line" },
  { key: "debt", label: "Задолженность по кредитам", short: "долг", kind: "line" },
  { key: "net", label: "Платежи − задолженность", short: "разность", kind: "line" },
];
const DEFAULT_SHOWN: SeriesKey[] = ["inflow", "balance"];

function value(b: FlowBar, key: SeriesKey): number {
  return key === "net" ? b.payments - b.debt : b[key];
}

/** Круглый шаг шкалы (1, 2, 2,5, 5 × 10ⁿ), чтобы делений было не больше `count`; ноль всегда на шкале. */
function niceScale(min: number, max: number, count = 4): number[] {
  const raw = (max - min) / count || 1;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * pow).find((s) => s >= raw) ?? 10 * pow;
  const lo = Math.floor(min / step);
  const hi = Math.ceil(max / step);
  return Array.from({ length: hi - lo + 1 }, (_, i) => (lo + i) * step);
}

/**
 * Столбики «поступления + остаток» по периодам и линии по кредитам поверх них, прогноз — светлым
 * и пунктиром. Справа — какие ряды показывать. Без библиотек: столбики на CSS, линии в SVG.
 */
export function FlowChart({ bars }: { bars: FlowBar[] }) {
  const lastFact = bars.map((b) => b.forecast).lastIndexOf(false);
  const [active, setActive] = useState<number | null>(null);
  const [shown, setShown] = useState<SeriesKey[]>(DEFAULT_SHOWN);
  const current = bars[active ?? (lastFact >= 0 ? lastFact : bars.length - 1)];

  const visible = SERIES.filter((s) => shown.includes(s.key));
  const values = bars.flatMap((b) => visible.map((s) => value(b, s.key)));
  const ticks = niceScale(Math.min(0, ...values), Math.max(1, ...values));
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const y = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const zero = y(0);
  const barPct = (v: number) => `${Math.max((v / hi) * 100, v > 0 ? 1 : 0)}%`;
  const x = (i: number) => ((i + 0.5) / bars.length) * 100;
  const fact = bars.filter((b) => !b.forecast);
  const summary = fact.length
    ? `Поступления от ${rubShort(Math.min(...fact.map((b) => b.inflow)))} до ${rubShort(Math.max(...fact.map((b) => b.inflow)))} за период`
    : "Нет данных";
  const dense = bars.length > 8 ? "is-dense" : "";
  const showInflow = shown.includes("inflow");
  const showBalance = shown.includes("balance");
  const lines = visible.filter((s) => s.kind === "line");

  function toggle(key: SeriesKey) {
    setShown((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));
  }

  // Факт — сплошной линией, прогноз продолжает её пунктиром от последнего факта
  function points(key: SeriesKey, from: number, to: number) {
    return bars
      .slice(from, to + 1)
      .map((b, i) => `${x(from + i)},${100 - y(value(b, key))}`)
      .join(" ");
  }
  const factEnd = lastFact >= 0 ? lastFact : -1;

  return (
    <div className="flow">
      <div className="flow-body">
        <div className="flow-main">
          <div className="flow-plot" role="group" aria-label={summary}>
            <div className="flow-axis" aria-hidden="true">
              {ticks.map((t) => (
                <span key={t} style={{ bottom: `${y(t)}%` }}>
                  {rubAxis(t)}
                </span>
              ))}
            </div>
            <div className={`flow-chart ${dense}`}>
              {ticks.map((t) => (
                <i key={t} className={`flow-grid ${t === 0 && lo < 0 ? "is-zero" : ""}`} style={{ bottom: `${y(t)}%` }} />
              ))}
              {bars.map((b, i) => (
                <button
                  type="button"
                  key={`${b.label}-${i}`}
                  className={`flow-col ${b.forecast ? "is-forecast" : ""} ${b === current ? "is-active" : ""}`}
                  title={`${b.label}${b.forecast ? " (прогноз)" : ""}: ${visible.map((s) => `${s.short} ${rubShort(value(b, s.key))}`).join(", ")}`}
                  aria-label={`${b.label}${b.forecast ? ", прогноз" : ""}`}
                  onClick={() => setActive(i)}
                  onMouseEnter={() => setActive(i)}
                >
                  <span className="flow-bars" style={{ bottom: `${zero}%` }}>
                    {showInflow && <span className="bar-inflow" style={{ height: barPct(b.inflow) }} />}
                    {showBalance && <span className="bar-balance" style={{ height: barPct(b.balance) }} />}
                  </span>
                </button>
              ))}
              {lines.length > 0 && (
                <svg className="flow-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                  {lines.map((s) => (
                    <g key={s.key} className={`line-${s.key}`}>
                      {factEnd >= 0 && <polyline points={points(s.key, 0, factEnd)} />}
                      {factEnd < bars.length - 1 && (
                        <polyline className="is-forecast" points={points(s.key, Math.max(factEnd, 0), bars.length - 1)} />
                      )}
                    </g>
                  ))}
                </svg>
              )}
              {lines.map((s) =>
                bars.map((b, i) => (
                  <i
                    key={`${s.key}-${i}`}
                    className={`flow-dot dot-${s.key} ${b.forecast ? "is-forecast" : ""} ${b === current ? "is-active" : ""}`}
                    style={{ left: `${x(i)}%`, bottom: `${y(value(b, s.key))}%` }}
                    aria-hidden="true"
                  />
                )),
              )}
            </div>
            <div className={`flow-labels ${dense}`} aria-hidden="true">
              {bars.map((b, i) => (
                <span key={`${b.label}-${i}`} className={b === current ? "is-active" : ""}>
                  {b.label}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="flow-series" role="group" aria-label="Что показать на графике">
          {SERIES.map((s) => (
            <button
              key={s.key}
              type="button"
              className="flow-series-item"
              aria-pressed={shown.includes(s.key)}
              onClick={() => toggle(s.key)}
            >
              <i className={`sw sw-${s.key} sw-${s.kind}`} />
              {s.label}
            </button>
          ))}
          <span className="flow-series-note">
            <i className="sw sw-forecast" />
            Прогноз — светлым и пунктиром
          </span>
        </div>
      </div>

      {/* Подсказка по выбранному периоду: на телефоне title не виден, а подписи сокращены */}
      {current && (
        <p className="flow-detail" aria-live="polite">
          <b>
            {current.label}
            {current.forecast ? " · прогноз" : ""}
          </b>
          {visible.length === 0 && <span>выберите, что показать</span>}
          {visible.map((s) => (
            <span key={s.key}>
              <i className={`sw sw-${s.key} sw-${s.kind} ${current.forecast ? "is-forecast" : ""}`} />
              {s.short} {rubShort(value(current, s.key))}
            </span>
          ))}
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
