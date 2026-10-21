// Моки заявок — синтетические данные, пока на бэкенде нет API заявок.
// Заявки привязаны к компаниям демо-персоны Анны (anna@example.com) по ИНН: у неё они появятся,
// когда компании добавлены в кабинет; у остальных пользователей заявок нет.

import type { Application, Company } from "../api/cabinet";

const NORTH_WIND = "7701234560"; // ООО «Северный ветер»
const IP_SMIRNOVA = "500100000015"; // ИП Смирнова А. В.

type MockApplication = Omit<Application, "companyId"> & { companyInn: string };

const APPLICATIONS: MockApplication[] = [
  {
    id: "a-1051",
    number: "1051",
    companyInn: IP_SMIRNOVA,
    createdAt: "2026-10-20",
    product: "Оборотный кредит",
    amount: 1_500_000,
    termMonths: 12,
    status: "docs_requested",
    note: "Счёт в другом банке — без выписки не сможем решить",
  },
  {
    id: "a-1047",
    number: "1047",
    companyInn: NORTH_WIND,
    createdAt: "2026-10-18",
    product: "Оборотный кредит",
    amount: 5_000_000,
    termMonths: 12,
    status: "counter_offer",
    note: "Можем дать 2 750 000 ₽ на 12 мес или 4 920 000 ₽ на 24 мес",
  },
  {
    id: "a-1042",
    number: "1042",
    companyInn: NORTH_WIND,
    createdAt: "2026-10-15",
    product: "Оборотный кредит",
    amount: 3_000_000,
    termMonths: 24,
    status: "checking",
    note: "От вас ничего не нужно — сообщим здесь",
  },
  {
    id: "a-1053",
    number: "1053",
    companyInn: NORTH_WIND,
    createdAt: "2026-10-21",
    product: "Овердрафт",
    amount: null,
    termMonths: null,
    status: "draft",
    note: "Заполнено 3 шага из 6",
  },
  {
    id: "a-1012",
    number: "1012",
    companyInn: NORTH_WIND,
    createdAt: "2026-08-02",
    product: "Оборотный кредит",
    amount: 1_200_000,
    termMonths: 18,
    status: "issued",
    note: "Кредит выдан 05.08, платёж 68 400 ₽ в месяц",
  },
  {
    id: "a-1008",
    number: "1008",
    companyInn: IP_SMIRNOVA,
    createdAt: "2026-07-27",
    product: "Оборотный кредит",
    amount: 800_000,
    termMonths: 6,
    status: "rejected",
    note: "Не хватило данных об оборотах — подайте снова с выпиской",
  },
];

const reply = <T>(value: T, ms = 250) =>
  new Promise<T>((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));

export function listApplications(companies: Company[]): Promise<Application[]> {
  const idByInn = new Map(companies.map((c) => [c.inn, c.id]));
  const apps: Application[] = [];
  for (const { companyInn, ...app } of APPLICATIONS) {
    const companyId = idByInn.get(companyInn);
    if (companyId) apps.push({ ...app, companyId });
  }
  return reply(apps);
}
