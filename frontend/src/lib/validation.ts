// Быстрые проверки в браузере, чтобы не гонять заведомо плохую форму на сервер.
// Окончательно всё проверяет бэкенд (app/types.py) — правила здесь те же.

import type { FieldErrors } from "../api/client";
import type { RegisterPayload } from "../api/auth";

const INN_WEIGHTS_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8];
const INN_WEIGHTS_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8];

function checkDigit(digits: number[], weights: number[]): number {
  return (weights.reduce((sum, w, i) => sum + w * digits[i], 0) % 11) % 10;
}

/** ИНН физлица: 12 цифр, две контрольные цифры (алгоритм ФНС). */
export function isValidInnFl(value: string): boolean {
  if (!/^\d{12}$/.test(value)) return false;
  const d = [...value].map(Number);
  return checkDigit(d, INN_WEIGHTS_11) === d[10] && checkDigit(d, INN_WEIGHTS_12) === d[11];
}

const INN_WEIGHTS_10 = [2, 4, 10, 3, 5, 9, 4, 6, 8];

/** ИНН юрлица: 10 цифр, одна контрольная цифра. */
export function isValidInnUl(value: string): boolean {
  if (!/^\d{10}$/.test(value)) return false;
  const d = [...value].map(Number);
  return checkDigit(d, INN_WEIGHTS_10) === d[9];
}

/** ИНН компании (10 цифр) или ИП (12 цифр): ошибка простыми словами или null. */
export function innError(value: string): string | null {
  if (!value) return "Введите ИНН";
  if (!/^\d+$/.test(value)) return "Только цифры";
  if (value.length !== 10 && value.length !== 12) return "10 цифр у ООО, 12 у ИП";
  const ok = value.length === 10 ? isValidInnUl(value) : isValidInnFl(value);
  return ok ? null : "Контрольные цифры не сходятся — проверьте ИНН";
}

/** Российский номер: 10 цифр или 11, начиная с 7/8. */
export function isValidPhone(value: string): boolean {
  const digits = value.replace(/\D/g, "");
  return digits.length === 10 || (digits.length === 11 && /^[78]/.test(digits));
}

export function validateRegistration(p: RegisterPayload): FieldErrors {
  const errors: FieldErrors = {};
  if (!p.last_name) errors.last_name = "Укажите фамилию";
  if (!p.first_name) errors.first_name = "Укажите имя";
  if (!p.inn_fl) errors.inn_fl = "Укажите ИНН";
  else if (!/^\d{12}$/.test(p.inn_fl)) errors.inn_fl = "ИНН физлица — 12 цифр";
  else if (!isValidInnFl(p.inn_fl)) errors.inn_fl = "Контрольные цифры не сходятся — проверьте ИНН. Пример тестового: 123456789047";
  if (p.phone && !isValidPhone(p.phone)) errors.phone = "Телефон в формате +7XXXXXXXXXX";
  if (!p.email) errors.email = "Укажите email";
  else if (!/^\S+@\S+\.\S+$/.test(p.email)) errors.email = "Некорректный email";
  if (p.password.length < 8) errors.password = "Минимум 8 символов";
  else if (p.password.length > 72) errors.password = "Максимум 72 символа";
  return errors;
}
