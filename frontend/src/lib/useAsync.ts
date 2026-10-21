import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../api/client";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

/**
 * Загрузка данных для страницы: состояние + повтор.
 * Смена deps — заново с «Загрузка…»; reload() — тихо, старые данные видны до прихода новых.
 */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setState({ status: "loading" });
    // load — свежая стрелка на каждом рендере; перезапуск задают только deps
  }, deps);

  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => !cancelled && setState({ status: "ready", data }),
      (err) =>
        !cancelled &&
        setState({ status: "error", message: err instanceof ApiError ? err.message : "Не удалось загрузить данные" }),
    );
    return () => {
      cancelled = true;
    };
  }, [...deps, attempt]);

  const reload = useCallback(() => {
    setState((s) => (s.status === "error" ? { status: "loading" } : s));
    setAttempt((n) => n + 1);
  }, []);
  return { ...state, reload };
}
