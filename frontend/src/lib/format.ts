// Форматирование сумм, дат и числительных для кабинета.

const MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];
const MONTHS_GENITIVE = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];
const MONTHS_PREPOSITIONAL = [
  "январе", "феврале", "марте", "апреле", "мае", "июне",
  "июле", "августе", "сентябре", "октябре", "ноябре", "декабре",
];

/** 2 750 000 ₽ */
export const rub = (n: number) => `${Math.round(n).toLocaleString("ru-RU")} ₽`;

/** 4,9 млн ₽ / 2,75 млн ₽ — для крупных сумм; меньше миллиона — полностью. */
export function rubShort(n: number): string {
  if (Math.abs(n) < 1_000_000) return rub(n);
  return `${(Math.round(n / 10_000) / 100).toLocaleString("ru-RU")} млн ₽`;
}

/** Подпись шкалы графика: 0 / 500 тыс / 1,5 млн */
export function rubAxis(n: number): string {
  if (n === 0) return "0";
  if (Math.abs(n) >= 1_000_000) return `${(Math.round(n / 100_000) / 10).toLocaleString("ru-RU")} млн`;
  if (Math.abs(n) >= 1_000) return `${Math.round(n / 1_000).toLocaleString("ru-RU")} тыс`;
  return Math.round(n).toLocaleString("ru-RU");
}

/** +8% / −3% */
export function percentDelta(current: number, previous: number): string | null {
  if (!previous) return null;
  const p = Math.round(((current - previous) / previous) * 100);
  return `${p >= 0 ? "+" : "−"}${Math.abs(p)}%`;
}

/** "2026-10" → индекс месяца 0–11 */
const monthIndex = (ym: string) => Number(ym.slice(5, 7)) - 1;

/** "2026-10" → "Окт" */
export const monthShort = (ym: string) => MONTHS_SHORT[monthIndex(ym)];

/** "2026-10" → "октябре" (для «в октябре») */
export const monthPrepositional = (ym: string) => MONTHS_PREPOSITIONAL[monthIndex(ym)];

/** "2026-10-25" → "25 октября" */
export function dayMonth(iso: string): string {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS_GENITIVE[d.getMonth()]}`;
}

/** "2026-10-25" → "25.10" */
export function dayMonthNum(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** «без ИП Смирнова А. В.» / «без 2 компаний» — чьих оборотов нет в сумме */
export function withoutCompanies(names: string[]): string {
  return names.length === 1 ? `без ${names[0]}` : `без ${names.length} компаний`;
}

/** plural(2, ["кредит", "кредита", "кредитов"]) → "кредита" */
export function plural(n: number, forms: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return forms[0];
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return forms[1];
  return forms[2];
}

/** "2026-10-22T14:02:00Z" → "14:02" (по местному времени) */
export const timeHm = (iso: string) => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });

/** 24 → "24%", 21.5 → "21,5%" */
export const percent = (n: number) => `${n.toLocaleString("ru-RU")}%`;
