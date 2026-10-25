// Каталог кредитов для витрины: тексты лендинга и страниц продуктов. Ставки и правила допуска — в таблице credit_products.

export type CompanyKind = "ip" | "llc";

export interface ProductFact {
  label: string;
  value: string;
  note?: string;
}

export interface Product {
  slug: string;
  /** Код продукта в API (credit_products.code) — для ссылки на форму заявки */
  code: string;
  title: string;
  /** Подпись в переключателе продуктов */
  short: string;
  menuNote: string;
  cardNote: string;
  lead: string;
  facts: ProductFact[];
  example: string;
  fit: string[];
  forKinds: CompanyKind[];
  calc?: { minAmount: number; maxAmount: number; minTerm: number; maxTerm: number };
}

const BASE_FIT = ["Бизнесу больше 6 месяцев", "Нет процедуры банкротства"];

export const PRODUCTS: Product[] = [
  {
    slug: "working-capital",
    code: "WORKING_CAPITAL",
    title: "Кредит на оборотные средства",
    short: "Оборотные средства",
    menuNote: "Без залога, от 300 тыс. до 50 млн ₽",
    cardNote: "300 тыс. – 50 млн ₽, 6–60 мес, без залога",
    lead: "Деньги на закупки, зарплату и налоги. Без залога, решение — через несколько секунд после заявки.",
    facts: [
      { label: "Сумма", value: "300 тыс. – 50 млн ₽", note: "сколько дадут — покажем до заявки" },
      { label: "Срок", value: "6–60 мес", note: "платёж каждый месяц равный" },
      { label: "Ставка", value: "от 24%", note: "зависит от рейтинга компании" },
      { label: "Залог", value: "не нужен", note: "поручительство тоже" },
    ],
    example: "1 000 000 ₽ на 12 месяцев под 24% — платёж 94 560 ₽ в месяц.",
    fit: ["ИП и ООО", ...BASE_FIT, "Доход покрывает платёж с запасом"],
    forKinds: ["ip", "llc"],
    calc: { minAmount: 300_000, maxAmount: 50_000_000, minTerm: 6, maxTerm: 60 },
  },
  {
    slug: "credit-line",
    code: "CREDIT_LINE",
    title: "Кредитная линия",
    short: "Кредитная линия",
    menuNote: "Берёте частями, когда нужно",
    cardNote: "300 тыс. – 30 млн ₽, до 18 мес",
    lead: "Лимит, из которого берёте частями, когда нужно. Проценты — только на то, что взяли.",
    facts: [
      { label: "Лимит", value: "300 тыс. – 30 млн ₽", note: "берёте частями" },
      { label: "Срок", value: "6–18 мес", note: "возвращаете и берёте снова" },
      { label: "Ставка", value: "от 22%", note: "зависит от рейтинга компании" },
      { label: "Залог", value: "не нужен" },
    ],
    example: "Взяли 1 000 000 ₽ на 12 месяцев под 22% — платёж 93 594 ₽ в месяц.",
    fit: ["ИП и ООО", ...BASE_FIT, "Доход покрывает платёж с запасом"],
    forKinds: ["ip", "llc"],
    calc: { minAmount: 300_000, maxAmount: 30_000_000, minTerm: 6, maxTerm: 18 },
  },
  {
    slug: "overdraft",
    code: "OVERDRAFT",
    title: "Овердрафт",
    short: "Овердрафт",
    menuNote: "Для клиентов с расчётным счётом",
    cardNote: "Доля оборотов по счёту, до 12 мес",
    lead: "Платите, даже когда на счёте не хватает денег. Лимит считаем по поступлениям на ваш счёт.",
    facts: [
      { label: "Лимит", value: "100 тыс. – 10 млн ₽", note: "не больше 30% поступлений в месяц" },
      { label: "Срок", value: "1–12 мес", note: "лимит обновляется" },
      { label: "Ставка", value: "от 26%", note: "только на использованную сумму" },
      { label: "Залог", value: "не нужен" },
    ],
    example: "Поступления на счёт 3 млн ₽ в месяц — лимит до 900 000 ₽.",
    fit: ["ИП и ООО с расчётным счётом", ...BASE_FIT, "Регулярные поступления на счёт"],
    forKinds: ["ip", "llc"],
  },
];

export function findProduct(slug: string | null): Product | undefined {
  return PRODUCTS.find((p) => p.slug === slug);
}
