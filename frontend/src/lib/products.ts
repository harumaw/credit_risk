// Каталог кредитов для витрины: тексты лендинга. Ставки и правила допуска — в таблице credit_products.

export type CompanyKind = "ip" | "llc";

export interface Product {
  slug: string;
  title: string;
  menuNote: string;
  cardNote: string;
  forKinds: CompanyKind[];
  calc?: { minAmount: number; maxAmount: number; minTerm: number; maxTerm: number };
}

export const PRODUCTS: Product[] = [
  {
    slug: "working-capital",
    title: "Кредит на оборотные средства",
    menuNote: "Без залога, от 300 тыс. до 50 млн ₽",
    cardNote: "300 тыс. – 50 млн ₽, 6–60 мес, без залога",
    forKinds: ["ip", "llc"],
    calc: { minAmount: 300_000, maxAmount: 50_000_000, minTerm: 6, maxTerm: 60 },
  },
  {
    slug: "credit-line",
    title: "Кредитная линия",
    menuNote: "Берёте частями, когда нужно",
    cardNote: "300 тыс. – 30 млн ₽, до 18 мес",
    forKinds: ["ip", "llc"],
    calc: { minAmount: 300_000, maxAmount: 30_000_000, minTerm: 6, maxTerm: 18 },
  },
  {
    slug: "overdraft",
    title: "Овердрафт",
    menuNote: "Для клиентов с расчётным счётом",
    cardNote: "Доля оборотов по счёту, до 12 мес",
    forKinds: ["ip", "llc"],
  },
  {
    slug: "secured",
    title: "Кредит под залог",
    menuNote: "До 150 млн ₽ на срок до 10 лет",
    cardNote: "До 150 млн ₽, до 10 лет, ставка ниже",
    forKinds: ["llc"],
    calc: { minAmount: 1_000_000, maxAmount: 150_000_000, minTerm: 12, maxTerm: 120 },
  },
  {
    slug: "state-support",
    title: "Льготный кредит",
    menuNote: "По государственной программе",
    cardNote: "Условия по программе господдержки",
    forKinds: ["ip", "llc"],
  },
];

export function findProduct(slug: string | null): Product | undefined {
  return PRODUCTS.find((p) => p.slug === slug);
}
