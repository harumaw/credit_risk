import { useEffect, useState } from "react";

import { getApplication, watchApplication, type ApplicationDetails, type ApplicationEvent } from "../api/cabinet";
import { useAsync, type AsyncState } from "../lib/useAsync";

/**
 * Заявка с живой историей: карточка из GET /applications/{id}, история — из потока событий.
 * Новое событие → тихо перечитываем карточку (в ней статус и решение).
 */
export function useApplication(id: string): AsyncState<ApplicationDetails> & { reload: () => void } {
  const data = useAsync(() => getApplication(id), [id]);
  const [live, setLive] = useState<ApplicationEvent[] | null>(null);
  const app = data.status === "ready" ? data.data : null;
  const loaded = app !== null;
  const { reload } = data;

  useEffect(() => {
    setLive(null);
    if (!loaded) return;
    return watchApplication(id, setLive);
  }, [id, loaded]);

  const behind = app !== null && live !== null && live.length > app.history.length;
  useEffect(() => {
    if (behind) reload();
  }, [behind, live, reload]);

  if (data.status !== "ready" || !live || live.length < data.data.history.length) return data;
  // Пока карточка перечитывается, показываем историю из потока — она свежее
  return { ...data, data: { ...data.data, history: live } };
}

/** Отозвана самим клиентом или клиент отказался от кредита. */
export const isCancelled = (app: ApplicationDetails) => app.status === "cancelled";
