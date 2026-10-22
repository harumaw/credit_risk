export type FieldErrors = Record<string, string>;

/** Ошибка API: общее сообщение + ошибки по полям (из 422 FastAPI). */
export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: FieldErrors;

  constructor(status: number, message: string, fieldErrors: FieldErrors = {}) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
  ctx?: { min_length?: number; max_length?: number };
}

function describeIssue(issue: ValidationIssue): string {
  switch (issue.type) {
    case "missing":
      return "Обязательное поле";
    case "string_too_short":
      return issue.ctx?.min_length && issue.ctx.min_length > 1
        ? `Минимум ${issue.ctx.min_length} символов`
        : "Обязательное поле";
    case "string_too_long":
      return "Слишком длинное значение";
    case "value_error":
      // Сообщения наших валидаторов приходят как «Value error, <текст>»
      return issue.msg.replace(/^Value error,\s*/, "");
    default:
      return issue.msg;
  }
}

export async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // не JSON — оставим общее сообщение
  }

  if (res.status === 429) {
    return new ApiError(429, "Слишком много попыток. Подождите минуту и попробуйте снова.");
  }

  const detail = (body as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail)) {
    const fieldErrors: FieldErrors = {};
    for (const issue of detail as ValidationIssue[]) {
      const field = String(issue.loc[issue.loc.length - 1]);
      fieldErrors[field] ??= field === "email" && issue.type !== "missing" ? "Некорректный email" : describeIssue(issue);
    }
    return new ApiError(res.status, "Проверьте поля формы", fieldErrors);
  }
  if (typeof detail === "string") return new ApiError(res.status, detail);
  return new ApiError(res.status, res.status >= 500 ? "Сервис временно недоступен" : "Ошибка запроса");
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  token?: string | null;
  /** Дополнительные заголовки, например Idempotency-Key */
  headers?: Record<string, string>;
}

/** Запрос к API на том же origin (в dev — через прокси Vite, в Docker — через nginx). */
export async function request<T>(
  path: string,
  { method = "GET", body, token, headers: extra }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { ...extra };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Нет связи с сервером");
  }

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
