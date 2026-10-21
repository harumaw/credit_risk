import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { listCompanies, type Company } from "../api/cabinet";
import { useAsync, type AsyncState } from "../lib/useAsync";

/** Выбор в переключателе: конкретная компания или сводка по всем. */
export type Selection = "all" | string;

const STORAGE_KEY = "cabinet_company";

function readStored(): Selection | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(value: Selection): void {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // приватный режим — выбор просто не запомнится
  }
}

interface CompanyContextValue {
  companies: AsyncState<Company[]>;
  /** Выбор с учётом списка: неизвестный id → первая компания */
  selection: Selection;
  selected: Company | null;
  select: (value: Selection) => void;
  reload: () => void;
}

const CompanyContext = createContext<CompanyContextValue | null>(null);

export function CompanyProvider({ children }: { children: ReactNode }) {
  const { reload, ...companies } = useAsync(listCompanies, []);
  const [stored, setStored] = useState<Selection | null>(readStored);

  const select = useCallback((value: Selection) => {
    setStored(value);
    writeStored(value);
  }, []);

  const value = useMemo<CompanyContextValue>(() => {
    const list = companies.status === "ready" ? companies.data : [];
    const found = list.find((c) => c.id === stored) ?? null;
    const selection: Selection = stored === "all" || !list.length ? "all" : (found ?? list[0]).id;
    return {
      companies,
      selection,
      selected: list.find((c) => c.id === selection) ?? null,
      select,
      reload,
    };
  }, [companies, stored, select, reload]);

  return <CompanyContext.Provider value={value}>{children}</CompanyContext.Provider>;
}

export function useCompanies(): CompanyContextValue {
  const ctx = useContext(CompanyContext);
  if (!ctx) throw new Error("useCompanies вне CompanyProvider");
  return ctx;
}
